from social_core.exceptions import AuthForbidden
from .models import Alumni, Role, User
import requests
from django.core.files.uploadedfile import SimpleUploadedFile
import logging
import traceback

def require_mssv(strategy, details, user=None, *args, **kwargs):
    # Nếu user đã có (tức là đã có UserSocialAuth), cho qua
    if user:
        return
    # Nếu chưa có user, yêu cầu mssv (chỉ cho phép đăng ký qua ViewSet custom, không cho pipeline tự tạo user)
    raise AuthForbidden('require_mssv')

