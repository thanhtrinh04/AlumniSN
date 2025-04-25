from xml.etree.ElementInclude import include

from django.urls import path, include
from . import views
from rest_framework import routers
from .views import RegisterAPIView

router = routers.DefaultRouter()
router.register(r'user', views.UserViewSet, basename='user')
router.register(r'register',views.RegisterAPIView, basename='register')
urlpatterns = [
    path('',include(router.urls)),

]
