from rest_framework import permissions

class IsAdmin(permissions.IsAdminUser):
    def has_permission(self, request, view):
        return request.user and request.user.is_staff


class IsAuthenticatedUser(permissions.IsAuthenticated):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated


class AllowAll(permissions.AllowAny):
    def has_permission(self, request, view):
        return True


class IsSelf(permissions.IsAuthenticated):
    """
    Quyền này chỉ cho phép người dùng thay đổi thông tin của chính họ:
    dùng cho update avatar, cover, password.
    """
    def has_permission(self, request, view):
        # Kiểm tra xem yêu cầu có phải là của người dùng hiện tại không
        return request.user and (request.user.pk == view.kwargs.get('pk') or request.user.pk == request.user.pk)

    def has_object_permission(self, request, view, obj):
        return obj == request.user


class IsOwner(permissions.BasePermission):
    """
    Chỉ cho phép người tạo bài đăng được xoá bài viết.
    """
    def has_object_permission(self, request, view, obj):
        return obj.author == request.user  # hoặc obj.user tuỳ vào tên trường trong model
