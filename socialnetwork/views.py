from datetime import timedelta
import json
from django.core.mail import send_mail
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework.parsers import MultiPartParser,JSONParser
from rest_framework.decorators import action
from rest_framework import parsers, viewsets, generics,permissions,status
from rest_framework.response import Response
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from SocialNetworkApp import settings

from socialnetwork.paginator import UserPagination
from socialnetwork.perms import IsSelf,IsOwner,IsAuthenticatedUser,AllowAll,RolePermission
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

from .models import User,Post,Comment,Reaction,Group,PostImage,SurveyPost,SurveyType,SurveyDraft,SurveyOption,SurveyQuestion,UserSurveyOption,InvitationPost
from .serializers import UserSerializer,UserRegisterSerializer,TeacherCreateSerializer,PostSerializer,CommentSerializer,SurveyPostSerializer, UserSerializer, SurveyDraftSerializer, \
    ReactionSerializer, GroupSerializer, InvitationPostSerializer
from .perms import RolePermission,OwnerPermission,CommentDeletePermission
from cloudinary.uploader import upload
# from .tasks import send_email_async
User = get_user_model()

class UserViewSet(viewsets.ViewSet ,generics.ListAPIView,generics.RetrieveAPIView):
    queryset = User.objects.filter(is_active=True)
    serializer_class = UserSerializer
    parser_classes = [parsers.MultiPartParser]
    pagination_class = UserPagination

    # Giới hạn List user cho Admin
    def get_permissions(self):
        if self.action in ['list', 'unverified_users', 'verify_user']:
            return [RolePermission([0])]
        else:
            return [IsSelf()]

    @action(methods=['get'], url_path='current_user', detail=False, permission_classes=[permissions.IsAuthenticated])
    def get_current_user(self,request):
        return Response(UserSerializer(request.user).data,status=status.HTTP_200_OK)

    @action(methods=['patch'], url_path='verify_user', detail=True, permission_classes=[RolePermission([0])])
    def verify_user(self, request, pk=None):
        try:
            user =User.objects.get(pk=pk)
            user.save()
            # Nếu là Alumni thì xác thực trường is_verified
            if hasattr(user, 'alumni'):
                user.alumni.is_verified = True
                user.alumni.save(update_fields=['is_verified'])  # Chỉ cập nhật trường is_verified
            return Response({'message': 'Tài khoản đã được xác thực'}, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response({'error': 'Không tìm thấy người dùng'}, status=status.HTTP_404_NOT_FOUND)

    # Lấy những user chưa dc xác thực (dành cho admin)
    @action(detail=False, methods=['get'], url_path='list_unverified_users', permission_classes=[RolePermission([0])])
    def list_unverified_users(self, request):
        unverified = User.objects.filter(alumni__is_verified=False)
        serializer = self.get_serializer(unverified, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['patch'], url_path='change_password',
            permission_classes=[IsSelf()], parser_classes=[parsers.JSONParser])
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
            permission_classes=[IsSelf()],
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
            permission_classes=[IsSelf()],
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

    @action(detail=False, methods=['post'], url_path='create_teacher', permission_classes=[RolePermission([0])])
    def create_teacher(self, request):
        serializer = TeacherCreateSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()

            # Soạn nội dung HTML
            html_content = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; border: 1px solid #e0e0e0; border-radius: 8px; overflow: hidden;">
                <div style="background-color: #673AB7; padding: 20px; color: white; text-align: center;">
                    <img src="https://res.cloudinary.com/demo/image/upload/v1700000000/logo.png" alt="Logo" style="height: 50px; margin-bottom: 10px;">
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
                    © 2025 Mạng xã hội cựu sinh viên | <a href="https://your-university.edu.vn" style="color: #3f51b5;">Truy cập hệ thống</a>
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

            return Response({'message': 'Đã cấp tài khoản giảng viên và gửi email thông báo'},
                            status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(methods=['patch'], url_path='set_password_reset_time', detail=True, permission_classes=[RolePermission([0])])
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
                'password_reset_deadline': reset_time
            }, status=status.HTTP_200_OK)

        except User.DoesNotExist:
            return Response({'error': 'Không tìm thấy người dùng'}, status=status.HTTP_404_NOT_FOUND)

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


class PostViewSet(viewsets.ViewSet, generics.RetrieveAPIView, generics.ListAPIView):
    queryset = Post.objects.filter(active=True)
    serializer_class = PostSerializer
    parser_classes = [JSONParser, MultiPartParser]

    def get_permissions(self):
        if self.action == "create":
            return [IsAuthenticated()]
        elif self.action in ["update", "destroy", "lock_unlock_comments"]:
            return [OwnerPermission(), RolePermission([0])]
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
        image = request.FILES.get('image')

        try:
            if image:
                upload_result = upload(image, folder='MangXaHoi')
                post.image = upload_result.get('secure_url')
            elif 'image' in request.data and request.data['image'] == '':
                post.image = None  # Nếu client gửi image = '' thì xoá ảnh
            post.content = content
            post.save(update_fields=['content', 'image'])
        except Exception as e:
            return Response({"error": f"Lỗi cập nhật ảnh: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        return Response({'message': 'Chỉnh sửa bài viết thành công.'}, status=status.HTTP_200_OK)

    def destroy(self, request, pk=None):
        post = get_object_or_404(Post, id=pk, active=True)
        self.check_object_permissions(request, post)
        post.soft_delete()  # Bạn cần method soft_delete() trong model Post
        return Response({'message': 'Xoá bài viết thành công.'}, status=status.HTTP_204_NO_CONTENT)

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


class SurveyPostViewSet(viewsets.ViewSet):
    queryset = SurveyPost.objects.filter(active=True)
    serializer_class = SurveyPostSerializer
    parser_classes = [JSONParser, MultiPartParser]

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

    def create(self, request):
        self.check_permissions(request)
        content = request.data.get('content')
        images = request.FILES.getlist('images')
        survey_type = request.data.get('survey_type')
        end_time = request.data.get('end_time')
        questions_data = request.data.get('questions')

        try:
            questions_data = json.loads(questions_data)
        except json.JSONDecodeError as e:
            return Response({"error": f"Lỗi phân tích cú pháp JSON: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        survey_post = SurveyPost.objects.create(content=content, user=request.user, survey_type=survey_type,
                                                end_time=end_time)

        for image in images:
            try:
                upload_result = upload(image, folder='MangXaHoi')
                image_url = upload_result.get('secure_url')
                PostImage.objects.create(post=survey_post, image=image_url)
            except Exception as e:
                return Response({"error": f"Lỗi đăng ảnh: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(survey_post)

        for question_data in questions_data:
            options_data = question_data.pop('options', [])
            question = SurveyQuestion.objects.create(survey_post=survey_post, **question_data)
            for option_data in options_data:
                SurveyOption.objects.create(survey_question=question, **option_data)

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
            questions_data = json.loads(questions_data)

        if not isinstance(questions_data, list):
            questions_data = []

        survey_post.content = content
        survey_post.survey_type = survey_type
        survey_post.end_time = end_time
        survey_post.save()

        PostImage.objects.filter(post=survey_post).delete()
        if images:
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


class GroupViewSet(viewsets.ViewSet, generics.ListAPIView, generics.CreateAPIView,
                    generics.RetrieveAPIView, generics.DestroyAPIView, generics.UpdateAPIView):
    queryset = Group.objects.filter(active=True)
    serializer_class = GroupSerializer
    permission_classes = [RolePermission]

    def get_permissions(self):
        return [RolePermission([0])]
