import asyncio
import logging
import os
import re
from random import randint

import yt_dlp
from aiogram import Bot, Dispatcher, types, F
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv

import database
from changelog import get_changelog_pages
from media_convert import (
    FFmpegNotFoundError,
    MediaConvertError,
    VNOTE_SIZE,
    convert_to_video_note,
    convert_to_voice,
    safe_remove,
)
from utils import AutoDelTime, find_file_by_name, get_youtube_info, notify_admin_error
from video_size import get_video_info

VNOTE_MAX_SECONDS = 59
VOICE_MAX_SECONDS = 9 * 60 + 55
VNOTE_RESOLUTIONS = ("360p", "720p")

# Configure logging
logging.basicConfig(level=logging.INFO)

load_dotenv()

TELEGRAM_API_BASE = os.getenv("TELEGRAM_API_BASE", "http://localhost:8081")
local_server = TelegramAPIServer.from_base(TELEGRAM_API_BASE)
session = AiohttpSession(api=local_server)

# Initialize bot and dispatcher под aiogram 3.x
bot = Bot(
    token=os.getenv('BOT_TOKEN'), 
    session=session,
    default=DefaultBotProperties(parse_mode="HTML")
)
dp = Dispatcher()


def _changelog_keyboard(page: int, total: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if page > 0:
        builder.add(InlineKeyboardButton(text="◀️", callback_data=f"changelog_page__{page - 1}"))
    builder.add(InlineKeyboardButton(text=f"{page + 1}/{total}", callback_data="changelog_nop"))
    if page < total - 1:
        builder.add(InlineKeyboardButton(text="▶️", callback_data=f"changelog_page__{page + 1}"))
    builder.adjust(3)
    return builder.as_markup()


def _vnote_resolutions(buttons: dict) -> list[str]:
    return [res for res in VNOTE_RESOLUTIONS if res in buttons]


def _add_extra_format_buttons(
    keyboard: InlineKeyboardMarkup,
    buttons: dict,
    youtube_id: str,
    duration_seconds: int | None,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder.from_markup(keyboard)
    
    if duration_seconds is not None and duration_seconds <= VNOTE_MAX_SECONDS:
        if _vnote_resolutions(buttons):
            builder.row(
                InlineKeyboardButton(text="⭕ Отправь как кружок", callback_data=f"vnote_menu__{youtube_id}")
            )

    if (
        duration_seconds is not None
        and duration_seconds <= VOICE_MAX_SECONDS
        and "audio" in buttons
    ):
        audio_format_id = buttons["audio"]["format_id"]
        builder.row(
            InlineKeyboardButton(
                text="🎤 Отправить как голосовое",
                callback_data=f"voice__{audio_format_id}__{youtube_id}",
            )
        )
    return builder.as_markup()


@dp.message(CommandStart())
async def send_welcome(message: types.Message):
    await message.answer(
        text=(
            "Бот для скачивания видео и аудио с YouTube в любом качестве:\n"
            "- Бесплатно\n"
            "- Без подписок на каналы \n\n"
            "<b>Для начала работы просто отправь мне ссылку на видео.</b>\n\n"
            "Доп. информация — /info\n"
            "История обновлений — /changelog"
        )
    )


@dp.message(Command('info'))
async def send_info(message: types.Message):
    await message.answer(
        text=(
            "<b>Часто задаваемые вопросы:</b>\n\n"
            "<b>Что означает эмодзи ракеты 🚀</b> — Этот значок указывает, что видео уже было "
            "загружено пользователем и сохранено ботом. Поэтому мы можем отправить его вам "
            "мгновенно, без ожидания повторного получения с YouTube и загрузки на сервера Telegram.\n\n"
            "----------------\n\n"
            "Дата последнего обновления бота: 23.05.2026\n"
            "История обновлений: /changelog\n"
            "<b>Разработчик: @ZederBreys</b>"
        )
    )


@dp.message(Command('changelog'))
async def send_changelog(message: types.Message):
    pages = get_changelog_pages()
    if not pages:
        return await message.reply("История обновлений пока недоступна.")

    keyboard = _changelog_keyboard(0, len(pages)) if len(pages) > 1 else None
    await message.reply(pages[0], reply_markup=keyboard)


@dp.callback_query(F.data.startswith("changelog_page__"))
async def changelog_page(callback_query: types.CallbackQuery):
    page = int(callback_query.data.split("__")[1])
    pages = get_changelog_pages()
    if not pages:
        return await callback_query.answer("История обновлений недоступна.", show_alert=True)

    page = max(0, min(page, len(pages) - 1))
    keyboard = _changelog_keyboard(page, len(pages)) if len(pages) > 1 else None
    
    # В aiogram 3 редактируем текст через callback_query.message.edit_text
    await callback_query.message.edit_text(
        text=pages[page],
        reply_markup=keyboard
    )
    await callback_query.answer()


@dp.callback_query(F.data == "changelog_nop")
async def changelog_nop(callback_query: types.CallbackQuery):
    await callback_query.answer()


@dp.message(F.text.regexp(r'^https?://(?:www\.)?youtube\.com/(?:watch\?v=|embed/|v/|shorts/|playlist\?list=)[\w-]+|^https?://youtu\.be/[\w-]+'))
async def process_youtube_url(message: types.Message):
    url = message.text

    if re.search(r'list=[^&]+', url):
        return await message.reply("Ссылки на стримы или плейлисты не обрабатываются.")

    temp_msg = await message.reply("Получаю информацию...")

    try:
        data = await asyncio.to_thread(get_youtube_info, url)

        if not data:
            return await temp_msg.edit_text(text="❌ Не удалось получить информацию о видео.")

        builder = InlineKeyboardBuilder()
        youtube_id, buttons, duration_seconds = await asyncio.to_thread(get_video_info, url)
        if str(youtube_id) == "streaming":
            return await temp_msg.edit_text("Ссылки на стримы или плейлисты не обрабатываются.")

        format_ids = [button_info["format_id"] for button_info in buttons.values()]
        available_resolutions = database.get_cache_resolution(youtube_id, format_ids)
        duration_seconds = duration_seconds or data.get("duration_seconds")

        text = (
            f"<b>{data['title']}</b>\n\n"
            f"👤 Канал: {data['channel']}\n"
            f"👁 Просмотры: {data['views']}\n"
            f"👍 Лайки: {data['likes']}\n"
            f"📅 Дата: {data['upload_date']}\n"
            f"⏱ Длительность: {data['duration']}"
        )

        for button in buttons:
            if button == "audio":
                continue
            i = buttons[f"{button}"]
            size = float(i['filesize_mb'])
            format_id = i['format_id']
            energy_icon = "🚀" if format_id in available_resolutions else ""

            if size > 1800:
                builder.row(InlineKeyboardButton(text=f"❌ {button} - {size:.2f} MB", callback_data="too_large"))
            else:
                builder.row(
                    InlineKeyboardButton(
                        text=f"{energy_icon}📺 {button} - {size:.2f} MB",
                        callback_data=f"download__{format_id}__{youtube_id}",
                    )
                )

        if "audio" in buttons:
            audio_info = buttons["audio"]
            audio_size = float(audio_info['filesize_mb'])
            audio_format_id = audio_info['format_id']
            audio_energy_icon = "🚀" if audio_format_id in available_resolutions else ""

            if audio_size > 1800:
                builder.row(InlineKeyboardButton(text=f"❌ audio - {audio_size:.2f} MB", callback_data="too_large"))
            else:
                builder.row(
                    InlineKeyboardButton(
                        text=f"{audio_energy_icon}🔊 audio - {audio_size:.2f} MB",
                        callback_data=f"audio__{audio_format_id}__{youtube_id}",
                    )
                )

        keyboard = builder.as_markup()
        keyboard = _add_extra_format_buttons(keyboard, buttons, youtube_id, duration_seconds)

        await AutoDelTime(temp_msg, 0)
        await message.answer_photo(
            photo=data["thumbnail"],
            caption=text,
            reply_markup=keyboard
        )
    except Exception as e:
        logging.exception("process_youtube_url failed for url=%s", url)
        await notify_admin_error(
            bot,
            message.from_user.id,
            e,
            context=f"handler=process_youtube_url\nurl={url}",
        )

        error_msg = str(e).lower()
        if "video unavailable" in error_msg or "private" in error_msg or "removed" in error_msg:
            await temp_msg.edit_text(text="❌ Данное видео не существует или недоступно для просмотра")
        elif "age restriction" in error_msg:
            await temp_msg.edit_text(text="❌ Видео имеет возрастное ограничение и не может быть загружено")
        else:
            await temp_msg.edit_text(text="❌ Ошибка при загрузке видео")


@dp.callback_query(F.data.startswith("vnote_menu__"))
async def vnote_quality_menu(callback_query: types.CallbackQuery):
    youtube_id = callback_query.data.split("__")[1]
    url = f"https://www.youtube.com/watch?v={youtube_id}"

    try:
        _, buttons, duration_seconds = await asyncio.to_thread(get_video_info, url)
    except Exception as e:
        logging.exception("vnote_quality_menu failed for youtube_id=%s", youtube_id)
        await notify_admin_error(
            bot,
            callback_query.from_user.id,
            e,
            context=f"handler=vnote_quality_menu\nurl={url}",
        )
        return await callback_query.answer("Не удалось получить список качеств.", show_alert=True)

    if duration_seconds is not None and duration_seconds > VNOTE_MAX_SECONDS:
        return await callback_query.answer(
            "Видео длиннее 59 секунд — кружок недоступен.",
            show_alert=True,
        )

    resolutions = _vnote_resolutions(buttons)
    if not resolutions:
        return await callback_query.answer("Нет подходящего качества для кружка.", show_alert=True)

    builder = InlineKeyboardBuilder()
    for resolution in resolutions:
        format_id = buttons[resolution]["format_id"]
        size = float(buttons[resolution]["filesize_mb"])
        builder.row(
            InlineKeyboardButton(
                text=f"📺 {resolution} — {size:.2f} MB",
                callback_data=f"vnote__{format_id}__{youtube_id}",
            )
        )

    await callback_query.message.reply(
        text="Выберите качество для отправки кружком (до включительно 720p):",
        reply_markup=builder.as_markup(),
    )
    await callback_query.answer()


@dp.callback_query(F.data.startswith('download__'))
async def process_download(callback_query: types.CallbackQuery):
    temp_msg = await bot.send_message(chat_id=callback_query.from_user.id, text="Скачиваю видео...")
    format_id = callback_query.data.split('__')[1]
    youtube_id = callback_query.data.split('__')[2]
    url = f"https://www.youtube.com/watch?v={youtube_id}"

    cache_video = await asyncio.to_thread(database.check_record_exists, youtube_id, format_id)
    if cache_video:
        await bot.send_video(chat_id=callback_query.from_user.id, video=cache_video)
        await AutoDelTime(temp_msg, 0)
    else:
        random_name = randint(1, 9999999)
        ydl_opts = {
            'format': f"{format_id}+worstaudio/worst",
            'outtmpl': 'downloads/{0}.%(ext)s'.format(random_name),
        }

        try:
            media_path = await _download_media(url, ydl_opts, random_name)
        except Exception as e:
            logging.exception("video download failed for youtube_id=%s", youtube_id)
            await notify_admin_error(
                bot,
                callback_query.from_user.id,
                e,
                context=f"handler=process_download\nurl={url}\nformat_id={format_id}",
            )
            return await temp_msg.edit_text(text="Не удалось скачать это видео. Попробуйте загрузить другое.")

        await temp_msg.edit_text(text="Отправляю видео..")
        if not media_path:
            return await temp_msg.edit_text(text="Не удалось подготовить видеофайл для отправки.")

        # Использование FSInputFile для отправки файлов по пути
        data_video = await bot.send_video(
            chat_id=callback_query.from_user.id,
            video=FSInputFile(media_path),
        )
        await AutoDelTime(temp_msg, 0)
        safe_remove(media_path)
        await asyncio.to_thread(
            database.create_record_if_not_exists,
            youtube_id,
            format_id,
            data_video.video.file_id,
        )


@dp.callback_query(lambda c: c.data.startswith('vnote__') and not c.data.startswith('vnote_menu__'))
async def process_video_note(callback_query: types.CallbackQuery):
    temp_msg = await bot.send_message(chat_id=callback_query.from_user.id, text="Готовлю кружок...")
    format_id = callback_query.data.split('__')[1]
    youtube_id = callback_query.data.split('__')[2]
    url = f"https://www.youtube.com/watch?v={youtube_id}"

    try:
        _, _, duration_seconds = await asyncio.to_thread(get_video_info, url)
    except Exception as e:
        logging.exception("process_video_note info failed for youtube_id=%s", youtube_id)
        await notify_admin_error(
            bot,
            callback_query.from_user.id,
            e,
            context=f"handler=process_video_note\nurl={url}",
        )
        return await temp_msg.edit_text(text="Не удалось проверить длительность видео.")

    if duration_seconds is not None and duration_seconds > VNOTE_MAX_SECONDS:
        return await temp_msg.edit_text(text="Видео длиннее 59 секунд — кружок недоступен.")

    random_name = randint(1, 9999999)
    ydl_opts = {
        'format': f"{format_id}+worstaudio/worst",
        'outtmpl': 'downloads/{0}.%(ext)s'.format(random_name),
        'merge_output_format': 'mp4',
    }

    try:
        media_path = await _download_media(url, ydl_opts, random_name)
    except Exception as e:
        logging.exception("video note download failed for youtube_id=%s", youtube_id)
        await notify_admin_error(
            bot,
            callback_query.from_user.id,
            e,
            context=f"handler=process_video_note\nurl={url}\nformat_id={format_id}",
        )
        return await temp_msg.edit_text(text="Не удалось подготовить кружок. Попробуйте другое качество.")

    if not media_path:
        return await temp_msg.edit_text(text="Не удалось подготовить файл для кружка.")

    converted_path = None
    try:
        await bot.send_chat_action(chat_id=callback_query.from_user.id, action="record_video_note")
        await temp_msg.edit_text(text="Превращаю видео в кружок...")

        try:
            converted_path = await asyncio.to_thread(convert_to_video_note, media_path)
        except FFmpegNotFoundError:
            return await temp_msg.edit_text(
                text="Для кружков нужен ffmpeg. Установите его на сервер и добавьте в PATH."
            )
        except MediaConvertError:
            return await temp_msg.edit_text(
                text="Не удалось подготовить кружок. Попробуйте другое качество."
            )
        finally:
            safe_remove(media_path)

        final_duration = min(
            int(duration_seconds or VNOTE_MAX_SECONDS),
            VNOTE_MAX_SECONDS,
        )

        await temp_msg.edit_text(text="Отправляю кружок...")
        await bot.send_video_note(
            chat_id=callback_query.from_user.id,
            video_note=FSInputFile(converted_path),
            duration=final_duration,
            length=VNOTE_SIZE,
        )
    except Exception as e:
        logging.exception("send video note failed for youtube_id=%s", youtube_id)
        await notify_admin_error(
            bot,
            callback_query.from_user.id,
            e,
            context=f"handler=process_video_note send\nurl={url}",
        )
        await temp_msg.edit_text(text="Не удалось отправить кружок.")
    finally:
        safe_remove(converted_path)

    await AutoDelTime(temp_msg, 0)


@dp.callback_query(F.data.startswith('audio__'))
async def process_download_audio(callback_query: types.CallbackQuery):
    temp_msg = await bot.send_message(chat_id=callback_query.from_user.id, text="Скачиваю аудио...")
    format_id = callback_query.data.split('__')[1]
    youtube_id = callback_query.data.split('__')[2]
    url = f"https://www.youtube.com/watch?v={youtube_id}"

    cache_audio = await asyncio.to_thread(database.check_record_exists, youtube_id, format_id)
    if cache_audio:
        await bot.send_audio(chat_id=callback_query.from_user.id, audio=cache_audio)
        await AutoDelTime(temp_msg, 0)
    else:
        random_name = randint(1, 9999999)
        ydl_opts = {
            'format': "worstaudio[ext=mp3]+worstaudio[ext=m4a]/worst[ext=mp3]/worst",
            'outtmpl': 'downloads/{0}.%(ext)s'.format(random_name),
        }

        try:
            media_path = await _download_media(url, ydl_opts, random_name)
        except Exception as e:
            logging.exception("audio download failed for youtube_id=%s", youtube_id)
            await notify_admin_error(
                bot,
                callback_query.from_user.id,
                e,
                context=f"handler=process_download_audio\nurl={url}\nformat_id={format_id}",
            )
            return await temp_msg.edit_text(text="Не удалось скачать это видео. Попробуйте загрузить другое.")

        await temp_msg.edit_text(text="Отправляю аудио..")
        if not media_path:
            return await temp_msg.edit_text(text="Не удалось подготовить аудиофайл для отправки.")

        data_audio = await bot.send_audio(
            chat_id=callback_query.from_user.id,
            audio=FSInputFile(media_path),
        )
        await AutoDelTime(temp_msg, 0)
        safe_remove(media_path)
        await asyncio.to_thread(
            database.create_record_if_not_exists,
            youtube_id,
            format_id,
            data_audio.audio.file_id,
        )


@dp.callback_query(F.data.startswith('voice__'))
async def process_voice_message(callback_query: types.CallbackQuery):
    temp_msg = await bot.send_message(chat_id=callback_query.from_user.id, text="Готовлю голосовое...")
    format_id = callback_query.data.split('__')[1]
    youtube_id = callback_query.data.split('__')[2]
    url = f"https://www.youtube.com/watch?v={youtube_id}"

    try:
        data = await asyncio.to_thread(get_youtube_info, url)
    except Exception as e:
        logging.exception("process_voice_message info failed for youtube_id=%s", youtube_id)
        await notify_admin_error(
            bot,
            callback_query.from_user.id,
            e,
            context=f"handler=process_voice_message\nurl={url}",
        )
        return await temp_msg.edit_text(text="Не удалось проверить длительность видео.")

    duration_seconds = data.get("duration_seconds") if data else None
    if duration_seconds is not None and duration_seconds > VOICE_MAX_SECONDS:
        return await temp_msg.edit_text(
            text="Видео длиннее 9 минут 55 секунд — голосовое сообщение недоступно."
        )

    random_name = randint(1, 9999999)
    ydl_opts = {
        'format': "worstaudio[ext=mp3]+worstaudio[ext=m4a]/worst[ext=mp3]/worst",
        'outtmpl': 'downloads/{0}.%(ext)s'.format(random_name),
    }

    try:
        media_path = await _download_media(url, ydl_opts, random_name)
    except Exception as e:
        logging.exception("voice download failed for youtube_id=%s", youtube_id)
        await notify_admin_error(
            bot,
            callback_query.from_user.id,
            e,
            context=f"handler=process_voice_message\nurl={url}\nformat_id={format_id}",
        )
        return await temp_msg.edit_text(text="Не удалось подготовить голосовое сообщение.")

    if not media_path:
        media_path = find_file_by_name("./downloads/", str(random_name))
    if not media_path:
        return await temp_msg.edit_text(text="Не удалось подготовить аудиофайл.")

    converted_path = None
    try:
        await bot.send_chat_action(chat_id=callback_query.from_user.id, action="record_voice")
        await temp_msg.edit_text(text="Конвертирую голосовое...")

        try:
            converted_path = await asyncio.to_thread(
                convert_to_voice,
                media_path,
                int(duration_seconds) if duration_seconds else VOICE_MAX_SECONDS,
            )
        except FFmpegNotFoundError:
            return await temp_msg.edit_text(
                text="Для голосовых нужен ffmpeg. Установите его на сервер и добавьте в PATH."
            )
        except MediaConvertError:
            return await temp_msg.edit_text(text="Не удалось подготовить голосовое сообщение.")
        finally:
            safe_remove(media_path)

        voice_duration = int(duration_seconds) if duration_seconds else None
        if voice_duration is not None:
            voice_duration = min(voice_duration, VOICE_MAX_SECONDS)

        await temp_msg.edit_text(text="Отправляю голосовое...")
        await bot.send_voice(
            chat_id=callback_query.from_user.id,
            voice=FSInputFile(converted_path),
            duration=voice_duration,
        )
    except Exception as e:
        logging.exception("send voice failed for youtube_id=%s", youtube_id)
        await notify_admin_error(
            bot,
            callback_query.from_user.id,
            e,
            context=f"handler=process_voice_message send\nurl={url}",
        )
        await temp_msg.edit_text(text="Не удалось отправить голосовое сообщение.")
    finally:
        safe_remove(converted_path)

    await AutoDelTime(temp_msg, 0)


@dp.callback_query(F.data == 'too_large')
async def process_too_large(callback_query: types.CallbackQuery):
    await callback_query.answer(
        text="Файл слишком большой для отправки через Telegram",
    )


# В aiogram 3 ошибки перехватываются через dp.errors.register или декоратор dp.errors()
@dp.errors()
async def global_errors_handler(exception_wrapper: types.ErrorEvent):
    update = exception_wrapper.update
    exception = exception_wrapper.exception
    
    logging.exception("Unhandled error in update=%s", update)
    user_id = None
    if update.message:
        user_id = update.message.from_user.id
    elif update.callback_query:
        user_id = update.callback_query.from_user.id

    await notify_admin_error(
        bot,
        user_id,
        exception,
        context=f"handler=global_errors_handler\nupdate={update!r}",
    )
    return True


async def _download_media(url: str, ydl_opts: dict, random_name: int) -> str | None:
    os.makedirs("downloads", exist_ok=True)
    await asyncio.to_thread(_download_with_yt_dlp, ydl_opts, url)
    return find_file_by_name("./downloads/", str(random_name))


def _download_with_yt_dlp(ydl_opts: dict, url: str) -> None:
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])


# Асинхронная точка входа для aiogram 3.x
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped!")