from django.contrib import admin
from django.utils.html import mark_safe
from .models import User, PostImage,Post,Comment,SurveyPost,SurveyOption,SurveyQuestion,Group,InvitationPost,EventInvitePost



class UserAdmin(admin.ModelAdmin):
    readonly_fields = ['avatar_preview','cover_preview']
    def avatar_preview(self, user):
        if user:
            return mark_safe(f"<img src='{user.avatar.url}' width='120' />")
        return '(No avatar)'
    avatar_preview.short_description = 'Avatar'
    def cover_preview(self, user):
        if user:
            return mark_safe(f"<img src='{user.cover.url}' width='120' />")
        return '(No cover)'
    cover_preview.short_description = 'Cover'

admin.site.register(User,UserAdmin)
admin.site.register(PostImage)
admin.site.register(Post)
admin.site.register(Comment)
admin.site.register(SurveyPost)
admin.site.register(SurveyQuestion)
admin.site.register(SurveyOption)
admin.site.register(Group)
admin.site.register(InvitationPost)
admin.site.register(EventInvitePost)

