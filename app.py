from flask import Flask, render_template, request, redirect, session, url_for
from sqlalchemy.orm import sessionmaker
from models import Base, Message, Chat, engine
from bot import TelegramBot
import asyncio
from threading import Thread
import logging

# Инициализация Flask приложения
app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Замените на случайный ключ для продакшена
app.jinja_env.add_extension('jinja2.ext.loopcontrols')

# Настройка SQLAlchemy
Session = sessionmaker(bind=engine)

# Глобальные переменные для управления ботом
telegram_bot = None
bot_thread = None

# Функция для запуска бота в отдельном потоке
def run_bot(token):
    global telegram_bot
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        telegram_bot = TelegramBot(token, Session)
        loop.run_until_complete(telegram_bot.start())
    except Exception as e:
        logging.error(f"Bot error: {e}")

# Маршрут для входа
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        token = request.form['token']
        try:
            # Проверка токена
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            test_bot = TelegramBot(token, Session)
            loop.run_until_complete(test_bot.bot.get_me())
            
            # Останавливаем предыдущий бот, если он был запущен
            global bot_thread, telegram_bot
            if bot_thread and bot_thread.is_alive():
                loop.run_until_complete(telegram_bot.stop())
            
            # Запускаем новый бот в отдельном потоке
            bot_thread = Thread(target=run_bot, args=(token,), daemon=True)
            bot_thread.start()
            
            session['bot_token'] = token
            return redirect(url_for('chats'))
        except Exception as e:
            return render_template('login.html', error="Неверный токен бота")
    
    return render_template('login.html')

# Маршрут для выхода
@app.route('/logout')
def logout():
    global bot_thread, telegram_bot
    if bot_thread and bot_thread.is_alive():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(telegram_bot.stop())
    
    session.clear()
    return redirect(url_for('login'))

# Маршрут для отображения списка чатов
@app.route('/chats')
def chats():
    if 'bot_token' not in session:
        return redirect(url_for('login'))
    
    db_session = Session()
    try:
        chats = db_session.query(Chat).order_by(Chat.updated.desc()).all()
        return render_template('chats.html', chats=chats)
    finally:
        db_session.close()

# Маршрут для отображения и отправки сообщений в конкретном чате
@app.route('/chat/<int:chat_id>', methods=['GET', 'POST'])
async def chat(chat_id):
    if 'bot_token' not in session:
        return redirect(url_for('login'))
    
    db_session = Session()
    try:
        if request.method == 'POST':
            if 'text' in request.form:
                text = request.form['text']
                msg = Message(
                    chat_id=chat_id,
                    text=text,
                    direction='outgoing'
                )
                db_session.add(msg)
                
                chat = db_session.get(Chat, chat_id)
                if chat:
                    chat.last_message = text
                    chat.unread = 0
                
                db_session.commit()
                
                # Отправляем сообщение через Telegram API
                bot = TelegramBot(session['bot_token'], Session)
                await bot.bot.send_message(chat_id=chat_id, text=text)
            
            return redirect(url_for('chat', chat_id=chat_id))
        
        # Получаем сообщения и информацию о чате
        messages = db_session.query(Message).filter_by(chat_id=chat_id).order_by(Message.timestamp).all()
        chat = db_session.get(Chat, chat_id)
        
        if chat:
            chat.unread = 0
            db_session.commit()
        
        return render_template('chat.html', messages=messages, chat=chat)
    finally:
        db_session.close()

# Запуск приложения
if __name__ == '__main__':
    # Создание таблиц в базе данных, если они не существуют
    Base.metadata.create_all(engine)
    
    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Запуск Flask приложения
    app.run(debug=True)