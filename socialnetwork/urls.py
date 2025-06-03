from xml.etree.ElementInclude import include

from django.urls import path, include
from rest_framework import routers
from .views import RegisterAPIView, GroupViewSet, UserViewSet, EventInviteViewSet, PostViewSet, CommentViewSet, ReactionViewSet, SurveyPostViewSet, ChatViewSet, GoogleRegisterViewSet

router = routers.DefaultRouter()

router.register(r'post', PostViewSet, basename='post')
router.register(r'comment', CommentViewSet, basename='comment')
router.register(r'survey', SurveyPostViewSet, basename='survey')
router.register(r'user', UserViewSet, basename='user')
router.register(r'register', RegisterAPIView, basename='register')
router.register(r'google-register', GoogleRegisterViewSet, basename='google-register')
router.register(r'groups', GroupViewSet, basename='groups')
router.register(r'event_invite', EventInviteViewSet, basename='event_invite')
router.register(r'chat', ChatViewSet, basename='chat')

urlpatterns = [
    path('', include(router.urls)),
]
