from xml.etree.ElementInclude import include

from django.urls import path, include
from . import views
from rest_framework import routers
from .views import RegisterAPIView

router = routers.DefaultRouter()
router.register(r'user', views.UserViewSet, basename='user')
router.register(r'register',views.RegisterAPIView, basename='register')
router.register(r'post', views.PostViewSet, basename='post')
router.register(r'comment', views.CommentViewSet, basename='comment')
router.register(r'reaction', views.ReactionViewSet, basename='reaction')
router.register(r'survey', views.SurveyPostViewSet, basename='survey')
router.register(r'group', views.GroupViewSet, basename='group')
urlpatterns = [
    path('',include(router.urls)),

]
