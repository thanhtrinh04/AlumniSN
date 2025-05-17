from datetime import timedelta
import json
from django.db.models.functions.text import Concat
from django.db.models import Value,CharField
from rest_framework.parsers import MultiPartParser,JSONParser
from email.message import EmailMessage
from django.core.mail import EmailMessage
from rest_framework.decorators import action
from rest_framework import parsers, viewsets, generics, permissions, status,filters
from django.db.models.functions import TruncYear, TruncMonth, TruncQuarter
from django.db.models import Count,Q
from django.contrib.auth import get_user_model
from rest_framework.response import Response
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.views import APIView

from SocialNetworkApp import settings
from .firebase_config import create_chat_room, send_message, get_messages, mark_messages_as_read
from django.http import JsonResponse
from socialnetwork.paginator import UserPagination,PostPagination,GroupPagination,OptionUserPagination,MessagePagination,ChatRoomPagination
from rest_framework.pagination import PageNumberPagination

from .models import User,Post,Comment,Reaction,Group,PostImage,SurveyPost,SurveyType,SurveyDraft,SurveyOption,SurveyQuestion,UserSurveyOption,Role, Group, EventInvitePost, Alumni, ChatRoom, Message
from .serializers import UserSerializer,UserRegisterSerializer,TeacherCreateSerializer,PostSerializer,CommentSerializer,SurveyPostSerializer, UserSerializer, SurveyDraftSerializer, \
    ReactionSerializer, GroupSerializer,GroupDetailSerializer,EventInvitePostSerializer, ChatRoomSerializer, MessageSerializer
from .perms import RolePermission,OwnerPermission,CommentDeletePermission,IsOwnerOrAdmin
from cloudinary.uploader import upload
# from .tasks import send_email_async
from socialnetwork.perms import  IsSelf, IsOwner, IsAuthenticatedUser, AllowAll,IsAdmin
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from django.utils import timezone
from django.db import models
from oauth2_provider.views import TokenView 
from django.contrib.auth import authenticate
User = get_user_model()


class UserViewSet(viewsets.ViewSet, generics.ListAPIView, generics.RetrieveAPIView):
    queryset = User.objects.filter(is_active=True)\
        .order_by('-date_joined')\
        .select_related('alumni', 'teacher')
    serializer_class = UserSerializer
    parser_classes = [parsers.MultiPartParser,parsers.JSONParser]
    pagination_class = UserPagination
    permission_classes = [RolePermission]


    # Giới hạn cho Admin
    def get_permissions(self):
        # Truy cập phương thức và đường dẫn request
        request = self.request

        # Kiểm tra nhiều endpoint không cho phép phương thức GET
        if (request.path.endswith('/update_avatar/') or
            request.path.endswith('/update_cover/') or
            request.path.endswith('/change_password/')or 
            request.path.endswith('/create_teacher/')) and request.method == 'GET':
            from rest_framework.exceptions import MethodNotAllowed
            raise MethodNotAllowed(request.method)

        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated()]
        elif self.action in ['destroy','unverified_users', 'verify_user','create_teacher','set_password_reset_time','teachers_expired_password_reset']:
            return [RolePermission([0])]
        else:
            return [IsSelf()]

    def get_queryset(self):
        queryset = self.queryset
        q = self.request.query_params.get('q')
        role = self.request.query_params.get('role')
        
        # Lọc theo role nếu được cung cấp
        if role is not None:
            try:
                role_value = int(role)
                queryset = queryset.filter(role=role_value)
            except ValueError:
                pass
        now = timezone.now()

        queryset = queryset.filter(
            Q(alumni__isnull=True) | Q(alumni__is_verified=True),
            Q(teacher__isnull=True) | Q(teacher__must_change_password=False) | Q(teacher__password_reset_time__lt=now)
        )

        # Tìm kiếm theo tên
        if q:
            queryset = queryset.annotate(
                full_name=Concat('first_name', Value(' '), 'last_name', output_field=CharField())
            ).filter(full_name__icontains=q)
            
        return queryset
    @action(methods=['get'], url_path='current_user', detail=False)
    def get_current_user(self, request):
        if not request.user.is_authenticated:
            return Response({'error': 'Chưa xác thực user'}, status=status.HTTP_401_UNAUTHORIZED)
        return Response(UserSerializer(request.user).data, status=status.HTTP_200_OK)

    @action(methods=['patch'], url_path='verify_user', detail=True)
    def verify_user(self, request, pk=None):
        try:
            user = User.objects.get(pk=pk)
            user.save()
            # Nếu là Alumni thì xác thực trường is_verified
            if hasattr(user, 'alumni'):
                user.alumni.is_verified = True
                user.alumni.save(update_fields=['is_verified'])  # Chỉ cập nhật trường is_verified
            return Response({'message': 'Tài khoản đã được xác thực'}, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response({'error': 'Không tìm thấy người dùng'}, status=status.HTTP_404_NOT_FOUND)

    # Lấy những user chưa dc xác thực (dành cho admin)
    @action(detail=False, methods=['get'], url_path='list_unverified_users')
    def list_unverified_users(self, request):
        q = request.query_params.get('q')
        queryset = User.objects.select_related('alumni').filter(alumni__is_verified=False).order_by('-date_joined')
        if q:
            queryset = queryset.annotate(
                full_name=Concat('last_name', Value(' '), 'first_name', output_field=CharField())
            ).filter(full_name__icontains=q)
        paginator = OptionUserPagination()
        page = paginator.paginate_queryset(queryset, request)
        if page is not None:
            serializer = UserSerializer(page, many=True, context={'request': request, 'view': self})
            return paginator.get_paginated_response(serializer.data)
        serializer = UserSerializer(queryset, many=True, context={'request': request, 'view': self})
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['patch'], url_path='change_password', parser_classes=[parsers.JSONParser])
    def change_password(self, request):
        user = request.user
        old_password = request.data.get('old_password')
        new_password = request.data.get('new_password')

        if not user.check_password(old_password):
            return Response({'error': 'Mật khẩu cũ không đúng'}, status=status.HTTP_400_BAD_REQUEST)

        if not new_password or len(new_password) < 8:
            return Response({'error': 'Mật khẩu mới quá ngắn (ít nhất 8 ký tự)'}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)
        user.save(update_fields=['password'])  # chỉ cập nhật mật khẩu
        # Nếu là giáo viên, cập nhật trạng thái đổi mật khẩu
        if hasattr(user, 'teacher'):
            user.teacher.must_change_password = False
            user.teacher.save(update_fields=['must_change_password'])
        return Response({'message': 'Đổi mật khẩu thành công'}, status=status.HTTP_200_OK)

    @action(detail=False, methods=['patch'], url_path='update_avatar',
            parser_classes=[parsers.MultiPartParser])
    def update_avatar(self, request):
        user = request.user
        avatar = request.FILES.get('avatar')

        if not avatar:
            return Response({'error': 'Vui lòng chọn ảnh avatar'}, status=status.HTTP_400_BAD_REQUEST)

        user.avatar = avatar
        user.save(update_fields=['avatar'])  # chỉ cập nhật avatar
        return Response({'message': 'Cập nhật avatar thành công', 'avatar': user.avatar.url}, status=status.HTTP_200_OK)

    @action(detail=False, methods=['patch'], url_path='update_cover',
            parser_classes=[parsers.MultiPartParser])
    def update_cover(self, request):
        user = request.user
        cover = request.FILES.get('cover')

        if not cover:
            return Response({'error': 'Vui lòng chọn ảnh cover'}, status=status.HTTP_400_BAD_REQUEST)

        user.cover = cover
        user.save(update_fields=['cover'])  # chỉ cập nhật ảnh bìa
        return Response({'message': 'Cập nhật ảnh bìa thành công', 'cover': user.cover.url}, status=status.HTTP_200_OK)

    # ghi đè lại để chỉ lấy 1 số trường nhất định
    def retrieve(self, request, *args, **kwargs):
        try:
            user = self.get_object()
            data = {
                "first_name": user.first_name,
                "last_name": user.last_name,
                "email": user.email,
                "avatar": request.build_absolute_uri(user.avatar.url) if user.avatar else None,
                "cover": request.build_absolute_uri(user.cover.url) if user.cover else None,
            }
            return Response(data, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response({'error': 'Không tìm thấy người dùng'}, status=status.HTTP_404_NOT_FOUND)


    # @action(detail=False, methods=['post'], url_path='create_teacher', permission_classes=[RolePermission([0])])
    @action(detail=False, methods=['post'], url_path='create_teacher',serializer_class=TeacherCreateSerializer)
    def create_teacher(self, request):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()

            # Soạn nội dung HTML
            html_content = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; border: 1px solid #e0e0e0; border-radius: 8px; overflow: hidden;">
                <div style="background-color: #1d559f; padding: 20px; color: white; text-align: center;">
                    <img src="https://res.cloudinary.com/dx8nciong/image/upload/v1746437801/alumnis_avatar-removebg-preview_ypjmpd.png" alt="Logo" style="height: 50px; margin-bottom: 10px;">
                    <h1 style="margin: 0; font-size: 24px;">MẠNG XÃ HỘI CỰU SINH VIÊN</h1>
                </div>

                <div style="padding: 20px; background-color: #f9f9f9;">
                    <p>Quý thầy/cô <strong style="color: #3f51b5;">{user.first_name} {user.last_name}</strong> thân mến,</p>
                    <p>Hệ thống đã khởi tạo tài khoản giảng viên cho thầy/cô với thông tin như sau:</p>

                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 8px;"><strong>👤 Họ tên:</strong></td>
                            <td style="padding: 8px;">{user.first_name} {user.last_name}</td>
                        </tr>
                        <tr style="background-color: #efefef;">
                            <td style="padding: 8px;"><strong>🧾 Username:</strong></td>
                            <td style="padding: 8px;">{user.username}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px;"><strong>🔑 Mật khẩu:</strong></td>
                            <td style="padding: 8px;"><code>ou@123</code></td>
                        </tr>
                    </table>

                    <div style="background-color: #ffebee; color: #c62828; padding: 15px; margin-top: 20px; border-left: 5px solid #d32f2f;">
                        ⚠️ <strong>Lưu ý bảo mật:</strong><br>
                        Vui lòng đăng nhập và đổi mật khẩu trong vòng <strong>24 giờ</strong> để tránh bị khóa tài khoản.
                    </div>

                    <p style="margin-top: 20px;">Nếu có bất kỳ thắc mắc nào, xin vui lòng liên hệ bộ phận hỗ trợ.</p>

                    <hr style="border: none; border-top: 1px solid #ccc; margin: 20px 0;">

                    <p style="font-size: 12px; color: #888;">Email này được gửi tự động từ hệ thống. Vui lòng không phản hồi email này.</p>
                </div>

                <div style="background-color: #eeeeee; padding: 10px; text-align: center; font-size: 13px;">
                    © 2025 AlumniSocialNetwork | <a href="https://your-university.edu.vn" style="color: #3f51b5;">Truy cập hệ thống</a>
                </div>
            </div>
            """

            # Tạo email
            message = Mail(
                from_email=settings.DEFAULT_FROM_EMAIL,
                to_emails=user.email,
                subject='THÔNG TIN TÀI KHOẢN ALUMNISNW CỦA GIẢNG VIÊN',
                html_content=html_content
            )

            try:
                sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
                sg.send(message)
            except Exception as e:
                return Response({'error': f'Lỗi gửi email: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            return Response({
                'message': 'Đã cấp tài khoản giảng viên và gửi email thông báo',
                'user': serializer.data
            }, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


    @action(detail=False, methods=['get'], url_path='teachers_expired_password_reset')
    def teachers_expired_password_reset(self, request):
        now = timezone.now()
        # Lọc các giáo viên có password_reset_time không rỗng và đã quá 24h
        q = request.query_params.get('q')
        queryset = User.objects.select_related('teacher').filter(
            is_active=True,
            teacher__must_change_password=True,
            teacher__password_reset_time__lt=now).order_by('-date_joined')  
        if q:
            queryset = queryset.annotate(
                full_name=Concat('last_name', Value(' '), 'first_name', output_field=CharField())
            ).filter(full_name__icontains=q)
        paginator = OptionUserPagination()
        page = paginator.paginate_queryset(queryset, request)
        if page is not None:
            serializer = UserSerializer(page, many=True, context={'request': request, 'view': self})
            return paginator.get_paginated_response(serializer.data)
        serializer = UserSerializer(queryset, many=True, context={'request': request, 'view': self})
        return Response(serializer.data, status=status.HTTP_200_OK)


       
    @action(methods=['patch'], url_path='set_password_reset_time', detail=True)

    def set_password_reset_time(self, request, pk=None):
        try:
            user = User.objects.get(pk=pk)
            hours = request.data.get('hours', 24)  # Mặc định là 24 giờ nếu không được chỉ định

            try:
                hours = int(hours)
                if hours <= 0:
                    return Response({'error': 'Thời gian phải là số dương'}, status=status.HTTP_400_BAD_REQUEST)
            except ValueError:
                return Response({'error': 'Thời gian phải là số nguyên'}, status=status.HTTP_400_BAD_REQUEST)
            # Kiểm tra xem user có phải là giáo viên không
            if not hasattr(user, 'teacher'):
                return Response({'error': 'Người dùng không phải là giáo viên'}, status=status.HTTP_400_BAD_REQUEST)

            # Thiết lập thời gian phải đổi mật khẩu
            user.teacher.must_change_password = True
            # Tính thời điểm giáo viên phải đổi mật khẩu trong vòng số giờ chỉ định
            reset_time = timezone.now() + timedelta(hours=hours)
            user.teacher.password_reset_time = reset_time
            user.teacher.save(update_fields=['must_change_password', 'password_reset_time'])

            return Response({
                'message': f'Đã thiết lập thời gian đổi mật khẩu: {hours} giờ',
                'password_reset_deadline': reset_time,
            }, status=status.HTTP_200_OK)

        except User.DoesNotExist:
            return Response({'error': 'Không tìm thấy người dùng'}, status=status.HTTP_404_NOT_FOUND)
    def destroy(self, request, *args, **kwargs):
        # Xoá mềm user
        instance = self.get_object()
        instance.soft_delete()  # Sử dụng soft delete thay vì xóa hoàn toàn
        return Response(status=status.HTTP_204_NO_CONTENT)
        


class RegisterAPIView(viewsets.ViewSet, generics.CreateAPIView):
    serializer_class = UserRegisterSerializer
    permission_classes = [AllowAll]
    parser_classes = [parsers.MultiPartParser]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response({
                'user': self.get_serializer(user).data
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CustomSearchFilter(filters.SearchFilter):
    search_param = 'q'

class PostViewSet(viewsets.ViewSet, generics.RetrieveAPIView, generics.ListAPIView):
    queryset = Post.objects.filter(active=True)
    serializer_class = PostSerializer
    pagination_class = PostPagination
    filter_backends = [CustomSearchFilter]
    search_fields = ['content']
    def get_parser_classes(self):
        if self.action in ['create', 'update']:
            return [JSONParser, MultiPartParser]
        return [JSONParser]  # Chỉ sử dụng JSONParser cho các phương thức khá

    def get_permissions(self):
        if self.action == "create":
            return [IsAuthenticated()]
        elif self.action in ["update", "destroy", "lock_unlock_comments"]:
            return [IsOwnerOrAdmin()]
        return super().get_permissions()

    def create(self, request):
        self.check_permissions(request)

        content = request.data.get('content')
        images = request.FILES.getlist('images')  # Lấy tất cả các tệp ảnh

        if not content:
            return Response({"error": "Nội dung bài viết không được để trống."}, status=status.HTTP_400_BAD_REQUEST)

        # Tạo bài viết
        post = Post.objects.create(content=content, lock_comment=True, user=request.user)

        # Xử lý ảnh nếu có
        if images:
            for image in images:
                try:
                    # Tải ảnh lên và lấy URL của ảnh
                    upload_result = upload(image, folder='MangXaHoi')  # Phương thức upload ảnh (Cloudinary hoặc khác)
                    image_url = upload_result.get('secure_url')

                    # Lưu ảnh vào model PostImage liên kết với bài viết
                    PostImage.objects.create(post=post, image=image_url)

                except Exception as e:
                    return Response({"error": f"Lỗi tải ảnh: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        # Serialize bài viết và trả về kết quả
        serializer = self.get_serializer(post)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, pk=None):
        post = get_object_or_404(Post, id=pk, active=True)
        self.check_object_permissions(request, post)

        content = request.data.get('content', post.content)
        image_file = request.FILES.get('image')

        try:
            post.content = content
            post.save(update_fields=['content'])

            if image_file:
                # Tạo ảnh mới liên kết với post
                upload_result = upload(image_file, folder='MangXaHoi')
                PostImage.objects.create(post=post, image=upload_result.get('secure_url'))
            elif 'image' in request.data and request.data['image'] == '':
                # Nếu client gửi image = '' thì xoá tất cả ảnh của post
                post.images.all().delete()

        except Exception as e:
            return Response({"error": f"Lỗi cập nhật ảnh: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        return Response({'message': 'Chỉnh sửa bài viết thành công.'}, status=status.HTTP_200_OK)

    def destroy(self, request, pk=None):
        post = get_object_or_404(Post, id=pk, active=True)
        print("POST USER:", post.user)
        print("REQUEST USER:", request.user)
        self.check_object_permissions(request, post)
        post.soft_delete()  # Gọi hàm soft delete từ model
        return Response({'message': 'Xoá bài viết thành công.'}, status=status.HTTP_200_OK)

    @action(methods=['get'], url_path='my-posts', detail=False)
    def get_my_posts(self, request):
        self.check_permissions(request)
        posts = Post.objects.filter(user=request.user, active=True)
        serializer = self.get_serializer(posts, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(methods=['post'], url_path='comment', detail=True)
    def create_comment(self, request, pk=None):
        self.check_permissions(request)
        post = get_object_or_404(Post, pk=pk, active=True)

        if post.lock_comment:
            return Response({"message": "Bài viết đã khóa bình luận"}, status=status.HTTP_403_FORBIDDEN)

        content = request.data.get('content')
        image = request.FILES.get('image')

        image_url = None
        if image:
            try:
                upload_result = upload(image, folder='MangXaHoi')
                image_url = upload_result.get('secure_url')
            except Exception as e:
                return Response({"error": f"Lỗi đăng ảnh: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        comment = Comment.objects.create(content=content, image=image_url, user=request.user, post=post)
        serializer = CommentSerializer(comment)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(methods=['patch'], url_path='lock-unlock-comment', detail=True)
    def lock_unlock_comments(self, request, pk=None):
        post = get_object_or_404(Post, pk=pk, active=True)
        self.check_object_permissions(request, post)
        post.lock_comment = not post.lock_comment
        post.save(update_fields=['lock_comment'])
        return Response({'message': 'Cập nhật trạng thái bình luận thành công.'}, status=status.HTTP_200_OK)


    @action(methods=['get'], detail=True, url_path='reacts')
    def reacts(self, request, pk=None):
        post = get_object_or_404(Post, pk=pk, active=True)
        reactions = Reaction.objects.filter(post=post, user__is_active=True)
        serializer = ReactionSerializer(reactions, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(methods=['post', 'delete'], detail=True, url_path='react', permission_classes=[IsAuthenticated])
    def react(self, request, pk=None):
        post = get_object_or_404(Post, pk=pk, active=True)

        if request.method == 'DELETE':
            try:
                reaction = Reaction.objects.get(user=request.user, post=post)
                reaction.delete()
                # Sửa lại từ 204 => 200, giữ lại message nếu cần
                return Response({"message": "Reaction đã được xóa."}, status=status.HTTP_200_OK)
            except Reaction.DoesNotExist:
                return Response({"detail": "Reaction không tồn tại."}, status=status.HTTP_404_NOT_FOUND)

        elif request.method == 'POST':
            reaction_id = request.data.get("reaction")
            try:
                reaction = Reaction.objects.get(user=request.user, post=post)
                if not reaction_id:
                    reaction.delete()
                    return Response({"message": "Reaction đã được xóa."}, status=status.HTTP_200_OK)
                else:
                    reaction.reaction = reaction_id
                    reaction.save()
                    return Response(ReactionSerializer(reaction).data, status=status.HTTP_200_OK)
            except Reaction.DoesNotExist:
                if not reaction_id:
                    return Response({"detail": "Không có reaction để xóa."}, status=status.HTTP_400_BAD_REQUEST)
                reaction = Reaction.objects.create(user=request.user, post=post, reaction=reaction_id)
                return Response(ReactionSerializer(reaction).data, status=status.HTTP_201_CREATED)


class CommentViewSet(viewsets.ViewSet):
    queryset = Comment.objects.filter(active=True)
    serializer_class = CommentSerializer
    parser_classes = [JSONParser, MultiPartParser]
    def get_permissions(self):
        if self.action == "update":
            return [OwnerPermission()]
        elif self.action == "destroy":
            return [CommentDeletePermission()]
        return super().get_permissions()

    def update(self, request, pk=None):
        comment = get_object_or_404(Comment, id=pk, active=True)
        self.check_object_permissions(request, comment)

        content = request.data.get('content', comment.content)
        image = request.FILES.get('image')

        try:
            if image:
                upload_result = upload(image, folder='MangXaHoi')
                comment.image = upload_result.get('secure_url')
            else:
                comment.image = None
            comment.content = content
            comment.save(update_fields=['content', 'image'])
        except Exception as e:
            return Response({"error": f"Lỗi đăng ảnh: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        return Response({'message': 'Chỉnh sửa bình luận thành công.'}, status=status.HTTP_200_OK)

    def destroy(self, request, pk=None):
        comment = get_object_or_404(Comment, id=pk, active=True)
        self.check_object_permissions(request, comment)
        comment.soft_delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(methods=['post'], detail=True, url_path='reply')
    def reply_comment(self, request, pk=None):
        self.check_permissions(request)
        comment = get_object_or_404(Comment, id=pk, active=True)

        if comment.post.lock_comment:
            return Response({'message': 'Bài viết này đã bị khóa bình luận.'}, status=status.HTTP_403_FORBIDDEN)

        content = request.data.get('content')
        image = request.FILES.get('image')

        image_url = None
        if image:
            try:
                upload_result = upload(image, folder='MangXaHoi')
                image_url = upload_result.get('secure_url')
            except Exception as e:
                return Response({"error": f"Lỗi đăng ảnh: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        reply = Comment.objects.create(content=content, image=image_url, user=request.user, post=comment.post,
                                       parent=comment)

        serializer = CommentSerializer(reply)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

class ReactionViewSet(viewsets.ViewSet, generics.ListAPIView):
    queryset = Reaction.objects.filter(active=True)
    serializer_class = ReactionSerializer

class SurveyPostViewSet(viewsets.ModelViewSet):
    queryset = SurveyPost.objects.filter(active=True)
    serializer_class = SurveyPostSerializer

    def get_parser_classes(self):
        if self.action in ['create', 'update']:
            return [JSONParser, MultiPartParser]
        return [JSONParser]

    def get_permissions(self):
        if self.action == "create":
            return [RolePermission([0])]
        elif self.action == "update":
            return [OwnerPermission()]
        elif self.action in ["draft", "submit_survey"]:
            return [RolePermission([1])]
        elif self.action == "resume_survey":
            return [OwnerPermission()]
        return super().get_permissions()

    def create(self, request, *args, **kwargs):
        print("DEBUG: Create survey called")
        self.check_permissions(request)

        content = request.data.get('content', '')  # default là chuỗi rỗng
        images = request.FILES.getlist('images') if hasattr(request, 'FILES') else []
        survey_type = request.data.get('survey_type')
        end_time = request.data.get('end_time')
        questions_data = request.data.get('questions')

        # Nếu questions là chuỗi JSON thì parse
        if isinstance(questions_data, str):
            try:
                questions_data = json.loads(questions_data)
            except json.JSONDecodeError as e:
                return Response({"error": f"Lỗi phân tích cú pháp JSON: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        # Kiểm tra trường bắt buộc
        if not survey_type or not end_time or not questions_data:
            return Response({"error": "survey_type, end_time và questions là bắt buộc."},
                            status=status.HTTP_400_BAD_REQUEST)

        # Tạo survey post chính
        survey_post = SurveyPost.objects.create(
            content=content,
            user=request.user,
            survey_type=survey_type,
            end_time=end_time
        )

        # Upload ảnh nếu có
        for image in images:
            try:
                upload_result = upload(image, folder='MangXaHoi')
                image_url = upload_result.get('secure_url')
                PostImage.objects.create(post=survey_post, image=image_url)
            except Exception as e:
                return Response({"error": f"Lỗi đăng ảnh: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        # Tạo câu hỏi + lựa chọn
        for question_data in questions_data:
            options_data = question_data.pop('options', [])
            question = SurveyQuestion.objects.create(survey_post=survey_post, **question_data)
            for option_data in options_data:
                SurveyOption.objects.create(survey_question=question, **option_data)

        serializer = self.get_serializer(survey_post)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, pk=None):
        survey_post = get_object_or_404(SurveyPost, pk=pk, active=True)
        self.check_object_permissions(request, survey_post)

        content = request.data.get('content', survey_post.content)
        images = request.FILES.getlist('images')
        survey_type = request.data.get('survey_type', survey_post.survey_type)
        end_time = request.data.get('end_time', survey_post.end_time)
        questions_data = request.data.get('questions', [])

        if isinstance(questions_data, str):
            try:
                questions_data = json.loads(questions_data)
            except json.JSONDecodeError:
                questions_data = []

        survey_post.content = content
        survey_post.survey_type = survey_type
        survey_post.end_time = end_time
        survey_post.save()

        PostImage.objects.filter(post=survey_post).delete()
        for image in images:
            try:
                upload_result = upload(image, folder='MangXaHoi')
                image_url = upload_result.get('secure_url')
                PostImage.objects.create(post=survey_post, image=image_url)
            except Exception as e:
                return Response({"error": f"Lỗi đăng ảnh: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        serializer = SurveyPostSerializer(survey_post)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, url_path='draft', methods=['post'])
    def draft(self, request, pk=None):
        self.check_permissions(request)
        existing_answers = UserSurveyOption.objects.filter(
            user=request.user, survey_option__survey_question__survey_post=pk
        )
        if existing_answers.exists():
            return Response({"error": "You had completed this survey."}, status=status.HTTP_400_BAD_REQUEST)

        data = request.data
        survey_post = get_object_or_404(SurveyPost, pk=pk, active=True)
        answers = data.get('answers', {})

        formatted_answers = [{'question_id': key, 'selected_options': value} for key, value in answers.items()]

        draft_instance = SurveyDraft.objects.filter(survey_post=survey_post, user=request.user).first()

        if draft_instance:
            draft_instance.answers = formatted_answers
            draft_instance.save(update_fields=['answers'])
            serializer = SurveyDraftSerializer(draft_instance)
            return Response(serializer.data, status=status.HTTP_200_OK)

        draft_data = {
            'survey_post': survey_post.id,
            'user': request.user.id,
            'answers': formatted_answers
        }

        serializer = SurveyDraftSerializer(data=draft_data)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, url_path='resume', methods=['get'])
    def resume_survey(self, request, pk=None):
        draft = SurveyDraft.objects.filter(survey_post_id=pk, user=request.user).first()

        has_completed = UserSurveyOption.objects.filter(user=request.user,
                                                        survey_option__survey_question__survey_post=pk).exists()

        if not draft:
            return Response({"answers": None, "has_completed": has_completed}, status=status.HTTP_200_OK)

        self.check_object_permissions(request, draft)

        return Response({"answers": draft.answers, "has_completed": has_completed}, status=status.HTTP_200_OK)

    @action(detail=True, url_path='submit', methods=['post'])
    def submit_survey(self, request, pk=None):
        self.check_permissions(request)
        data = request.data
        user = request.user
        survey_post = get_object_or_404(SurveyPost, pk=pk, active=True)
        answers = data.get('answers', {})

        existing_answers = UserSurveyOption.objects.filter(user=user, survey_option__survey_question__survey_post=pk)
        if existing_answers.exists():
            return Response({"error": "You had completed this survey."}, status=status.HTTP_400_BAD_REQUEST)

        required_question_ids = set(survey_post.questions.values_list('id', flat=True))
        answered_question_ids = set(int(question_id) for question_id in answers.keys())

        if required_question_ids - answered_question_ids:
            return Response({"error": "You must answer all questions."}, status=status.HTTP_400_BAD_REQUEST)

        for question_id, selected_option_ids in answers.items():
            for option_id in selected_option_ids:
                UserSurveyOption.objects.create(user=user, survey_option_id=option_id)

        SurveyDraft.objects.filter(user=user, survey_post=survey_post).delete()

        return Response({"message": "Survey submitted successfully."}, status=status.HTTP_201_CREATED)


class GroupViewSet(viewsets.ViewSet, generics.ListAPIView, generics.CreateAPIView, generics.RetrieveAPIView, generics.UpdateAPIView, generics.DestroyAPIView):
    queryset = Group.objects.filter(active=True).order_by('-created_date').prefetch_related('users')
    pagination_class = GroupPagination
    permission_classes = [RolePermission]
    
    def get_serializer_class(self):
        if self.action in ['list', 'create', 'update']:
            return GroupSerializer
        return GroupDetailSerializer
    def get_permissions(self):
        return [RolePermission([0])]

    def get_queryset(self):

        queryset = self.queryset.annotate(user_count=Count('users'))
        # Chỉ lọc theo 'q' nếu đang gọi action 'list'
        if self.action == 'list':
            q = self.request.query_params.get('q')
            if q:
                queryset = queryset.filter(group_name__icontains=q)
        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        # Lấy instance nhóm
        instance = self.get_object()
        # Lấy tham số tìm kiếm và phân trang cho người dùng
        q = request.query_params.get('q')
        
        # Lấy queryset người dùng của nhóm
        users_queryset = instance.users.all().order_by('-date_joined')
        
        # Xử lý tìm kiếm nếu có từ khóa
        if q:
            users_queryset = users_queryset.annotate(
                full_name=Concat('last_name', Value(' '), 'first_name', output_field=CharField())
            ).filter(
                full_name__icontains=q
            )
        
        # Sử dụng paginator cho người dùng
        paginator = OptionUserPagination()
        
        # Lấy dữ liệu người dùng được phân trang
        page = paginator.paginate_queryset(users_queryset, request)
        # Serialize nhóm
        group_serializer = self.get_serializer(instance)
        # Chuẩn bị dữ liệu trả về
        response_data = group_serializer.data
        # Nếu có phân trang
        if page is not None:
            # Serialize người dùng
            users_serializer = UserSerializer(
                page, 
                many=True, 
                context={'request': request, 'view': self}
            )
            
            # Thêm thông tin người dùng và phân trang vào response
            return paginator.get_paginated_response({
                **response_data,
                'users': users_serializer.data
            })
        # Nếu không phân trang
        users_serializer = UserSerializer(
            users_queryset, 
            many=True, 
            context={'request': request, 'view': self}
        )
        response_data['users'] = users_serializer.data
        
        return Response(response_data, status=status.HTTP_200_OK)    

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        group_name = request.data.get('group_name')
        users = request.data.get('users', [])

        if group_name:
            instance.group_name = group_name

        if users:
            # Xóa tất cả users hiện tại
            instance.users.clear()
            # Thêm users mới
            for user_id in users:
                try:
                    user = User.objects.get(id=user_id)
                    instance.users.add(user)
                except User.DoesNotExist:
                    continue

        instance.save()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        # Xoá nhóm
        instance = self.get_object()
        instance.soft_delete()  # Sử dụng soft delete thay vì xóa hoàn toàn
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], url_path='add_users')
    def add_users(self, request, pk=None):
        # Thêm users vào nhóm
        instance = self.get_object()
        users = request.data.get('users', [])
        
        for user_id in users:
            try:
                user = User.objects.get(id=user_id)
                instance.users.add(user)
            except User.DoesNotExist:
                continue
        
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='remove_users')
    def remove_users(self, request, pk=None):
        """Xóa users khỏi nhóm"""
        instance = self.get_object()
        users = request.data.get('users', [])
        
        for user_id in users:
            try:
                user = User.objects.get(id=user_id)
                instance.users.remove(user)
            except User.DoesNotExist:
                continue
        
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


class EventInviteViewSet(viewsets.ViewSet, generics.CreateAPIView, generics.ListAPIView, generics.RetrieveAPIView,
                         generics.DestroyAPIView):
    queryset = EventInvitePost.objects.all()
    serializer_class = EventInvitePostSerializer
    permission_classes = [RolePermission]
    pagination_class = PostPagination
    parser_classes = [parsers.JSONParser, parsers.FormParser, parsers.FormParser,parsers.MultiPartParser]

    def get_permissions(self):
        return [RolePermission([0])]

    def perform_create(self, serializer):
        post = serializer.save(user=self.request.user)

        subject = "Thông báo về bài đăng mời tham gia sự kiện sắp tới của Trường Đại Học Mở Thành phố Hồ Chí Minh"

        title = post.title or "Sự kiện từ Trường Đại Học Mở Thành phố Hồ Chí Minh"
        content = post.content or ""
        image_html = ""
        for image in post.images.all():
            image_html += f"""
                <div style="text-align:center; margin: 10px 0;">
                    <img src="{image.image.url}" alt="Event Image" style="max-width:100%; height:auto; border-radius:8px;">
                </div>
            """
        message = f"""<!DOCTYPE html>
        <html lang="en">
        <head>
          <meta charset="UTF-8">
          <meta name="viewport" content="width=device-width, initial-scale=1.0">
          <title>Event Invitation</title>
          <style>
            body {{ font-family: Arial, sans-serif; color: #333; margin: 0; padding: 0; }}
            .email-container {{ max-width: 600px; margin: 0 auto; border: 1px solid #ddd; }}
            .email-header {{ background-color: #1d559f; padding: 20px; text-align: center; color: white; }}
            .email-body {{ padding: 20px; background-color: #fff; }}
            .event-details {{ background-color: #f9f9f9; border-left: 3px solid #1d559f; padding: 15px; margin: 15px 0; }}
            .cta-button {{ display: inline-block; background-color: #1d559f; color: white; padding: 10px 25px; border-radius: 4px; text-decoration: none; font-weight: bold; }}
            .email-footer {{ background-color: #f5f5f5; padding: 15px; text-align: center; font-size: 12px; color: #666; }}
          </style>
        </head>
        <body>
          <div class="email-container">
            <div class="email-header">
              <h1>Thông báo về bài đăng mời tham gia sự kiện sắp tới của nhà trường</h1>
            </div>
            <div class="email-body">
              <h2>{post.title}</h2>
              <p>{post.content or ''}</p>
              {image_html}
              <a href="#" class="cta-button" style="color: white; text-decoration: none;" onclick="this.style.color='white'">Xác nhận tham gia</a>
              <p>Trân trọng,<br>Trường Đại học Mở TP.HCM</p>
            </div>
            <div class="email-footer">
              <p>© 2025 AlumniSocialNetwork | <a href="#">Liên hệ</a></p>
            </div>
          </div>
        </body>
        </html>"""
        from_email = settings.DEFAULT_FROM_EMAIL

        recipient_list = set()

        # Gửi cho từng cá nhân nếu có
        if hasattr(post, 'receivers'):
            recipient_list |= set(post.receivers.values_list('email', flat=True))

        # Gửi cho người trong các nhóm nếu có
        if hasattr(post, 'groups'):
            for group in post.groups.all():
                recipient_list |= set(group.users.values_list('email', flat=True))

        # Gửi cho tất cả user nếu đánh dấu gửi tới tất cả
        if getattr(post, 'send_to_all', False):
            recipient_list |= set(
                User.objects.exclude(email__isnull=True).exclude(email__exact='').values_list('email', flat=True))

        # Gửi mail
        if recipient_list:
            email = EmailMessage(
                subject=subject,
                body=message,
                from_email=from_email,
                to=list(recipient_list)
            )
            email.content_subtype = "html"  # Đảm bảo email có định dạng HTML
            email.send(fail_silently=True)  # Hoặc False để debug lỗi gửi mail


# class StatisticsViewSet(viewsets.ViewSet):
#     """
#     ViewSet cho các API thống kê
#     """
#     permission_classes = [RolePermission]

#     def get_permissions(self):
#         return [RolePermission([0])]

#     # Đảm bảo chỉ admin mới có quyền truy cập

#     @action(detail=False, methods=['get'], url_path='user_statistics')
#     def user_statistics(self, request):
#         """
#         API thống kê người dùng theo năm, tháng, quý
#         """
#         # Lấy tham số từ query
#         period = request.query_params.get('period', 'month')  # mặc định là tháng
#         year = request.query_params.get('year', timezone.now().year)  # mặc định là năm hiện tại
#         role = request.query_params.get('role', None)  # Tùy chọn lọc theo role

#         # Lọc người dùng theo role nếu có
#         users = User.objects.filter(is_active=True)
#         if role is not None:
#             try:
#                 role_value = int(role)
#                 users = users.filter(role=role_value)
#             except ValueError:
#                 return Response({'error': 'Role không hợp lệ'}, status=status.HTTP_400_BAD_REQUEST)

#         # Thống kê theo từng loại thời gian
#         if period == 'year':
#             # Thống kê theo năm
#             stats = users.annotate(
#                 date=TruncYear('date_joined')
#             ).values('date').annotate(
#                 count=Count('id')
#             ).order_by('date')

#         elif period == 'quarter':
#             # Thống kê theo quý (trong năm đã chọn)
#             stats = users.filter(
#                 date_joined__year=year
#             ).annotate(
#                 date=TruncQuarter('date_joined')
#             ).values('date').annotate(
#                 count=Count('id')
#             ).order_by('date')

#         else:  # default: month
#             # Thống kê theo tháng (trong năm đã chọn)
#             stats = users.filter(
#                 date_joined__year=year
#             ).annotate(
#                 date=TruncMonth('date_joined')
#             ).values('date').annotate(
#                 count=Count('id')
#             ).order_by('date')

#         # Định dạng dữ liệu trả về cho frontend
#         formatted_stats = []

#         for item in stats:
#             stat_item = {}
#             if period == 'year':
#                 stat_item['date'] = item['date'].strftime('%Y')
#                 stat_item['label'] = item['date'].strftime('%Y')
#             elif period == 'quarter':
#                 quarter = (item['date'].month - 1) // 3 + 1
#                 stat_item['date'] = item['date'].strftime('%Y-%m-%d')
#                 stat_item['label'] = f'Q{quarter} {item["date"].year}'
#             else:
#                 stat_item['date'] = item['date'].strftime('%Y-%m-%d')
#                 stat_item['label'] = item['date'].strftime('%m/%Y')

#             stat_item['count'] = item['count']
#             formatted_stats.append(stat_item)

#         # Định dạng dữ liệu cho Chart.js
#         chart_data = {
#             'labels': [item['label'] for item in formatted_stats],
#             'data': [item['count'] for item in formatted_stats],
#         }

#         response_data = {
#             'stats': formatted_stats,  # Dữ liệu chi tiết
#             'chart': chart_data,  # Dữ liệu cho biểu đồ
#             'period': period,
#             'year': int(year) if year else None,
#             'role': role
#         }

#         return Response(response_data, status=status.HTTP_200_OK)

class ChatViewSet(viewsets.ViewSet, generics.ListAPIView, generics.CreateAPIView, generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ChatRoomSerializer
    queryset = ChatRoom.objects.all()
    lookup_field = 'id'
    pagination_class = ChatRoomPagination

    def get_queryset(self):
        return ChatRoom.objects.filter(
            models.Q(user1=self.request.user) | models.Q(user2=self.request.user)
        ).select_related('user1', 'user2')

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        user_id = request.data.get('user_id')
        if not user_id:
            return Response({'error': 'Vui lòng cung cấp ID của người dùng'}, status=status.HTTP_400_BAD_REQUEST)
        if request.user.id == int(user_id):
            return Response({'error': 'Không thể tạo phòng chat với chính mình.'}, status=status.HTTP_400_BAD_REQUEST)

        other_user = get_object_or_404(User, id=user_id)
        
        # Kiểm tra xem phòng chat đã tồn tại chưa
        existing_room = ChatRoom.objects.filter(
            models.Q(user1=request.user, user2=other_user) |
            models.Q(user1=other_user, user2=request.user)
        ).first()
        if existing_room:
            return Response(ChatRoomSerializer(existing_room, context={'request': request}).data)

        chat_room = ChatRoom.objects.create(user1=request.user, user2=other_user)
        # Tạo phòng chat trong Firebase
        create_chat_room(chat_room.id, [request.user, other_user])
        return Response(ChatRoomSerializer(chat_room, context={'request': request}).data)

    @action(detail=True, methods=['get'], url_path='messages')
    def get_messages(self, request, id=None):
        """Lấy tin nhắn mới nhất từ Firebase và đánh dấu đã đọc"""
        chat_room = get_object_or_404(
            ChatRoom.objects.filter(
                models.Q(user1=request.user) | models.Q(user2=request.user)
            ),
            pk=id
        )
        # Lấy tin nhắn mới nhất từ Firebase
        messages = get_messages(id)
        # Đánh dấu đã đọc trên Firebase
        mark_messages_as_read(id, request.user.id)
        return Response(messages)

    @action(detail=True, methods=['post'], url_path='send_message')
    def send_message(self, request, id=None):
        chat_room = get_object_or_404(
            ChatRoom.objects.filter(
                models.Q(user1=request.user) | models.Q(user2=request.user)
            ),
            pk=id
        )
        content = request.data.get('content')
        if not content:
            return Response({'error': 'Vui lòng nhập nội dung tin nhắn'}, status=status.HTTP_400_BAD_REQUEST)

        # Gửi tin nhắn lên Firebase 
        firebase_message = send_message(id, request.user.id, content)
        # Lưu vào DB để backup/thống kê
        db_message = Message.objects.create(
            chat_room=chat_room,
            sender=request.user,
            content=content
        )
        # Cập nhật last_message, last_message_time cho ChatRoom
        chat_room.last_message = content
        chat_room.last_message_time = db_message.created_date
        chat_room.save(update_fields=['last_message', 'last_message_time'])

        return Response(MessageSerializer(db_message).data)

    @action(detail=True, methods=['get'], url_path='old_messages')
    def get_old_messages(self, request, id=None):
        """Phân trang tin nhắn cũ từ DB, trả về từ mới nhất đến cũ nhất để FE append khi cuộn lên"""
        chat_room = get_object_or_404(
            ChatRoom.objects.filter(
                models.Q(user1=request.user) | models.Q(user2=request.user)
            ),
            pk=id
        )
        before_id = request.query_params.get('before_id')
        queryset = chat_room.messages.order_by('-created_date').select_related('sender')
        if before_id:
            try:
                before_message = Message.objects.get(pk=before_id, chat_room=chat_room)
                queryset = queryset.filter(created_date__lt=before_message.created_date)
            except Message.DoesNotExist:
                return Response({'count': 0, 'next': None, 'previous': None, 'results': []}, status=200)
        # Sử dụng DRF Pagination
        paginator = MessagePagination()
        page = paginator.paginate_queryset(queryset, request)
        serializer = MessageSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

# class CustomTokenView(TokenView):
#     def post(self, request, *args, **kwargs):
#         username = request.POST.get('username')
#         password = request.POST.get('password')
#         user = authenticate(username=username, password=password)
#         if user and hasattr(user, 'teacher') and user.teacher.must_change_password:
#             if user.teacher.password_reset_time and user.teacher.password_reset_time < timezone.now():
#                 user.is_active = False
#                 user.save(update_fields=['is_active'])
#                 return JsonResponse({'error': 'Tài khoản đã bị khóa do quá hạn đổi mật khẩu.'}, status=403)
#         return super().post(request, *args, **kwargs)
