# models.py
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class Message(Base):
    __tablename__ = 'messages'
    
    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer)
    text = Column(Text)
    direction = Column(String(10))
    timestamp = Column(DateTime, default=datetime.now)

class Chat(Base):
    __tablename__ = 'chats'
    
    id = Column(Integer, primary_key=True)
    title = Column(String(100))
    last_message = Column(Text)
    unread = Column(Integer, default=0)
    updated = Column(DateTime, default=datetime.now, onupdate=datetime.now)

engine = create_engine('sqlite:///chats.db', connect_args={'check_same_thread': False})
Base.metadata.create_all(engine)