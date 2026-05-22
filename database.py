from settings import conn_pool

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
            WHERE yt_id = %s AND resolution = ANY(%s::smallint[]);
            """, (yt_id, resolution_ids))

            available_resolutions = {row[0] for row in cursor.fetchall()}
            return available_resolutions
    except Exception as e:
        print(f"Ошибка при получении разрешения кэша: {e}")
        return set()
    finally:
        release_connection(conn)