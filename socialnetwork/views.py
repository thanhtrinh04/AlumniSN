from datetime import timedelta

from django.core.mail import send_mail
from django.http.multipartparser import MultiPartParser
from rest_framework.decorators import action
from rest_framework import parsers, viewsets, generics,permissions,status

from SocialNetworkApp import settings
from .serializers import UserSerializer,UserRegisterSerializer,TeacherCreateSerializer
from django.contrib.auth import get_user_model
from rest_framework.response import Response
from socialnetwork.paginator import UserPagination
from socialnetwork.perms import IsAdmin,IsSelf,IsOwner,IsAuthenticatedUser,AllowAll
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from django.utils import timezone


User = get_user_model()

class UserViewSet(viewsets.ViewSet ,generics.ListAPIView,generics.RetrieveAPIView):
    queryset = User.objects.filter(is_active=True)
    serializer_class = UserSerializer
    parser_classes = [parsers.MultiPartParser]
    pagination_class = UserPagination

    # Giới hạn List user cho Admin
    def get_permissions(self):
        if self.action in ['list', 'unverified_users', 'verify_user']:
            return [IsAdmin()]
        else:
            return [IsSelf()]

    @action(methods=['get'], url_path='current_user', detail=False, permission_classes=[permissions.IsAuthenticated])
    def get_current_user(self,request):
        return Response(UserSerializer(request.user).data,status=status.HTTP_200_OK)

    @action(methods=['patch'], url_path='verify_user', detail=True, permission_classes=[IsAdmin()])
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
    @action(detail=False, methods=['get'], url_path='list_unverified_users', permission_classes=[IsAdmin()])
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

    @action(detail=False, methods=['post'], url_path='create_teacher', permission_classes=[IsAdmin()])
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

    @action(methods=['patch'], url_path='set_password_reset_time', detail=True, permission_classes=[IsAdmin()])
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