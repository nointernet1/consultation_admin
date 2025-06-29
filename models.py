from tortoise import fields, models
from datetime import datetime

class Message(models.Model):
    id = fields.IntField(pk=True)
    chat_id = fields.BigIntField()
    text = fields.TextField()
    direction = fields.CharField(max_length=10)
    timestamp = fields.DatetimeField(auto_now_add=True)

class Chat(models.Model):
    id = fields.BigIntField(pk=True)
    title = fields.CharField(max_length=100)
    last_message = fields.TextField()
    unread = fields.IntField(default=0)
    updated = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "chats"