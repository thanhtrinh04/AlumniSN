from sys import maxsize

from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from cloudinary.models import CloudinaryField
from enum import IntEnum
from django.utils import timezone
class Role(IntEnum):
    ADMIN = 0
    ALUMNI = 1
    TEACHER = 2
    @classmethod
    def choices(cls):
        return [(role.value, role.name.capitalize()) for role in cls]

class User(AbstractUser):
    avatar = CloudinaryField('avatar', null=False, blank=False, folder='MangXaHoi',
                             default='null')
    cover = CloudinaryField('cover', null=True, blank=True, folder='MangXaHoi')
    role = models.IntegerField(choices=Role.choices(), default=Role.ADMIN.value)
    email = models.EmailField(unique=True,null=False,max_length=255)
    class Meta:
        ordering=['id']


class BaseModel(models.Model):
    created_date=models.DateTimeField(auto_now_add=True,null=True)
    updated_date=models.DateTimeField(auto_now=True,null=True)
    deleted_date=models.DateTimeField(null=True,blank=True)
    active=models.BooleanField(default=True)

    class Meta:
        abstract=True
        ordering=["-id"]

    def soft_delete(self, using=None, keep_parents=False):
        self.deleted_date = timezone.now()
        self.active = False
        self.save(update_fields=['deleted_date', 'active'])

    def restore(self, using=None, keep_parents=False):
        self.deleted_date = None
        self.active = True
        self.save(update_fields=['deleted_date', 'active'])


class Alumni(BaseModel):
    mssv=models.CharField(max_length=10,unique=True,null=False)
    is_verified=models.BooleanField(default=False )
    user = models.OneToOneField(User,on_delete=models.CASCADE)
    def __str__(self):
        return str(self.user)

    def delete(self, *args, **kwargs):
        self.user.delete()
        super().delete(*args, **kwargs)

class Teacher(BaseModel):
    must_change_password=models.BooleanField(default=True)
    password_reset_time=models.DateTimeField(null=True,blank=True)
    user=models.OneToOneField(User,on_delete=models.CASCADE)
    def __str__(self):
        return str(self.user)

class Post(BaseModel):
    content=models.TextField()
    lock_comment=models.BooleanField(default=False)
    user=models.ForeignKey(User,on_delete=models.CASCADE,null=False)

    def __str__(self):
        return self.content

    def can_user_comment(self):
        return not self.lock_comment


class PostImage(models.Model):
    image = CloudinaryField('Post Image', null=True, blank=True, folder='socialnetwork')
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='images',null=True)

class SurveyType(IntEnum):
    TRAINING_PROGRAM = 1
    RECRUITMENT_NEEDS = 2
    INCOME = 3
    EMPLOYMENT_STATUS_OF_ALUMNI = 4

    @classmethod
    def choices(cls):
        return [(type.value, type.name.replace('_', ' ').capitalize()) for type in cls]


class SurveyPost(Post):
    end_time=models.DateTimeField()
    survey_type=models.IntegerField(choices=SurveyType.choices(),default=SurveyType.TRAINING_PROGRAM.value)


class SurveyQuestion(models.Model):
    question=models.TextField()
    multi_choice = models.BooleanField(default=False)
    survey_post = models.ForeignKey(SurveyPost, on_delete=models.CASCADE, related_name='questions')

    def clean(self):
        if self.options.count() < 2:
            raise ValidationError("Each question must have at least 2 options.")

    def __str__(self):
        return self.question



class SurveyOption(models.Model):
    option = models.TextField()

    survey_question = models.ForeignKey(SurveyQuestion, on_delete=models.CASCADE, related_name='options')

    def __str__(self):
        return self.option


class UserSurveyOption(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    survey_option = models.ForeignKey(SurveyOption, on_delete=models.CASCADE)

    class Meta:
        unique_together = ('user', 'survey_option')


class SurveyDraft(models.Model):
    survey_post = models.ForeignKey(SurveyPost, on_delete=models.CASCADE, related_name='drafts')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='drafts')
    answers = models.JSONField(default=dict)
    drafted_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('survey_post', 'user')


class Group(BaseModel):
    group_name = models.CharField(max_length=255, unique=True)
    users = models.ManyToManyField(User, blank=True, related_name='my_groups')

    def __str__(self):
        return self.group_name


class Interaction(BaseModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    post = models.ForeignKey(Post, on_delete=models.CASCADE)

    class Meta:
        abstract = True



class ReactionType(IntEnum):
    LIKE = 1
    HAHA = 2
    LOVE = 3

    @classmethod
    def choices(cls):
        return [(reaction.value, reaction.name.capitalize()) for reaction in cls]


class Reaction(Interaction):
    reaction = models.IntegerField(choices=ReactionType.choices(), default=ReactionType.LIKE.value)

    class Meta:
        unique_together = ('user', 'post')

    def __str__(self):
        return f"{self.user.username} - {ReactionType(self.reaction).name} on Post {self.post.id}"

class Comment(Interaction):
    content = models.TextField(null=False)
    image = CloudinaryField('Comment Image', null=True, blank=True, folder='MangXaHoi')

    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.CASCADE)

    def get_replies(self):
        return Comment.objects.filter(parent=self).order_by("created_date")



class EventInvitePost(Post):
    title = models.CharField(max_length=255)
    send_to_all = models.BooleanField(default=False)
    groups = models.ManyToManyField(Group, blank=True)
    individuals = models.ManyToManyField(User, blank=True, related_name='event_invites')

    def __str__(self):
        return self.title

class ChatRoom(BaseModel):
    user1 = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chat_rooms_as_user1')
    user2 = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chat_rooms_as_user2')
    last_message = models.TextField(null=True, blank=True)
    last_message_time = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"Chat Room {self.id}"

    class Meta:
        unique_together = ('user1', 'user2')

class Message(BaseModel):
    chat_room = models.ForeignKey(ChatRoom, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    content = models.TextField()
    is_read = models.BooleanField(default=False)
    
    def __str__(self):
        return f"Message from {self.sender.username} in Room {self.chat_room.id}"


