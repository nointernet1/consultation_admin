from tortoise import fields, models

class Bot(models.Model):
    id = fields.IntField(pk=True)
    token = fields.CharField(max_length=100, unique=True)
    name = fields.CharField(max_length=100)
    bot_type = fields.CharField(max_length=50)
    is_active = fields.BooleanField(default=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    
    class Meta:
        table = "bots"

class Message(models.Model):
    id = fields.IntField(pk=True)
    chat_id = fields.BigIntField()
    text = fields.TextField()
    direction = fields.CharField(max_length=10)
    timestamp = fields.DatetimeField(auto_now_add=True)
    bot = fields.ForeignKeyField('models.Bot', related_name='messages')
    
    class Meta:
        table = "messages"

class Chat(models.Model):
    id = fields.BigIntField(pk=True)
    title = fields.CharField(max_length=100)
    last_message = fields.TextField()
    unread = fields.IntField(default=0)
    updated = fields.DatetimeField(auto_now=True)
    bot = fields.ForeignKeyField('models.Bot', related_name='chats')
    
    class Meta:
        table = "chats"
        indexes = [
            ("bot", "updated")
        ]