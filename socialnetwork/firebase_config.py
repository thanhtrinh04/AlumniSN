import firebase_admin
from firebase_admin import credentials, firestore
from django.conf import settings
import os

# Initialize Firebase Admin SDK
cred = credentials.Certificate({
    "type": "service_account",
    "project_id": os.getenv('FIREBASE_PROJECT_ID'),
    "private_key_id": os.getenv('FIREBASE_PRIVATE_KEY_ID'),
    "private_key": os.getenv('FIREBASE_PRIVATE_KEY').replace('\\n', '\n'),
    "client_email": os.getenv('FIREBASE_CLIENT_EMAIL'),
    "client_id": os.getenv('FIREBASE_CLIENT_ID'),
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": os.getenv('FIREBASE_CLIENT_CERT_URL')
})

firebase_admin.initialize_app(cred)
db = firestore.client()

def create_chat_room(room_id, users):
    """Tạo phòng chat mới trong Firebase"""
    chat_ref = db.collection('chat_rooms').document(str(room_id))
    chat_ref.set({
        'users': [str(u.id) for u in users],
        'created_at': firestore.SERVER_TIMESTAMP,
        'last_message': None,
        'last_message_time': None
    })
    return chat_ref

def send_message(room_id, sender_id, content):
    """Gửi tin nhắn đến phòng chat"""
    # Kiểm tra phòng chat có tồn tại không
    chat_ref = db.collection('chat_rooms').document(str(room_id))
    chat_doc = chat_ref.get()
    
    if not chat_doc.exists:
        # Tạo phòng chat nếu chưa tồn tại
        chat_ref.set({
            'users': [str(sender_id)],  # Sẽ cập nhật sau
            'created_at': firestore.SERVER_TIMESTAMP,
            'last_message': None,
            'last_message_time': None
        })
    
    # Tạo tin nhắn mới
    message_ref = chat_ref.collection('messages').document()
    message_ref.set({
        'sender_id': str(sender_id),
        'content': content,
        'timestamp': firestore.SERVER_TIMESTAMP,
        'is_read': False
    })
    
    # Cập nhật tin nhắn cuối cùng trong phòng chat
    chat_ref.update({
        'last_message': content,
        'last_message_time': firestore.SERVER_TIMESTAMP
    })
    
    return message_ref

def get_messages(room_id, limit=50):
    """Lấy tin nhắn từ phòng chat"""
    messages_ref = db.collection('chat_rooms').document(str(room_id)).collection('messages')
    # Chỉ sử dụng order_by để tránh yêu cầu index phức tạp
    messages = messages_ref.order_by('timestamp', direction=firestore.Query.DESCENDING).limit(limit).stream()
    return [msg.to_dict() for msg in messages]

def mark_messages_as_read(room_id, user_id):
    """Đánh dấu tất cả tin nhắn chưa đọc là đã đọc cho một người dùng cụ thể"""
    messages_ref = db.collection('chat_rooms').document(str(room_id)).collection('messages')
    # Chỉ lọc theo is_read để tránh yêu cầu index phức tạp
    unread_messages = messages_ref.where('is_read', '==', False).stream()
    
    batch = db.batch()
    for msg in unread_messages:
        # Kiểm tra sender_id trong code thay vì trong query
        if msg.to_dict().get('sender_id') != str(user_id):
            batch.update(msg.reference, {'is_read': True})
    batch.commit() 