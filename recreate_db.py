# recreate_db.py
from tortoise import Tortoise, run_async
from models import Bot, Message, Chat

TORTOISE_CONFIG = {
    "connections": {"default": "sqlite://db.sqlite3"},
    "apps": {
        "models": {
            "models": ["main"],
            "default_connection": "default",
        }
    },
}

async def recreate_schema():
    await Tortoise.init(config=TORTOISE_CONFIG)
    await Tortoise.generate_schemas(safe=False)
    print("Database schema recreated")
    
    # Проверяем создание таблиц
    print("Tables created:")
    for model in [Bot, Message, Chat]:
        print(f"- {model.name}")

if __name__ == "__main__":
    run_async(recreate_schema())