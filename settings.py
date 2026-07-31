import ast
import os

from dotenv import load_dotenv
import psycopg2
from psycopg2 import pool

load_dotenv()


def _parse_admin_ids() -> set[int]:
    raw = os.getenv("ADMINS_ID", "[]")
    try:
        parsed = ast.literal_eval(raw)
    except (SyntaxError, ValueError):
        return set()
    if not isinstance(parsed, (list, tuple, set)):
        return set()
    return {int(admin_id) for admin_id in parsed}


ADMINS_ID = _parse_admin_ids()

# Настройки подключения к базе данных
DB_CONFIG = {
    'dbname': os.getenv('DB_NAME', 'yt_download'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST', '127.0.0.1'),
    'port': os.getenv('DB_PORT', '5432')
}

# Создаем пул соединений
conn_pool = psycopg2.pool.SimpleConnectionPool(1, 5, **DB_CONFIG)

if conn_pool:
    print("[DataBase] Connection pool created successfully.")