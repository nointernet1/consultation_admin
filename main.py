from fastapi import FastAPI, Request, Form, Depends, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from aiogram import Bot
from models import Message, Chat
from bot import TelegramBot
from tortoise import Tortoise
from starlette.middleware.sessions import SessionMiddleware
import asyncio
import logging
import secrets
import threading
import aiohttp

# Initialize FastAPI
app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=secrets.token_hex(32))
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Global bot state
bot_instance = None
bot_thread = None

# Tortoise initialization
TORTOISE_CONFIG = {
    "connections": {"default": "sqlite://db.sqlite3"},
    "apps": {
        "models": {
            "models": ["models"],
            "default_connection": "default",
        }
    },
}

@app.on_event("startup")
async def startup():
    await Tortoise.init(config=TORTOISE_CONFIG)
    await Tortoise.generate_schemas()

@app.on_event("shutdown")
async def shutdown():
    global bot_instance, bot_thread
    if bot_instance:
        await bot_instance.stop()
    if bot_thread:
        bot_thread.join(timeout=5)

async def require_auth(request: Request):
    if "bot_token" not in request.session:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    return True

async def verify_token(token: str) -> bool:
    """Проверка токена"""
    try:
        async with Bot(token=token) as temp_bot:
            await temp_bot.get_me()
        return True
    except Exception as e:
        logging.error(f"Token verification error: {e}")
        return False

def run_bot(token: str):
    """Запуск бота в отдельном потоке"""
    global bot_instance
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    bot_instance = TelegramBot(token)
    loop.run_until_complete(bot_instance.start())

async def start_bot(token: str):
    """Запуск бота в фоновом потоке"""
    global bot_thread
    
    # Остановка предыдущего бота
    if bot_instance:
        await bot_instance.stop()
    if bot_thread:
        bot_thread.join(timeout=5)
    
    # Запуск нового бота в отдельном потоке
    bot_thread = threading.Thread(target=run_bot, args=(token,), daemon=True)
    bot_thread.start()
    return bot_instance

# Routes
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = None):
    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": error
    })

@app.post("/login")
async def login(request: Request, token: str = Form(...)):
    if await verify_token(token):
        await start_bot(token)
        request.session["bot_token"] = token
        return RedirectResponse(url="/chats", status_code=status.HTTP_302_FOUND)
    
    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": "Invalid bot token"
    })

@app.get("/logout")
async def logout(request: Request):
    global bot_instance, bot_thread
    if bot_instance:
        await bot_instance.stop()
    if bot_thread:
        bot_thread.join(timeout=5)
    
    request.session.clear()
    return RedirectResponse(url="/login")

@app.get("/chats", response_class=HTMLResponse)
async def chats(request: Request, auth: bool = Depends(require_auth)):
    # Добавим задержку для тестирования
    import time
    time.sleep(0.5)
    
    chats = await Chat.all().order_by("-updated")
    return templates.TemplateResponse("chats.html", {
        "request": request,
        "chats": chats
    })

@app.get("/chat/{chat_id}", response_class=HTMLResponse)
async def chat_get(request: Request, chat_id: int, auth: bool = Depends(require_auth)):
    messages = await Message.filter(chat_id=chat_id).order_by("timestamp")
    chat = await Chat.get_or_none(id=chat_id)
    if chat:
        chat.unread = 0
        await chat.save()
    return templates.TemplateResponse("chat.html", {
        "request": request,
        "messages": messages,
        "chat": chat
    })

# ... (остальной код остается прежним)
import threading

# Глобальная блокировка для доступа к боту
bot_lock = threading.Lock()

import aiohttp
import asyncio

@app.post("/chat/{chat_id}")
async def chat_post(
    request: Request,
    chat_id: int,
    text: str = Form(...),
    auth: bool = Depends(require_auth)
):
    # Сохраняем исходящее сообщение в БД
    await Message.create(
        chat_id=chat_id,
        text=text,
        direction='outgoing'
    )
    logging.info(f"✅ Сообщение сохранено в БД: chat_id={chat_id}, text='{text}'")
    
    # Обновляем информацию о чате
    chat = await Chat.get_or_none(id=chat_id)
    if chat:
        chat.last_message = text
        chat.unread = 0
        await chat.save()
        logging.info(f"✅ Информация чата обновлена")
    
    # Отправляем сообщение через Telegram API с использованием aiohttp
    token = request.session.get("bot_token")
    if token:
        try:
            api_url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": text
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(api_url, json=payload) as response:
                    result = await response.json()
                    
                    if result.get('ok'):
                        logging.info("✅ Сообщение успешно отправлено через Telegram API")
                    else:
                        error_msg = result.get('description', 'Неизвестная ошибка')
                        logging.error(f"❌ Ошибка Telegram API: {error_msg}")
        except Exception as e:
            logging.error(f"🔥 Ошибка при отправке запроса к Telegram API: {e}")
    else:
        logging.error("❌ Токен бота отсутствует в сессии")
    
    return RedirectResponse(url=f"/chat/{chat_id}", status_code=status.HTTP_302_FOUND)