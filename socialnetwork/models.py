from sys import maxsize

from django.db import models
from django.contrib.auth.models import AbstractUser
from cloudinary.models import CloudinaryField
from enum import IntEnum

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

class BaseModel(models.Model):
    created_date=models.DateTimeField(auto_now_add=True,null=True)
    updated_date=models.DateTimeField(auto_now=True,null=True)
    deleted_date=models.DateTimeField(null=True,blank=True)
    active=models.BooleanField(default=True)
    class Meta:
        abstract=True
        ordering=["-id"]



class Alumni(BaseModel):
    mssv=models.CharField(max_length=10,unique=True)
    is_verified=models.BooleanField(default=False )
    user = models.OneToOneField(User,on_delete=models.CASCADE)
    def __str__(self):
        return str(self.user)

class Teacher(BaseModel):
    must_change_password=models.BooleanField(default=True)
    password_reset_time=models.DateTimeField(null=True,blank=True)
    user=models.OneToOneField(User,on_delete=models.CASCADE)
    def __str__(self):
        return str(self.user)

class Post(BaseModel):
    content=models.TextField()
    look_comment=models.BooleanField(default=True)
    user=models.ForeignKey(User,on_delete=models.CASCADE,null=False)

    def __str__(self):
        return self.content

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
    end_timme=models.DateTimeField()
    servey_type=models.IntegerField(choices=SurveyType.choices(),default=SurveyType.TRAINING_PROGRAM.value)

class SurveyQuestion(models.Model):
    question=models.TextField()
    multi_choice = models.BooleanField(default=False)
    survey_post = models.ForeignKey(SurveyPost, on_delete=models.CASCADE, related_name='questions')

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

    users = models.ManyToManyField(User, blank=True)

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

class Comment(Interaction):
    content = models.TextField(null=False)
    image = CloudinaryField('Comment Image', null=True, blank=True, folder='MangXaHoi')

    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.CASCADE)


