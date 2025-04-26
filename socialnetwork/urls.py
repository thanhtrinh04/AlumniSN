from xml.etree.ElementInclude import include

from django.urls import path, include
from rest_framework import routers
from .views import RegisterAPIView, GroupViewSet, UserViewSet,EventInviteViewSet,StatisticsViewSet
router = routers.DefaultRouter()
router.register(r'user', UserViewSet, basename='user')
router.register(r'register',RegisterAPIView, basename='register')
router.register(r'groups',GroupViewSet, basename='groups')
router.register(r'event_invite',EventInviteViewSet, basename='event_invite')
router.register('statistics', StatisticsViewSet, basename='statistics')
urlpatterns = [
    path('',include(router.urls)),

]
