"""KV 数据库"""
import os
import shelve
import threading

from nonebot.log import logger

_DB_DIR = os.path.join("assets", "database")
os.makedirs(_DB_DIR, exist_ok=True)
_DB_PATH = os.path.join(_DB_DIR, "maplebot")
_lock = threading.Lock()


def get(key: str) -> tuple[str, bool]:
    """根据 Key 获取 Value，返回 (value, ok)"""
    with _lock:
        try:
            with shelve.open(_DB_PATH) as db:
                if key in db:
                    return db[key], True
                return "", False
        except Exception as e:
            logger.error(f"get failed: key={key}, error={e}")
            return "", False


def set_value(key: str, value: str) -> None:
    """设置键值对"""
    with _lock:
        try:
            with shelve.open(_DB_PATH) as db:
                db[key] = value
        except Exception as e:
            logger.error(f"set failed: key={key}, error={e}")
