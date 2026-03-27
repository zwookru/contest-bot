"""
Бот для приёма треков на конкурс.
Сидит в группе, ждёт когда юзер напишет свой user_id и отправит файл.
Сохраняет всё в Google Sheets.

Установка:
    pip install aiogram gspread google-auth

Переменные окружения в Railway:
    BOT_TOKEN=токен_от_BotFather
    GOOGLE_SHEET_ID=id_таблицы_из_ссылки
    GOOGLE_CREDS_JSON=содержимое_creds.json_одной_строкой
"""

import asyncio
import json
import logging
import os
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Google Sheets ────────────────────────────────────────────────────────────

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

def get_sheet():
    # Читаем credentials из переменной окружения (не из файла)
    creds_json = os.getenv("GOOGLE_CREDS_JSON")
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(os.getenv("GOOGLE_SHEET_ID")).sheet1

    # Создаём шапку если таблица пустая
    if not sheet.row_values(1):
        sheet.append_row([
            "Дата",
            "BotHelp user_id",
            "TG Username отправителя",
            "Имя файла",
            "file_id",
        ])
    return sheet


# ── Хранилище ожидающих юзеров ───────────────────────────────────────────────
# Когда юзер пишет текст с user_id — запоминаем его telegram_id → bothelp_user_id
# Когда от него приходит файл — достаём и записываем в таблицу

pending: dict[int, str] = {}  # { telegram_user_id: bothelp_user_id }


# ── Хэндлеры ────────────────────────────────────────────────────────────────

async def handle_user_id(message: Message):
    """Юзер написал свой BotHelp user_id текстом."""
    text = message.text.strip()

    # Принимаем только числа (user_id всегда числовой)
    if not text.isdigit():
        return

    pending[message.from_user.id] = text
    await message.reply(
        f"✅ ID {text} запомнен.\nТеперь отправь свой трек в формате WAV или MP3."
    )
    logger.info(f"Получен user_id {text} от @{message.from_user.username}")


async def handle_file(message: Message):
    """Юзер отправил аудио или документ."""
    sender_id = message.from_user.id

    # Получаем объект файла (audio или document)
    file_obj = message.audio or message.document
    if not file_obj:
        return

    file_name = getattr(file_obj, "file_name", None) or "unknown"
    file_id   = file_obj.file_id

    # Проверяем что юзер до этого прислал свой BotHelp user_id
    bothelp_uid = pending.get(sender_id)
    if not bothelp_uid:
        await message.reply(
            "⚠️ Сначала напиши свой ID из бота, потом отправляй файл."
        )
        return

    username = f"@{message.from_user.username}" if message.from_user.username else str(sender_id)

    # Пишем строку в Google Sheets
    try:
        sheet = get_sheet()
        sheet.append_row([
            datetime.now().strftime("%d.%m.%Y %H:%M"),
            bothelp_uid,
            username,
            file_name,
            file_id,
        ])
        logger.info(f"Сохранено: {bothelp_uid} | {username} | {file_name}")
    except Exception as e:
        logger.error(f"Ошибка записи в таблицу: {e}")
        await message.reply("❌ Ошибка сохранения, попробуй ещё раз.")
        return

    # Удаляем из ожидания (один юзер — один трек, если нужно несколько — убери эту строку)
    del pending[sender_id]

    await message.reply(
        f"🎵 Трек принят!\n"
        f"Файл: {file_name}\n"
        f"Удачи на конкурсе! 🏆"
    )


# ── Запуск ───────────────────────────────────────────────────────────────────

async def main():
    bot = Bot(token=os.getenv("BOT_TOKEN"))
    dp  = Dispatcher()

    # Текстовые сообщения — ловим числовой user_id
    dp.message.register(handle_user_id, F.text)

    # Файлы — аудио и документы
    dp.message.register(handle_file, F.audio | F.document)

    logger.info("Бот запущен, слушаю группу...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
