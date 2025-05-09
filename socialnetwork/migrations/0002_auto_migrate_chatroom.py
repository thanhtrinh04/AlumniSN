from django.db import migrations, models
import django.db.models.deletion

def migrate_chatroom_data(apps, schema_editor):
    ChatRoom = apps.get_model('socialnetwork', 'ChatRoom')
    User = apps.get_model('socialnetwork', 'User')
    
    # Lấy tất cả phòng chat hiện tại
    for chat_room in ChatRoom.objects.all():
        # Lấy 2 người dùng đầu tiên từ participants
        participants = list(chat_room.participants.all()[:2])
        if len(participants) == 2:
            chat_room.user1 = participants[0]
            chat_room.user2 = participants[1]
            chat_room.save()

class Migration(migrations.Migration):

    dependencies = [
        ('socialnetwork', '0001_initial'),
    ]

    operations = [
        # Thêm trường mới với null=True tạm thời
        migrations.AddField(
            model_name='chatroom',
            name='user1',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='chat_rooms_as_user1', to='socialnetwork.user'),
        ),
        migrations.AddField(
            model_name='chatroom',
            name='user2',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='chat_rooms_as_user2', to='socialnetwork.user'),
        ),
        # Chạy migration để chuyển dữ liệu
        migrations.RunPython(migrate_chatroom_data),
        # Xóa trường participants cũ
        migrations.RemoveField(
            model_name='chatroom',
            name='participants',
        ),
        # Đặt null=False cho các trường mới
        migrations.AlterField(
            model_name='chatroom',
            name='user1',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='chat_rooms_as_user1', to='socialnetwork.user'),
        ),
        migrations.AlterField(
            model_name='chatroom',
            name='user2',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='chat_rooms_as_user2', to='socialnetwork.user'),
        ),
        # Thêm unique_together
        migrations.AlterUniqueTogether(
            name='chatroom',
            unique_together={('user1', 'user2')},
        ),
    ] 