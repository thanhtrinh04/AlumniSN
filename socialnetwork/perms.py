from rest_framework import permissions

class IsAdmin(permissions.IsAdminUser):
    def has_permission(self, request, view):
        return request.user and request.user.is_staff

class RolePermission(permissions.BasePermission):
    def __init__(self,allowed_roles):
        self.allowed_roles=allowed_roles

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role in self.allowed_roles)

class IsAuthenticatedUser(permissions.IsAuthenticated):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated


class AllowAll(permissions.AllowAny):
    def has_permission(self, request, view):
        return True


class IsSelf(permissions.IsAuthenticated):
    """
    Quyền này chỉ cho phép người dùng chỉnh sửa chính mình
    (ví dụ update avatar, cover, password).
    """
    def has_permission(self, request, view):
        # Nếu trong URL có pk, kiểm tra pk == user.pk
        if 'pk' in view.kwargs:
            return request.user and str(request.user.pk) == str(view.kwargs['pk'])
        return True  # Nếu không có pk, vẫn cho phép tiếp tục (chờ kiểm tra object)

    def has_object_permission(self, request, view, obj):
        # Chỉ cho phép nếu object chính là user hiện tại
        return obj == request.user


class IsOwner(permissions.BasePermission):
    """
    Chỉ cho phép người tạo bài đăng được xoá bài viết.
    """
    def has_object_permission(self, request, view, obj):
        return obj.author == request.user  # hoặc obj.user tuỳ vào tên trường trong model

class OwnerPermission(permissions.IsAuthenticated):
    def has_object_permission(self, request, view, object):
        return super().has_permission(request, view) and object == request.user

class CommentDeletePermission(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        return obj.post.user == request.user or obj.user == request.user or getattr(request.user, "role", None) == 0