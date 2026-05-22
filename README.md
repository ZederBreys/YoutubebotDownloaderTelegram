# YouTube Downloader Telegram Bot

Telegram-бот для скачивания видео и аудио с YouTube в выбранном качестве. Повторная отправка уже загруженных форматов выполняется мгновенно за счёт кэша `file_id` в PostgreSQL.

## Возможности

- Скачивание видео в качестве 360p, 720p, 1080p, 1440p, 2160p (если доступно на YouTube)
- Скачивание аудиодорожки
- Отправка видео как **кружок** (video note, до 59 сек, 360p/720p) — нужен [ffmpeg](https://ffmpeg.org/)
- Отправка аудио как **голосовое сообщение** (до ~9:55) — нужен ffmpeg
- Кэш в PostgreSQL: иконка 🚀 у формата означает, что файл уже есть в Telegram и отправится без повторной загрузки с YouTube
- Команды: `/start`, `/info`, `/changelog`
- Уведомления об ошибках для администраторов (см. `ADMINS_ID`)

Бот рассчитан на работу с **локальным Telegram Bot API server** (отправка больших файлов). URL сервера задаётся в `TELEGRAM_API_BASE`.

## Требования

- Python 3.10+
- PostgreSQL
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) (см. `pips_install.txt`)
- Локальный [Telegram Bot API](https://github.com/tdlib/telegram-bot-api) (по умолчанию `http://localhost:8081`)
- **ffmpeg** в `PATH` — только для кружков и голосовых сообщений

## Установка

1. Клонируйте репозиторий и перейдите в каталог проекта.

2. Создайте виртуальное окружение и установите зависимости:

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python -m pip install -U --pre "yt-dlp[default]"
```

На Linux/macOS вместо `venv\Scripts\activate` используйте `source venv/bin/activate`.

3. Создайте базу PostgreSQL (имя по умолчанию — `yt_download`):

```sql
CREATE DATABASE yt_download;
```

Таблица `cache_video` создаётся **автоматически** при первом запуске бота (см. `database.py`).

4. Создайте файл `.env` в корне проекта (см. раздел ниже).

5. Запустите локальный Telegram Bot API server и убедитесь, что `TELEGRAM_API_BASE` указывает на него.

6. Запустите бота:

```bash
python bot.py
```

Папка `downloads/` для временных файлов создаётся автоматически при скачивании.

## Переменные окружения (`.env`)

Создайте файл `.env` в корне проекта. Пример:

```env
# Обязательно
BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz

# Локальный Telegram Bot API (по умолчанию http://localhost:8081)
TELEGRAM_API_BASE=http://localhost:8081

# PostgreSQL
DB_NAME=yt_download
DB_USER=postgres
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=5432

# Telegram user ID администраторов (Python-список). Им показываются детали ошибок.
ADMINS_ID=[123456789, 987654321]
```

| Переменная | Обязательна | По умолчанию | Описание |
|------------|-------------|--------------|----------|
| `BOT_TOKEN` | да | — | Токен бота от [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_API_BASE` | нет | `http://localhost:8081` | Базовый URL локального Telegram Bot API |
| `DB_NAME` | нет | `yt_download` | Имя базы данных PostgreSQL |
| `DB_USER` | да | — | Пользователь PostgreSQL |
| `DB_PASSWORD` | да | — | Пароль PostgreSQL |
| `DB_HOST` | нет | `localhost` | Хост PostgreSQL |
| `DB_PORT` | нет | `5432` | Порт PostgreSQL |
| `ADMINS_ID` | нет | `[]` | Список Telegram ID админов в формате Python, например `[111, 222]` |

Файл `.env` не попадает в git (см. `.gitignore`).

## База данных

Таблица кэша создаётся при старте, если её нет:

| Колонка | Тип | Описание |
|---------|-----|----------|
| `yt_id` | `VARCHAR(11)` | ID видео на YouTube |
| `resolution` | `SMALLINT` | ID формата yt-dlp (`format_id`) |
| `file_id` | `TEXT` | `file_id` файла в Telegram для повторной отправки |

Составной первичный ключ: `(yt_id, resolution)`.

## Структура проекта

| Файл | Назначение |
|------|------------|
| `bot.py` | Обработчики Telegram, скачивание и отправка медиа |
| `database.py` | PostgreSQL: кэш и автосоздание таблицы |
| `settings.py` | Загрузка `.env`, пул соединений с БД |
| `video_size.py` | Список доступных качеств через yt-dlp |
| `utils.py` | Метаданные YouTube, автоудаление сообщений, ошибки для админов |
| `media_convert.py` | Конвертация в кружок и голосовое (ffmpeg) |
| `changelog.py` / `change_log.txt` | История обновлений для `/changelog` |
| `requirements.txt` | Python-зависимости |
| `pips_install.txt` | Команда установки yt-dlp |

## Ограничения

- Не обрабатываются плейлисты и прямые трансляции
- Файлы больше ~1800 MB помечаются как недоступные для отправки
- Кружки — только для видео до 59 секунд; голосовые — до ~9 минут 55 секунд
