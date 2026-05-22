from dotenv import load_dotenv
import psycopg2
from psycopg2 import pool
import os

load_dotenv()

# Настройки подключения к базе данных
DB_CONFIG = {
    'dbname': 'yt_download',
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'host': 'localhost',
    'port': '5432'
}

# Создаем пул соединений
conn_pool = psycopg2.pool.SimpleConnectionPool(1, 5, **DB_CONFIG)

if conn_pool:
    print("Connection pool created successfully.")