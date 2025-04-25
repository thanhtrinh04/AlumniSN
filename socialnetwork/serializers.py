import datetime
from django.utils import timezone
from django.contrib.auth.hashers import make_password
from rest_framework import serializers
from socialnetwork.models import *
from django.contrib.auth import get_user_model

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['username', 'password', 'email', 'first_name', 'last_name', 'avatar', 'cover', 'role']
        extra_kwargs = {'password': {'write_only': True}}

class UserRegisterSerializer(serializers.ModelSerializer):
        password = serializers.CharField(write_only=True)
        mssv = serializers.CharField(write_only=True, required=False)
        avatar = serializers.ImageField(required=False)
        cover = serializers.ImageField(required=False)

        class Meta:
            model = User
            fields = ['username', 'password', 'email', 'first_name', 'last_name', 'avatar', 'cover', 'role', 'mssv']

        def validate(self, data):
            if User.objects.filter(email=data['email']).exists():  # kiểm tra email
                raise serializers.ValidationError({"email": "Email đã được sử dụng"})
                # Kiểm tra MSSV
            if data['role'] == Role.ALUMNI.value:
                if not data.get('mssv'):
                    raise serializers.ValidationError({'mssv': 'Vui lòng cung cấp MSSV cho cựu sinh viên.'})
                    # Kiểm tra MSSV đã tồn tại hay chưa
                if Alumni.objects.filter(mssv=data['mssv']).exists():
                    raise serializers.ValidationError({'mssv': 'MSSV này đã được đăng ký.'})
            if data['role'] == Role.ALUMNI.value and not data.get('mssv'):
                raise serializers.ValidationError({'mssv': 'Vui lòng cung cấp MSSV cho cựu sinh viên.'})
            if data['role'] in [Role.ADMIN.value, Role.TEACHER.value]:
                raise serializers.ValidationError({'role': 'Không thể đăng ký vai trò này.'})

            # Kiểm tra có avatar hay không (để hiển thị thông báo lỗi rõ ràng hơn)
            if 'avatar' not in data or not data['avatar']:
                raise serializers.ValidationError({'avatar': 'Vui lòng tải lên ảnh đại diện.'})

            return data

        def create(self, validated_data):
            role = validated_data['role']
            mssv = validated_data.pop('mssv', None)
            password = validated_data.pop('password')

            user = User(**validated_data)
            user.set_password(password)
            user.save()

            if role == Role.ALUMNI.value:
                Alumni.objects.create(user=user, mssv=mssv)

            return user


class TeacherCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Email đã được sử dụng")
        return value

    def create(self, validated_data):
        email = validated_data['email']
        first_name = validated_data['first_name']
        last_name = validated_data['last_name']

        user = User.objects.create(
            username=email,
            email=email,
            first_name=first_name,
            last_name=last_name,
            role=Role.TEACHER.value,
            password=make_password('ou@123')
        )

        Teacher.objects.create(
            user=user,
            must_change_password=True,
            password_reset_time=timezone.now() + datetime.timedelta(hours=24)
        )

        return user
