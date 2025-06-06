

from rest_framework.pagination import PageNumberPagination

class UserPagination(PageNumberPagination):
    page_size = 9

class OptionUserPagination(PageNumberPagination):
    page_size = 7

class PostPagination(PageNumberPagination):
    page_size = 5

class CommentPagination(PageNumberPagination):
    page_size = 5

class GroupPagination(PageNumberPagination):
    page_size = 6

class MessagePagination(PageNumberPagination):
    page_size = 8

class ChatRoomPagination(PageNumberPagination):
    page_size = 8