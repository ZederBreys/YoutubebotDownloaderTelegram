import asyncio
from aiogram import types
import os

def format_duration(duration_in_seconds):
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
    except Exception as e:
        pass

def find_file_by_name(directory : str, filename : str):
    for file in os.listdir(directory):
        if filename in file:
            return os.path.join(directory, file)
        
def format_number_with_spaces(number):
    return f"{number:,}".replace(",", " ")