from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from sqlalchemy.orm import sessionmaker
from models import Message, Chat
import asyncio

class TelegramBot:
    def __init__(self, token, db_session):
        self.bot = Bot(token=token)
        self.dp = Dispatcher()
        self.db_session = db_session
        self.register_handlers()

    def register_handlers(self):
        @self.dp.message()
        async def handle_message(message: types.Message):
            with self.db_session() as session:
                try:
                    # Сохраняем сообщение
                    msg = Message(
                        chat_id=message.chat.id,
                        text=message.text or '',
                        direction='incoming'
                    )
                    session.add(msg)
                    
                    # Обновляем информацию о чате
                    chat = session.get(Chat, message.chat.id)
                    if not chat:
                        chat = Chat(
                            id=message.chat.id,
                            title=message.chat.title or message.chat.first_name or "Unknown",
                            last_message=message.text,
                            unread=1
                        )
                        session.add(chat)
                    else:
                        chat.last_message = message.text
                        chat.unread += 1
                    
                    session.commit()
                except Exception as e:
                    session.rollback()
                    print(f"Error saving message: {e}")

    async def start(self):
        await self.dp.start_polling(self.bot)

    async def stop(self):
        await self.bot.session.close()