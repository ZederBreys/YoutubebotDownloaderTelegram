import asyncio
import html
import os
import traceback

from aiogram import Bot, types
from yt_dlp import YoutubeDL

from settings import ADMINS_ID


def is_admin(user_id: int | None) -> bool:
    return user_id is not None and user_id in ADMINS_ID


def format_admin_error(exc: Exception, *, context: str | None = None) -> str:
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))

    parts = [
        "<b>Ошибка (admin)</b>",
        f"<code>{html.escape(type(exc).__name__)}: {html.escape(str(exc))}</code>",
    ]
    if context:
        parts.append(f"\n{html.escape(context)}")
    parts.append(f"\n<pre>{html.escape(tb[-3000:])}</pre>")
    text = "\n".join(parts)
    return text[:4096]


async def notify_admin_error(
    bot: Bot,
    user_id: int | None,
    exc: Exception,
    *,
    context: str | None = None,
) -> None:
    if not is_admin(user_id):
        return
    await bot.send_message(
        chat_id=user_id,
        text=format_admin_error(exc, context=context),
        parse_mode="HTML",
        disable_web_page_preview=True
    )

def format_duration(duration_in_seconds):
    if duration_in_seconds is None:
        return "Неизвестно"
    
    hours = duration_in_seconds // 3600
    minutes = (duration_in_seconds % 3600) // 60
    seconds = duration_in_seconds % 60
    
    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    elif minutes > 0:
        return f"{minutes}:{seconds:02d}"
    else:
        return f"00:{seconds:02d}"

async def AutoDelTime(msg : types.Message, timesleep : int = 5):
    # на всякий случай проверяем есть ли еще сообщение
    try:
        await asyncio.sleep(timesleep)
        await msg.delete()
    except Exception:
        pass

def find_file_by_name(directory : str, filename : str):
    for file in os.listdir(directory):
        if filename in file:
            return os.path.join(directory, file)
        
def format_number_with_spaces(number):
    return f"{number:,}".replace(",", " ")

def _format_number(value):
    return f"{value:,}".replace(",", " ") if value is not None else "Скрыто"

def _format_date(upload_date):
    if not upload_date or len(upload_date) != 8:
        return "Неизвестно"
    return f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}"

def get_youtube_info(url: str) -> dict | None:


    ydl_opts = {
        'quiet': True,
        'skip_download': True,
        'no_warnings': True,
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception:
        return None

    # Нормализация данных (всё сразу приводим к безопасному виду)
    return {
        "title": info.get('title') or "Без названия",
        "views": _format_number(info.get('view_count')),
        "likes": _format_number(info.get('like_count')),
        "upload_date": _format_date(info.get('upload_date')),
        "channel": info.get('uploader') or "Неизвестно",
        "duration": format_duration(info.get('duration')),
        "duration_seconds": info.get('duration'),
        "thumbnail": info.get('thumbnail')
    }
