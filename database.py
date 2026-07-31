from settings import conn_pool

CREATE_CACHE_VIDEO_TABLE = """
CREATE TABLE IF NOT EXISTS public.cache_video (
    yt_id VARCHAR(11) NOT NULL,
    resolution VARCHAR(50) NOT NULL,
    file_id TEXT NOT NULL,
    PRIMARY KEY (yt_id, resolution)
);
"""

CHECK_RESOLUTION_TYPE = """
SELECT data_type
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'cache_video'
  AND column_name = 'resolution';
"""

ALTER_RESOLUTION_TO_VARCHAR = """
ALTER TABLE public.cache_video
ALTER COLUMN resolution TYPE VARCHAR(50)
USING resolution::VARCHAR;
"""

NUMERIC_TYPES = frozenset({"smallint", "integer", "bigint", "numeric", "real", "double precision"})


def ensure_schema():
    """Создаёт таблицу cache_video, если её ещё нет в базе."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(CREATE_CACHE_VIDEO_TABLE)
        conn.commit()
        print("[DataBase] Table cache_video is ready.")
    except Exception as e:
        conn.rollback()
        print(f"[DataBase] Failed to ensure schema: {e}")
        raise
    finally:
        release_connection(conn)


def migrate_resolution_to_varchar():
    """Безопасная миграция колонки resolution с SMALLINT на VARCHAR(50)."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(CHECK_RESOLUTION_TYPE)
            row = cur.fetchone()

        if row is None:
            print("[DataBase] Migration: table cache_video not found, skipping.")
            return

        current_type = row[0]
        if current_type in NUMERIC_TYPES:
            with conn.cursor() as cur:
                cur.execute(ALTER_RESOLUTION_TO_VARCHAR)
            conn.commit()
            print(
                f"[DataBase] Migrated resolution from {current_type} to VARCHAR(50)."
            )
        else:
            print(
                f"[DataBase] Migration: resolution is already {current_type}, no changes needed."
            )
    except Exception:
        conn.rollback()
        raise
    finally:
        release_connection(conn)


def get_connection():
    return conn_pool.getconn()

def release_connection(conn):
    conn_pool.putconn(conn)

def check_record_exists(yt_id, resolution):
    """Проверяет наличие записи с заданным yt_id и resolution в таблице cache_video и возвращает содержимое записи."""
    query = """
    SELECT file_id FROM cache_video WHERE yt_id = %s AND resolution = %s;
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(query, (yt_id, resolution))
            result = cur.fetchone()
        
        if result:
            return result[0]
        else:
            return None
    except Exception as e:
        print(f"Ошибка при проверке записи: {e}")
        return None
    finally:
        release_connection(conn)

def create_record_if_not_exists(yt_id, resolution, file_id):
    """Создает запись, если запись с заданным yt_id и resolution отсутствует в таблице cache_video."""
    if check_record_exists(yt_id, resolution):
        return
    
    query = """
    INSERT INTO cache_video (yt_id, resolution, file_id) VALUES (%s, %s, %s)
    ON CONFLICT DO NOTHING;
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(query, (yt_id, resolution, file_id))
            conn.commit()
    except Exception as e:
        print(f"Ошибка при создании записи: {e}")
    finally:
        release_connection(conn)

def get_cache_resolution(yt_id, resolution_ids):
    """Получаем все записи с заданным yt_id и resolution list из таблицы cache_video."""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
            SELECT resolution, yt_id
            FROM public.cache_video
            WHERE yt_id = %s AND resolution = ANY(%s::varchar[]);
            """, (yt_id, resolution_ids))

            available_resolutions = {row[0] for row in cursor.fetchall()}
            return available_resolutions
    except Exception as e:
        print(f"Ошибка при получении разрешения кэша: {e}")
        return set()
    finally:
        release_connection(conn)


ensure_schema()
migrate_resolution_to_varchar()