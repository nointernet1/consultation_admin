from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from tortoise import Tortoise
from starlette.middleware.sessions import SessionMiddleware
from models import Message, Chat, Bot as BotModel
from bot import BaseBot, ShopBot, ConsultationBot, TranscriptionBot
import asyncio
import logging
import secrets
import threading
import aiohttp
import os

# Настройка логгирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)

# Инициализация FastAPI
app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=secrets.token_hex(32))
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Глобальные переменные
bot_manager = None

# Конфигурация Tortoise ORM
TORTOISE_CONFIG = {
    "connections": {"default": "sqlite://db.sqlite3"},
    "apps": {
        "models": {
            "models": ["models"],
            "default_connection": "default",
        }
    },
}

class BotManager:
    """Менеджер для управления ботами"""
    def __init__(self):
        self.bots = {}  # bot_id -> (bot_instance, thread)
        self.lock = threading.Lock()
        logging.info("BotManager initialized")
    
    async def start_bot(self, bot_db_instance):
        """Запуск бота в отдельном потоке"""
        try:
            with self.lock:
                bot_id = bot_db_instance.id
                token = bot_db_instance.token
                bot_type = bot_db_instance.bot_type
                
                if bot_id in self.bots:
                    logging.warning(f"Bot {bot_id} already running")
                    return self.bots[bot_id][0]
                
                # Логируем запуск
                logging.info(f"Starting bot: ID={bot_id}, Type={bot_type}, Token={token[:5]}...")
                
                # Создаем экземпляр бота
                if bot_type == 'shop':
                    bot_instance = ShopBot(token, bot_id)
                elif bot_type == 'consultation':
                    bot_instance = ConsultationBot(token, bot_id)
                elif bot_type == 'transcription':
                    bot_instance = TranscriptionBot(token, bot_id)
                else:
                    bot_instance = BaseBot(token, bot_id)
                
                # Запускаем в отдельном потоке
                bot_thread = threading.Thread(
                    target=self.run_bot, 
                    args=(bot_instance,),
                    daemon=True
                )
                bot_thread.start()
                
                self.bots[bot_id] = (bot_instance, bot_thread)
                logging.info(f"Bot {bot_id} started successfully")
                return bot_instance
        
        except Exception as e:
            logging.error(f"Failed to start bot {bot_db_instance.id}: {e}", exc_info=True)
            # Деактивируем бота при ошибке запуска
            bot_db_instance.is_active = False
            await bot_db_instance.save()
            raise
    
    async def run_bot(self, bot_instance):
        """Запускаем бота с обработкой ошибок"""
        try:
            # Инициализируем ORM перед запуском
            await bot_instance.init_orm()
            logging.info(f"Starting bot {bot_instance.bot_id}")
            await bot_instance.start()
        except Exception as e:
            logging.error(f"Bot task failed: {e}", exc_info=True)
        finally:
            # Удаляем бота при завершении задачи
            async with self.lock:
                if bot_instance.bot_id in self.bots:
                    del self.bots[bot_instance.bot_id]
                if bot_instance.bot_id in self.tasks:
                    del self.tasks[bot_instance.bot_id]
            
            # Закрываем соединения ORM
            if bot_instance._tortoise_inited:
                await Tortoise.close_connections()
                logging.info(f"Tortoise connections closed for bot {bot_instance.bot_id}")
    
    async def stop_bot(self, bot_id):
        """Остановка бота"""
        with self.lock:
            if bot_id in self.bots:
                bot_instance, bot_thread = self.bots[bot_id]
                await bot_instance.stop()
                bot_thread.join(timeout=5)
                del self.bots[bot_id]
    
    async def stop_all(self):
        """Остановка всех ботов"""
        with self.lock:
            for bot_id, (bot_instance, bot_thread) in list(self.bots.items()):
                await bot_instance.stop()
                bot_thread.join(timeout=5)
            self.bots.clear()

# Инициализация менеджера ботов
bot_manager = BotManager()

@app.on_event("startup")
async def startup():
    """Инициализация при запуске"""
    await Tortoise.init(config=TORTOISE_CONFIG)
    await Tortoise.generate_schemas()
    
    # Запускаем всех активных ботов из базы
    active_bots = await BotModel.filter(is_active=True)
    for bot in active_bots:
        await bot_manager.start_bot(bot)
    logging.info(f"Started {len(active_bots)} bots on startup")

@app.on_event("shutdown")
async def shutdown():
    """Действия при завершении работы"""
    await bot_manager.stop_all()
    await Tortoise.close_connections()
    
# Вспомогательные функции
async def verify_token(token: str) -> bool:
    """Проверка валидности токена бота"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://api.telegram.org/bot{token}/getMe",
                timeout=5
            ) as response:
                data = await response.json()
                return data.get('ok', False)
    except Exception as e:
        logging.error(f"Token verification failed: {e}")
        return False

async def require_auth(request: Request):
    """Проверка аутентификации"""
    if "bot_id" not in request.session:
        return RedirectResponse(url="/login", status_code=303)
    
    # Проверяем, что бот активен
    bot_id = request.session["bot_id"]
    bot = await BotModel.get_or_none(id=bot_id, is_active=True)
    if not bot:
        request.session.clear()
        return RedirectResponse(url="/login", status_code=303)
    
    return True

# Роуты аутентификации
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = None):
    """Страница входа"""
    bots = await BotModel.filter(is_active=True).all()
    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": error,
        "bots": bots
    })

@app.post("/login")
async def login(request: Request, bot_id: int = Form(...)):
    """Обработка входа"""
    bot = await BotModel.get_or_none(id=bot_id, is_active=True)
    if not bot:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Bot not found or inactive"
        })
    
    # Устанавливаем сессию
    request.session["bot_token"] = bot.token
    request.session["bot_id"] = bot.id
    
    return RedirectResponse(url="/chats", status_code=303)

@app.get("/logout")
async def logout(request: Request):
    """Выход из системы"""
    request.session.clear()
    return RedirectResponse(url="/login")

# Роуты управления ботами
@app.get("/admin/bots", response_class=HTMLResponse)
async def admin_bots(request: Request, auth: bool = Depends(require_auth)):
    """Страница управления ботами"""
    bots = await BotModel.all().order_by("-id")
    return templates.TemplateResponse("admin/bots.html", {
        "request": request,
        "bots": bots
    })

@app.post("/admin/bots")
async def add_bot(
    request: Request,
    token: str = Form(...),
    name: str = Form(...),
    bot_type: str = Form(...)
):
    """Добавление нового бота"""
    # Проверка токена
    if not await verify_token(token):
        return templates.TemplateResponse("admin/bots.html", {
            "request": request,
            "error": "Invalid bot token",
            "bots": await BotModel.all()
        })
    
    # Проверяем, не существует ли уже бота с таким токеном
    existing_bot = await BotModel.get_or_none(token=token)
    if existing_bot:
        return templates.TemplateResponse("admin/bots.html", {
            "request": request,
            "error": "Bot with this token already exists",
            "bots": await BotModel.all()
        })
    
    # Создаем нового бота
    bot = await BotModel.create(
        token=token,
        name=name,
        bot_type=bot_type,
        is_active=True
    )
    
    # Запускаем бота
    await bot_manager.start_bot(bot)
    
    return RedirectResponse(url="/admin/bots", status_code=303)

@app.post("/admin/bots/{bot_id}/toggle")
async def toggle_bot(bot_id: int):
    """Включение/выключение бота"""
    bot = await BotModel.get_or_none(id=bot_id)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    
    if bot.is_active:
        # Останавливаем бота
        await bot_manager.stop_bot(bot_id)
        bot.is_active = False
    else:
        # Запускаем бота
        await bot_manager.start_bot(bot)
        bot.is_active = True
    
    await bot.save()
    return RedirectResponse(url="/admin/bots", status_code=303)


# Роуты для работы с чатами
@app.get("/chats", response_class=HTMLResponse)
async def get_chats(request: Request, auth: bool = Depends(require_auth)):
    """Список чатов"""
    bot_id = request.session.get("bot_id")
    bot = await BotModel.get(id=bot_id)
    
    chats = await Chat.filter(bot=bot).order_by("-updated")
    return templates.TemplateResponse("chats.html", {
        "request": request,
        "chats": chats,
        "current_bot": bot
    })

@app.get("/chat/{chat_id}", response_class=HTMLResponse)
async def get_chat(request: Request, chat_id: int, auth: bool = Depends(require_auth)):
    """Просмотр чата"""
    bot_id = request.session.get("bot_id")
    bot = await BotModel.get(id=bot_id)
    
    messages = await Message.filter(chat_id=chat_id, bot=bot).order_by("timestamp")
    chat = await Chat.get_or_none(id=chat_id, bot=bot)
    
    if chat:
        chat.unread = 0
        await chat.save()
    
    return templates.TemplateResponse("chat.html", {
        "request": request,
        "messages": messages,
        "chat": chat
    })

@app.post("/chat/{chat_id}")
async def send_message(
    request: Request,
    chat_id: int,
    text: str = Form(...),
    auth: bool = Depends(require_auth)
):
    """Отправка сообщения"""
    bot_id = request.session.get("bot_id")
    bot_model = await BotModel.get(id=bot_id)
    
    # Сохраняем исходящее сообщение
    await Message.create(
        chat_id=chat_id,
        text=text,
        direction='outgoing',
        bot=bot_model
    )
    
    # Обновляем информацию о чате
    chat = await Chat.get_or_none(id=chat_id, bot=bot_model)
    if chat:
        chat.last_message = text
        chat.unread = 0
        await chat.save()
    
    # Отправляем сообщение через Telegram API
    token = bot_model.token
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text}
        ) as response:
            if response.status != 200:
                logging.error(f"Failed to send message: {await response.text()}")
    
    return RedirectResponse(url=f"/chat/{chat_id}", status_code=303)