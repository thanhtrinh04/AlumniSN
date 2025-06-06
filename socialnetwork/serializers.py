import datetime
from django.utils import timezone
from django.contrib.auth.hashers import make_password
from rest_framework import serializers
from .models import *
from django.contrib.auth import get_user_model
from rest_framework.serializers import ModelSerializer, PrimaryKeyRelatedField
from cloudinary.uploader import upload as cloudinary_upload
import os
from django.conf import settings
from django.db import transaction
# User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    avatar = serializers.ImageField(required=True)
    cover = serializers.ImageField(required=False)
    is_verified = serializers.SerializerMethodField()
    password_reset_time = serializers.SerializerMethodField()
    must_change_password = serializers.SerializerMethodField()
    mssv = serializers.SerializerMethodField()
    class Meta:
        model = User
        fields = ['id','username', 'password', 'email', 'first_name', 'last_name', 'avatar', 'cover', 'role', 'is_verified', 'password_reset_time', 'must_change_password', 'mssv']
        extra_kwargs = {'password': {'write_only': True}}

    def get_is_verified(self, obj):
        # Truy xuất is_verified từ alumni_set đã được prefetch
        if obj.role == 1:  # ALUMNI
            alumni = getattr(obj, 'alumni', None)  # Tránh lỗi nếu không có liên kết
            return alumni.is_verified if alumni else False
        return None

    def get_mssv(self, obj):
        if obj.role == 1:
            alumni = getattr(obj, 'alumni', None)
            return alumni.mssv if alumni else None
        return None

    def get_password_reset_time(self, obj):
        if obj.role == 2 and hasattr(obj, 'teacher'):
            return obj.teacher.password_reset_time
        return None

    def get_must_change_password(self, obj):
        if obj.role == 2 and hasattr(obj, 'teacher'):
            return obj.teacher.must_change_password
        return None

    def to_representation(self, instance):
        data = super().to_representation(instance)
        view = self.context.get('view')
        action = getattr(view, 'action', None)
        # Loại bỏ 'cover' khi action là 'list'
        if action in ['list', 'list_unverified_users', 'teachers_expired_password_reset']:
            data.pop('cover', None)
        if instance.role != 1:  # Nếu không phải ALUMNI
            data.pop('is_verified', None)
            data.pop('mssv', None)
        if instance.role != 2:  # Nếu không phải TEACHER
            data.pop('password_reset_time', None)
            data.pop('must_change_password', None)
        return data


class UserRegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    mssv = serializers.CharField(write_only=True, required=True)
    avatar = serializers.ImageField(required=True)
    cover = serializers.ImageField(required=False)

    class Meta:
        model = User
        fields = ['id','username', 'password', 'email', 'first_name', 'last_name', 'avatar', 'cover', 'mssv']

    def validate(self, data):
        # Kiểm tra MSSV
        if not data.get('mssv'):
            raise serializers.ValidationError({'mssv': 'Vui lòng cung cấp MSSV cho cựu sinh viên.'})
        # Kiểm tra MSSV đã tồn tại hay chưa
        if Alumni.objects.filter(mssv=data['mssv']).exists():
            raise serializers.ValidationError({'mssv': 'MSSV này đã được đăng ký.'})
        # Kiểm tra có avatar hay không (để hiển thị thông báo lỗi rõ ràng hơn)
        if 'avatar' not in data or not data['avatar']:
            raise serializers.ValidationError({'avatar': 'Vui lòng tải lên ảnh đại diện.'})
        return data

    def create(self, validated_data):
        mssv = validated_data.pop('mssv', None)
        password = validated_data.pop('password')
        with transaction.atomic():
            user = User(**validated_data)
            user.set_password(password)
            user.role = Role.ALUMNI.value  # Mặc định là ALUMNI
            user.save()
            Alumni.objects.create(user=user, mssv=mssv)
        return user
# serializer bổ sung mssv khi đăng kí bằng google
# class AddMSSVSerializer(serializers.Serializer):
#     mssv = serializers.CharField()

#     def validate_mssv(self, value):
#         if Alumni.objects.filter(mssv=value).exists():
#             raise serializers.ValidationError("MSSV này đã được đăng ký cho tài khoản khác.")
#         return value


class TeacherCreateSerializer(serializers.ModelSerializer):
    username = serializers.CharField(read_only=True)
    email = serializers.EmailField(required=True)
    first_name = serializers.CharField(required=True)
    last_name = serializers.CharField(required=True)
    avatar = serializers.ImageField(required=False)

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Email đã được sử dụng")
        return value

    def create(self, validated_data):
        email = validated_data['email']
        first_name = validated_data['first_name']
        last_name = validated_data['last_name']
        avatar = validated_data.get('avatar')

        if not avatar:
            # Đường dẫn tuyệt đối tới file tĩnh
            static_avatar_path = os.path.join(settings.BASE_DIR, 'socialnetwork', 'static', 'image_default', 'alumni.png')
            # Upload lên Cloudinary
            result = cloudinary_upload(static_avatar_path, folder='MangXaHoi')
            avatar_url = result['secure_url']
        else:
            # Nếu có avatar upload, CloudinaryField sẽ tự xử lý
            avatar_url = avatar

        user = User.objects.create(
            username=email,
            email=email,
            first_name=first_name,
            last_name=last_name,
            role=Role.TEACHER.value,
            password=make_password('ou@123'),
            avatar=avatar_url
        )

        Teacher.objects.create(
            user=user,
            must_change_password=True,
            password_reset_time=timezone.now() + datetime.timedelta(hours=24)
        )

        return user

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'avatar']

#serializer đăng kí bằng google
class GoogleRegisterSerializer(serializers.Serializer):
    token = serializers.CharField()
    mssv = serializers.CharField()

    def validate_mssv(self, value):
        if Alumni.objects.filter(mssv=value).exists():
            raise serializers.ValidationError("MSSV đã tồn tại.")
        return value
       


class PostImageSerializer(ModelSerializer):
    class Meta:
        model = PostImage
        fields = ['id', 'image']

class PostSerializer(ModelSerializer):
    images = PostImageSerializer(many=True, required=False)
    user = UserSerializer(read_only=True)
    object_type = serializers.SerializerMethodField()

    class Meta:
        model = Post
        fields = ['id', 'content', 'images', 'lock_comment', 'user', 'created_date', 'updated_date', 'object_type']

    def get_object_type(self, obj):
        if SurveyPost.objects.filter(pk=obj.pk).exists():
            return "survey"
        elif EventInvitePost.objects.filter(pk=obj.pk).exists():
            return "invitation"
        return "post"

class CommentSerializer(ModelSerializer):
    user = UserSerializer(read_only=True)
    post = PostSerializer(read_only=True)

    class Meta:
        model = Comment
        fields = ['id', 'user', 'content', 'image', 'post', 'parent', 'created_date', 'updated_date']

class ReactionSerializer(ModelSerializer):
    user = UserSerializer(read_only=True)
    post = PostSerializer(read_only=True)

    class Meta:
        model = Reaction
        fields = ['id', 'reaction', 'user', 'post', 'created_date', 'updated_date']

class SurveyOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SurveyOption
        fields = ['id', 'option']


class SurveyQuestionSerializer(serializers.ModelSerializer):
    options = SurveyOptionSerializer(many=True, required=True)

    class Meta:
        model = SurveyQuestion
        fields = ['id', 'question', 'multi_choice', 'options']


class SurveyPostSerializer(PostSerializer):
    questions = SurveyQuestionSerializer(many=True, required=False)

    class Meta(PostSerializer.Meta):
        model = SurveyPost
        fields = PostSerializer.Meta.fields + ['end_time', 'survey_type', 'questions']


    def create(self, validated_data):
        questions_data = validated_data.pop('questions', [])
        survey_post = SurveyPost.objects.create(**validated_data)

        for question_data in questions_data:
            options_data = question_data.pop('options', [])
            question = SurveyQuestion.objects.create(survey_post=survey_post, **question_data)

            for option_data in options_data:
                SurveyOption.objects.create(survey_question=question, **option_data)  # Sửa ở đây

        return survey_post

    def update(self, instance, validated_data):
        questions_data = validated_data.pop('questions', None)

        instance.content = validated_data.get('content', instance.content)
        instance.survey_type = validated_data.get('survey_type', instance.survey_type)
        instance.end_time = validated_data.get('end_time', instance.end_time)
        instance.save()

        if questions_data is not None:
            instance.questions.all().delete()
            for question_data in questions_data:
                options_data = question_data.pop('options', [])
                question = SurveyQuestion.objects.create(survey_post=instance, **question_data)
                for option_data in options_data:
                    SurveyOption.objects.create(survey_question=question, **option_data)

        return instance

class UserSurveyOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserSurveyOption
        fields = ['id', 'user', 'survey_option']


class SurveyDraftSerializer(serializers.ModelSerializer):
    class Meta:
        model = SurveyDraft
        fields = ['id', 'survey_post', 'user', 'answers', 'drafted_at']


class GroupSerializer(serializers.ModelSerializer):
    user_count= serializers.IntegerField(read_only=True)
    class Meta:
        model = Group
        fields = ['id', 'group_name', 'user_count','users', 'created_date', 'updated_date']

class GroupDetailSerializer(serializers.ModelSerializer):
    users = UserSerializer(many=True, read_only=True)
    class Meta:
        model = Group
        fields = ['id', 'group_name', 'users', 'created_date', 'updated_date']




class EventInvitePostSerializer(serializers.ModelSerializer):
    images = PostImageSerializer(many=True, required=False)
    class Meta:
        model = EventInvitePost
        fields = ['title','images', 'content', 'send_to_all', 'groups', 'individuals', 'created_date']

    def create(self, validated_data):
        groups = validated_data.pop('groups', [])
        individuals = validated_data.pop('individuals', [])
        images_data = self.context['request'].FILES.getlist('images')

        post = EventInvitePost.objects.create(**validated_data)

        # Gán quan hệ many-to-many
        post.groups.set(groups)
        post.individuals.set(individuals)

        for image in images_data:
            PostImage.objects.create(post=post, image=image)

        return post

class ChatRoomSerializer(serializers.ModelSerializer):
    other_user = serializers.SerializerMethodField()
    last_message = serializers.CharField(read_only=True)
    last_message_time = serializers.DateTimeField(read_only=True)
    last_message_sender_id = serializers.SerializerMethodField()
    is_read = serializers.SerializerMethodField()

    class Meta:
        model = ChatRoom
        fields = ['id', 'other_user', 'last_message', 'last_message_time', 'last_message_sender_id', 'is_read']
        read_only_fields = ['last_message', 'last_message_time', 'last_message_sender_id', 'is_read']

    def get_other_user(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None
        user = request.user
        other = obj.user2 if obj.user1 == user else obj.user1
        return {
            'id': other.id,
            'username': other.username,
            'first_name': other.first_name,
            'last_name': other.last_name,
            'avatar': other.avatar.url if other.avatar else None
        }

    def get_last_message_sender_id(self, obj):
        latest_message_list = getattr(obj, 'latest_message', [])
        if latest_message_list:
            latest_message = latest_message_list[0]
            if latest_message and hasattr(latest_message, 'sender'):
                return latest_message.sender.id
        return None

    def get_is_read(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return True
        user = request.user
        latest_message_list = getattr(obj, 'latest_message', [])
        if not latest_message_list:
            return True
        latest_message = latest_message_list[0]
        if latest_message.sender == user:
            return True
        return latest_message.is_read

class MessageSerializer(serializers.ModelSerializer):
    sender = UserSerializer(read_only=True)
    
    class Meta:
        model = Message
        fields = ['id', 'chat_room', 'sender', 'content', 'is_read', 'created_date']


