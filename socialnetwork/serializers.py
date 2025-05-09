import datetime
from django.utils import timezone
from django.contrib.auth.hashers import make_password
from rest_framework import serializers
from .models import *
from django.contrib.auth import get_user_model
from rest_framework.serializers import ModelSerializer, PrimaryKeyRelatedField
# User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    avatar = serializers.ImageField(required=True)
    cover = serializers.ImageField(required=False)
    is_verified = serializers.SerializerMethodField()
    class Meta:
        model = User
        fields = ['id','username', 'password', 'email', 'first_name', 'last_name', 'avatar', 'cover', 'role', 'is_verified']
        extra_kwargs = {'password': {'write_only': True}}

    def get_is_verified(self, obj):
        # Truy xuất is_verified từ alumni_set đã được prefetch
        if obj.role == 1:  # ALUMNI
            alumni = getattr(obj, 'alumni', None)  # Tránh lỗi nếu không có liên kết
            return alumni.is_verified if alumni else False
        return None

    def to_representation(self, instance):
        # Nếu không phải ALUMNI thì loại bỏ trường is_verified
        data = super().to_representation(instance)
        if instance.role != 1:  # Nếu không phải ALUMNI
            data.pop('is_verified', None)
        return data


class UserRegisterSerializer(serializers.ModelSerializer):
        password = serializers.CharField(write_only=True)
        mssv = serializers.CharField(write_only=True, required=False)
        avatar = serializers.ImageField(required=True)
        cover = serializers.ImageField(required=False)

        class Meta:
            model = User
            fields = ['id','username', 'password', 'email', 'first_name', 'last_name', 'avatar', 'cover', 'role', 'mssv']

        def validate(self, data):
                # Kiểm tra MSSV
            if data['role'] == Role.ALUMNI.value:
                if not data.get('mssv'):
                    raise serializers.ValidationError({'mssv': 'Vui lòng cung cấp MSSV cho cựu sinh viên.'})
                    # Kiểm tra MSSV đã tồn tại hay chưa
                if Alumni.objects.filter(mssv=data['mssv']).exists():
                    raise serializers.ValidationError({'mssv': 'MSSV này đã được đăng ký.'})
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

    class Meta:
        model = SurveyPost
        fields = ['id', 'end_time', 'survey_type', 'questions']

class UserSurveyOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserSurveyOption
        fields = ['id', 'user', 'survey_option']


class SurveyDraftSerializer(serializers.ModelSerializer):
    class Meta:
        model = SurveyDraft
        fields = ['id', 'survey_post', 'user', 'answers', 'drafted_at']


class GroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = ['id', 'group_name', 'users', 'created_date', 'updated_date']



class GroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = ['id','group_name', 'users']

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
    user1 = UserSerializer(read_only=True)
    user2 = UserSerializer(read_only=True)
    last_message = serializers.CharField(read_only=True)
    last_message_time = serializers.DateTimeField(read_only=True)

    class Meta:
        model = ChatRoom
        fields = ['id', 'user1', 'user2', 'last_message', 'last_message_time']
        read_only_fields = ['last_message', 'last_message_time']

    def create(self, validated_data):
        user_id = self.context['request'].data.get('user_id')
        if not user_id:
            raise serializers.ValidationError("Vui lòng cung cấp ID của người dùng")
            
        try:
            user2 = User.objects.get(id=user_id)
            chat_room = ChatRoom.objects.create(
                user1=self.context['request'].user,
                user2=user2
            )
            return chat_room
        except User.DoesNotExist:
            raise serializers.ValidationError("Người dùng không tồn tại")

class MessageSerializer(serializers.ModelSerializer):
    sender = UserSerializer(read_only=True)
    
    class Meta:
        model = Message
        fields = ['id', 'chat_room', 'sender', 'content', 'is_read', 'created_date']
