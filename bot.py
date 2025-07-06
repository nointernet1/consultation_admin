from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message
from models import Message as DBMessage, Chat, Bot as BotModel
import logging
from tortoise import Tortoise

TORTOISE_CONFIG = {
    "connections": {"default": "sqlite://db.sqlite3"},
    "apps": {
        "models": {
            "models": ["main"],
            "default_connection": "default",
        }
    },
}

class BaseBot:
    def __init__(self, token: str, bot_id: int):
        self.token = token
        self.bot_id = bot_id
        self.bot = Bot(token=token)
        self.storage = MemoryStorage()
        self.dp = Dispatcher(storage=self.storage)
        self.running = False
        self.bot_id = bot_id
        self._tortoise_inited = False
        
        # Регистрация обработчиков
        self.dp.message.register(self.handle_message)
        
        logging.info(f"Base bot initialized: {token[:5]}...")
        
    async def init_orm(self):
        """Инициализация Tortoise ORM для этого бота"""
        if not self._tortoise_inited:
            await Tortoise.init(config=TORTOISE_CONFIG)
            self._tortoise_inited = True
            logging.info(f"Tortoise ORM initialized for bot {self.bot_id}")

    async def handle_message(self, message: types.Message):
        
        if not self._tortoise_inited:
            await self.init_orm()
        
        """Обработчик входящих сообщений для всех ботов"""
        try:
            chat_id = message.chat.id
            text = message.text or message.caption or ''
            
            # Логируем получение сообщения
            logging.info(f"Received message from chat {chat_id}: {text[:100]}{'...' if len(text) > 100 else ''}")
            
            # Получаем модель бота из БД
            try:
                bot_instance = await BotModel.get(id=self.bot_id)
                logging.info(f"Bot instance found: {bot_instance.name}")
            except Exception as e:
                logging.error(f"Error getting bot model: {e}")
                return
            
            # Сохраняем сообщение
            try:
                db_message = await DBMessage.create(
                    chat_id=chat_id,
                    text=text,
                    direction='incoming',
                    bot=bot_instance
                )
                logging.info(f"Message saved to DB with ID {db_message.id}")
            except Exception as e:
                logging.error(f"Error saving message to DB: {e}", exc_info=True)
                return
            
            # Создаем название чата
            chat_title = message.chat.title or ""
            if not chat_title:
                if message.chat.first_name or message.chat.last_name:
                    chat_title = f"{message.chat.first_name or ''} {message.chat.last_name or ''}".strip()
                else:
                    chat_title = f"User #{chat_id}"
            
            # Обновляем информацию о чате
            try:
                chat, created = await Chat.get_or_create(
                    id=chat_id,
                    bot=bot_instance,
                    defaults={
                        'title': chat_title,
                        'last_message': text,
                        'unread': 1
                    }
                )
                
                if not created:
                    chat.unread += 1
                    chat.last_message = text
                    await chat.save()
                
                logging.info(f"Chat updated: {chat_title} (ID: {chat_id})")
                
            except Exception as e:
                logging.error(f"Error updating chat: {e}", exc_info=True)
            
        except Exception as e:
            logging.error(f"Unhandled error in message handler: {e}", exc_info=True)
            
    async def start(self):
        """Запуск бота"""
        if not self.running:
            self.running = True
            logging.info("Starting bot polling...")
            await self.dp.start_polling(self.bot)
            logging.info("Bot polling stopped")

    async def stop(self):
        """Остановка бота"""
        if self.running:
            self.running = False
            logging.info("Stopping bot...")
            await self.dp.stop_polling()
            await self.storage.close()
            logging.info("Bot stopped")

class ShopBot(BaseBot):
    """Бот для интернет-магазина"""
    def __init__(self, token: str, bot_id: int):
        super().__init__(token, bot_id)
        
        # Регистрация специфичных обработчиков
        self.dp.message.register(self.start_command, Command("start"))
        self.dp.message.register(self.handle_product_query, F.text.lower().contains("товар"))
        
        logging.info(f"Shop bot initialized: {token[:5]}...")

    async def start_command(self, message: Message):
        """Обработчик команды /start"""
        await message.answer("🛒 Добро пожаловать в наш магазин! Выберите категорию:")
        # Здесь будет логика магазина

    async def handle_product_query(self, message: Message):
        """Обработчик запросов о товарах"""
        await message.answer("🔍 Вот список доступных товаров...")
        # Логика обработки товаров

class ConsultationBot(BaseBot):
    """Бот для записи на консультации"""
    def __init__(self, token: str, bot_id: int):
        super().__init__(token, bot_id)
        
        # Регистрация специфичных обработчиков
        self.dp.message.register(self.start_command, Command("start"))
        self.dp.message.register(self.handle_schedule, Command("schedule"))
        
        logging.info(f"Consultation bot initialized: {token[:5]}...")

    async def start_command(self, message: Message):
        """Обработчик команды /start"""
        await message.answer("📅 Добро пожаловать в бот для записи на консультации!")
        
    async def handle_schedule(self, message: Message):
        """Обработчик команды /schedule"""
        await message.answer("🗓️ Выберите удобное время для консультации:")
        # Логика записи

class TranscriptionBot(BaseBot):
    """Бот для транскрибации сообщений"""
    def __init__(self, token: str, bot_id: int):
        super().__init__(token, bot_id)
        
        # Регистрация обработчика всех сообщений
        self.dp.message.register(self.transcribe_message)
        
        logging.info(f"Transcription bot initialized: {token[:5]}...")

    async def transcribe_message(self, message: Message):
        """Транскрибация входящих сообщений"""
        text = message.text or message.caption or ''
        if text:
            # Здесь будет логика транскрибации
            await message.answer(f"🔤 Транскрипция: {text.upper()}")