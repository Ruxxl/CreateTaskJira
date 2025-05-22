import asyncio
import aiohttp
import ssl
import re
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

# === Конфигурация ===
BOT_TOKEN = '7440372138:AAHIcrjUjo0lXixcSRLWJedMg229pHg6h08'
JIRA_EMAIL = 'ruslan.issin@mechta.kz'
JIRA_API_TOKEN = 'токен с джири взять'
JIRA_PROJECT_KEY = 'AS'
JIRA_PARENT_KEY = 'AS-1679'
JIRA_URL = 'https://mechtamarket.atlassian.net'

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
TRIGGER_TAGS = ['#bug', '#jira']

# === Очистка summary от тегов ===
def clean_summary(text: str, tags: list[str]) -> str:
    for tag in tags:
        text = re.sub(re.escape(tag), '', text, flags=re.IGNORECASE)
    return ' '.join(text.split()).strip()

# === Обработка сообщений с фото ===
@dp.message(F.photo)
async def handle_photo(message: Message):
    if message.caption and any(tag in message.caption.lower() for tag in TRIGGER_TAGS):
        await message.reply("🔄 Обнаружен тег и фото, создаю задачу в Jira...")

        file_id = message.photo[-1].file_id
        file = await bot.get_file(file_id)
        file_path = file.file_path
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"

        # ⛔️ Отключаем SSL-проверку (временно!)
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        async with aiohttp.ClientSession() as session:
            async with session.get(file_url, ssl=ssl_context) as photo_response:
                if photo_response.status == 200:
                    photo_bytes = await photo_response.read()
                    success = await create_jira_ticket(
                        message.caption,
                        message.from_user.full_name,
                        photo_bytes,
                        filename="telegram_photo.jpg"
                    )
                    if success:
                        await message.reply("✅ Задача с фото успешно создана!")
                    else:
                        await message.reply("❌ Ошибка при создании задачи в Jira.")
                else:
                    await message.reply("❌ Не удалось скачать фото с Telegram.")

# === Создание задачи в Jira ===
async def create_jira_ticket(text: str, author: str, file_bytes: bytes, filename: str) -> bool:
    auth = aiohttp.BasicAuth(JIRA_EMAIL, JIRA_API_TOKEN)
    cleaned_text = clean_summary(text, TRIGGER_TAGS)
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    # 1. Создаём задачу
    create_url = f"{JIRA_URL}/rest/api/3/issue"
    headers = {"Content-Type": "application/json"}
    payload = {
        "fields": {
            "project": {"key": JIRA_PROJECT_KEY},
            "parent": {"key": JIRA_PARENT_KEY},
            "summary": cleaned_text[:255],
            "description": {
                "type": "doc",
                "version": 1,
                "content": [
                    {"type": "paragraph", "content": [{"type": "text", "text": text}]}
                ]
            },
            "issuetype": {"name": "Подзадача"}
        }
    }

    async with aiohttp.ClientSession(auth=auth) as session:
        async with session.post(create_url, json=payload, headers=headers, ssl=ssl_context) as response:
            if response.status != 201:
                error = await response.text()
                print(f"❌ Ошибка при создании задачи: {response.status} — {error}")
                return False

            result = await response.json()
            issue_key = result["key"]
            print(f"✅ Задача {issue_key} создана")

        # 2. Загружаем вложение
        attach_url = f"{JIRA_URL}/rest/api/3/issue/{issue_key}/attachments"
        attach_headers = {
            "X-Atlassian-Token": "no-check"
        }

        data = aiohttp.FormData()
        data.add_field('file', file_bytes, filename=filename, content_type='image/jpeg')

        async with session.post(attach_url, data=data, headers=attach_headers, ssl=ssl_context) as attach_response:
            if attach_response.status == 200 or attach_response.status == 201:
                print(f"📎 Фото прикреплено к задаче {issue_key}")
                return True
            else:
                error = await attach_response.text()
                print(f"❌ Ошибка при добавлении вложения: {attach_response.status} — {error}")
                return False

# === Запуск бота ===
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
