import os
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.types import InputFile
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.types import ChatMemberStatus
from aiogram.bot.api import TelegramAPIServer
from aiogram.utils import executor
from pytube import YouTube
from dotenv import load_dotenv
from video_size import get_video_info
from utils import *
from random import randint
import database
import yt_dlp, os, re


# Configure logging
logging.basicConfig(level=logging.INFO)

load_dotenv()

local_server = TelegramAPIServer.from_base('http://localhost:8081')

# Initialize bot and dispatcher
bot = Bot(token=os.getenv('BOT_TOKEN'), server=local_server)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())


@dp.message_handler(commands=['start'])
async def send_welcome(message: types.Message):
    await message.bot.send_message(chat_id=message.from_user.id, text=f"Бот для скачивания видео и аудио с YouTube в любом качестве:\n- Бесплатно\n- Без подписок на каналы \n\n<b>Для начала работы просто отправь мне ссылку на видео.</b>\n\nДоп. Информация /info", parse_mode="HTML")
@dp.message_handler(commands=['info'])
async def send_welcome(message: types.Message):
    await message.bot.send_message(chat_id=message.from_user.id, text=f"<b>Часто задаваемы вопросы:\n\nЧто означает эмодзи ракеты 🚀</b> — Этот значок указывает, что видео уже было загружено пользователем и сохранено ботом. Поэтому мы можем отправить его вам мгновенно, без ожидания повторного получения с YouTube и загрузки на сервера Telegram.\n\n----------------\n\nДата последнего обновления бота: 20.11.2024\n<b>Разработчик: @ZederBreys</b>", parse_mode="HTML")

@dp.message_handler(regexp='^https?://(?:www\.)?youtube\.com/(?:watch\?v=|embed/|v/|shorts/|playlist\?list=)[\w-]+|^https?://youtu\.be/[\w-]+')
async def process_youtube_url(message: types.Message):
    url = message.text

    pattern = r'list=[^&]+'

    match = re.search(pattern, url)
    if match:
        return await message.reply("Ссылки на стримы или плейлисты не обрабатываются.")

    temp_msg = await message.reply("Получаю информцию...")
    
    yt = YouTube(url)
    
    # Get video information
    title = yt.title
    views = yt.views
    likes = yt.rating
    upload_date = yt.publish_date.strftime('%Y-%m-%d')
    channel = yt.author
    duration = yt.length
    
    # Get thumbnail
    thumbnail_url = yt.thumbnail_url
    
    formatted_duration = format_duration(duration)
    # Prepare message
    views = format_number_with_spaces(views)
    text = f"<b>{title}</b>\n\n👁 Просмотров: {views} 👁\n 🖥️Дата загрузки видео: {upload_date}\n 🏧Канал: {channel}\n ⏸Длительность видео: {formatted_duration}"
    # Создание клавиатуры
    keyboard = InlineKeyboardMarkup(row_width=1)
    youtube_id, buttons = get_video_info(url=url)
    if str(youtube_id) == "streaming":
        return await temp_msg.edit_text("Ссылки на стримы или плейлисты не обрабатываются.")

    # Собираем все уникальные format_id из buttons
    format_ids = [button_info["format_id"] for button_info in buttons.values()]

    available_resolutions = database.get_cache_resolution(youtube_id, format_ids)

    # Добавление кнопок в клавиатуру
    for button in buttons:
        i = buttons[f"{button}"]
        size = float(i['filesize_mb'])
        format_id = i['format_id']

        # Проверяем, есть ли запись в базе данных для данного format_id
        energy_icon = "🚀" if int(format_id) in available_resolutions else ""

        # Проверка веса файла
        if size > 1800:
            if button != "audio":
                keyboard.add(InlineKeyboardButton(f"❌ {button} - {size:.2f} MB", callback_data="too_large"))
        else:
            print(f"🎥{button} / {format_id}")
            if button != "audio":
                keyboard.add(InlineKeyboardButton(f"{energy_icon}📺 {button} - {size:.2f} MB", callback_data=f"download__{format_id}__{youtube_id}"))
                
    # Добавляем кнопку audio в конец
    if "audio" in buttons:
        audio_info = buttons["audio"]
        audio_size = float(audio_info['filesize_mb'])
        audio_format_id = audio_info['format_id']

        # Проверяем, есть ли запись в базе данных для аудио format_id
        audio_energy_icon = "🚀" if int(audio_format_id) in available_resolutions else ""

        if audio_size > 1800:
            keyboard.add(InlineKeyboardButton(f"❌ audio - {audio_size:.2f} MB", callback_data="too_large"))
        else:
            keyboard.add(InlineKeyboardButton(f"{audio_energy_icon}🔊 audio - {audio_size:.2f} MB", callback_data=f"audio__{audio_format_id}__{youtube_id}"))

    # Send message with thumbnail
    await AutoDelTime(temp_msg, 0)
    await bot.send_photo(message.chat.id, photo=thumbnail_url, caption=text, reply_markup=keyboard, parse_mode="HTML")

@dp.callback_query_handler(lambda c: c.data.startswith('download__'))
async def process_download(callback_query: types.CallbackQuery):
    temp_msg = await bot.send_message(callback_query.from_user.id, "Скачиваю видео...")
    format_id = callback_query.data.split('__')[1]
    youtube_id = callback_query.data.split('__')[2]
    url = f"https://www.youtube.com/watch?v={youtube_id}"

    cache_video = database.check_record_exists(youtube_id, format_id)
    if cache_video:
        await bot.send_video(chat_id=callback_query.from_user.id, video=cache_video)
        await AutoDelTime(temp_msg, 0)
    else:
        random_name = randint(1, 9999999)
        # Download video
        ydl_opts = {
            'format': f"{format_id}+worstaudio/worst",
            'outtmpl': 'downloads/{0}.%(ext)s'.format(random_name),  # Указываем шаблон имени файла
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                ydl.download([url])
            except:
                return await temp_msg.edit_text("Не удалось скачать это видео. Попробуйте загрузить другое.")
        #Отправка видео пользвателю
        await temp_msg.edit_text("Отправляю видео..")
        video_path = find_file_by_name("./downloads/", str(random_name))


        with open(video_path, 'rb') as video_file:
            data_video = await bot.send_video(chat_id=callback_query.from_user.id, video=InputFile(video_file))
            await AutoDelTime(temp_msg, 0)
            os.remove(video_path)
            database.create_record_if_not_exists(youtube_id, format_id, data_video.video.file_id)

@dp.callback_query_handler(lambda c: c.data.startswith('audio__'))
async def process_download_audio(callback_query: types.CallbackQuery):
    temp_msg = await bot.send_message(callback_query.from_user.id, "Скачиваю аудио...")
    format_id = callback_query.data.split('__')[1]
    youtube_id = callback_query.data.split('__')[2]
    url = f"https://www.youtube.com/watch?v={youtube_id}"

    cache_audio = database.check_record_exists(youtube_id, format_id)
    if cache_audio:
        await bot.send_video(chat_id=callback_query.from_user.id, video=cache_audio)
        await AutoDelTime(temp_msg, 0)
    else:
        random_name = randint(1, 9999999)
        # Download video
        print(format_id)
        ydl_opts = {
            'format': f"worstaudio[ext=mp3]+worstaudio[ext=m4a]/worst[ext=mp3]/worst", #f"worstaudio/worst", 
            'outtmpl': 'downloads/{0}.%(ext)s'.format(random_name),  # Указываем шаблон имени файла
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                ydl.download([url])
            except:
                return await temp_msg.edit_text("Не удалось скачать это видео. Попробуйте загрузить другое.")
        #Отправка видео пользвателю
        await temp_msg.edit_text("Отправляю аудио..")
        video_path = find_file_by_name("./downloads/", str(random_name))

        with open(video_path, 'rb') as video_file:
            data_audio = await bot.send_audio(chat_id=callback_query.from_user.id, audio=InputFile(video_file))
            await AutoDelTime(temp_msg, 0)
            os.remove(video_path)
            database.create_record_if_not_exists(youtube_id, format_id, data_audio.audio.file_id)

@dp.callback_query_handler(lambda c: c.data == 'too_large')
async def process_too_large(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id, text="Файл слишком большой для отправки через Telegram")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)