from aiogram import Bot, Dispatcher, types
from models import Message, Chat
import logging
import asyncio

class TelegramBot:
    def __init__(self, token):
        self.token = token
        self.bot = Bot(token=token)
        self.dp = Dispatcher()
        self.running = False
        self.register_handlers()
        logging.info(f"Bot initialized with token: {token[:5]}...")

    def register_handlers(self):
        @self.dp.message()
        async def handle_message(message: types.Message):
            try:
                chat_id = message.chat.id
                text = message.text or ''
                logging.info(f"Received message from {chat_id}: {text}")
                
                # Save message
                await Message.create(
                    chat_id=chat_id,
                    text=text,
                    direction='incoming'
                )
                
                # Update chat info
                chat, created = await Chat.get_or_create(
                    id=chat_id,
                    defaults={
                        'title': message.chat.title or message.chat.first_name or "Unknown",
                        'last_message': text,
                        'unread': 1
                    }
                )
                
                if not created:
                    # Корректное увеличение счетчика непрочитанных
                    chat.unread += 1
                    chat.last_message = text
                    await chat.save()
                    
                logging.info(f"Message saved for chat {chat_id}")
            except Exception as e:
                logging.error(f"Error saving message: {e}", exc_info=True)

    async def start(self):
        if not self.running:
            self.running = True
            logging.info("Starting bot polling...")
            await self.dp.start_polling(self.bot)
            logging.info("Bot polling stopped")

    async def stop(self):
        if self.running:
            self.running = False
            logging.info("Stopping bot...")
            await self.dp.stop_polling()
            await self.bot.session.close()
            logging.info("Bot stopped")