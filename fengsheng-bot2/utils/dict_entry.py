"""词条消息的序列化 / 反序列化 + 图片本地缓存管理"""
import hashlib
import json
import os
import shutil
import time
from typing import Any

import httpx
from nonebot.adapters.qq.message import Message, MessageSegment
from nonebot.log import logger

# ---- 图片缓存目录（仅用于持久化原始文件，避免重复下载） ----
_CACHE_DIR = "chat_images"
os.makedirs(_CACHE_DIR, exist_ok=True)

# ---- 孤立图片暂存目录（移入后保留 7 天再删除） ----
_STAGING_DIR = "chat_images1"
os.makedirs(_STAGING_DIR, exist_ok=True)
_STAGING_KEEP_DAYS = 7


# ===========================================================================
# 序列化（存词条）
# ===========================================================================

def serialize_message(msg: Message) -> str:
    """
    将 OneBot V11 Message 序列化为 JSON 字符串存入词条数据库。

    图片段：下载原图到本地 chat_images/ 缓存，JSON 中只存本地文件路径。
    文本段：直接保留 text。
    其他段：保留原始结构。
    """
    segments: list[dict[str, Any]] = []
    for seg in msg:
        seg_type: str = seg.type
        data: dict = dict(seg.data)

        if seg_type == "image":
            # 优先取 url，其次取 file
            url: str = data.get("url", "") or data.get("file", "")
            local_path = _download_image(url) if url else None
            if local_path:
                segments.append({"type": "image", "data": {"file": local_path}})
            else:
                logger.warning(f"图片段无法获取内容，已跳过: {data}")
        else:
            segments.append({"type": seg_type, "data": data})

    return json.dumps(segments, ensure_ascii=False)


def _download_image(url: str) -> str | None:
    """
    下载图片到 chat_images/ 本地缓存，返回本地文件路径。
    若 url 是 file:// 本地路径则直接返回该路径。
    下载失败返回 None。
    """
    # 本地文件路径
    local_path = url[len("file://"):] if url.startswith("file://") else None
    if local_path and os.path.isfile(local_path):
        return local_path

    # 普通 URL：先查本地缓存
    try:
        url_hash = hashlib.md5(url.encode()).hexdigest()
        url_path = url.split("?")[0].rstrip("/")
        ext = os.path.splitext(url_path)[1]
        if ext.lower() not in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"):
            ext = ".jpg"
        cached = os.path.join(_CACHE_DIR, f"{url_hash}{ext}")

        if not os.path.exists(cached):
            logger.info(f"下载图片: {url} -> {cached}")
            with httpx.Client(timeout=15, follow_redirects=True) as client:
                resp = client.get(url)
                resp.raise_for_status()
                with open(cached, "wb") as f:
                    f.write(resp.content)

        return cached
    except Exception as e:  # pylint: disable=broad-except
        logger.warning(f"获取图片失败 ({url}): {e}")
        return None


def _read_file_bytes(path: str) -> bytes | None:
    """读取文件并返回 base64 字符串，失败返回 None。"""
    try:
        with open(path, "rb") as f:
            return f.read()
    except Exception as e:  # pylint: disable=broad-except
        logger.warning(f"读取文件失败 ({path}): {e}")
        return None


# ===========================================================================
# 反序列化（读词条）
# ===========================================================================

def deserialize_to_segments(raw: str) -> list[MessageSegment]:
    """
    将词条 JSON 字符串反序列化为 V11Seg 列表，供发送使用。

    图片段：直接取 base64 字段，通过 base64:// 协议发送，兼容 Docker 环境。
    expire_hours 参数保留以兼容调用方，实际不再使用。
    """
    try:
        segments_data: list[dict] = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        # 兼容旧版：直接当文本
        logger.debug(f"词条内容不是 JSON，作为文本处理: {raw[:80]}")
        return [MessageSegment.text(str(raw))]

    result: list[MessageSegment] = []

    for seg in segments_data:
        seg_type: str = seg.get("type", "")
        data: dict = seg.get("data", {})

        if seg_type == "text":
            text = data.get("text", "")
            if text:
                result.append(MessageSegment.text(text))

        elif seg_type == "image":
            file: str = data.get("file", "")
            # 去掉 file:// 前缀（兼容旧格式）
            local_path = file[len("file://"):] if file.startswith("file://") else file

            img: bytes = b""
            if local_path and os.path.isfile(local_path):
                img = _read_file_bytes(local_path) or b""

            # 兼容旧格式：有 url 字段，重新下载到本地再转 base64
            if not img:
                url: str = data.get("url", "")
                if url:
                    dl = _download_image(url)
                    if dl:
                        img = _read_file_bytes(dl) or b""

            if img:
                result.append(MessageSegment.file_image(img))
            else:
                result.append(MessageSegment.text("（找不到图片，请重新编辑词条）"))

        # elif seg_type == "face":
            # result.append(MessageSegment.face(int(data.get("id", 0))))

        # elif seg_type == "at":
        #     result.append(MessageSegment.at(str(data.get("qq", ""))))

        else:
            # try:
            #     result.append(V11Seg(seg_type, data))
            # except Exception:  # pylint: disable=broad-except
            logger.warning(f"无法还原消息段类型 {seg_type}，已跳过")

    return result


def build_message(raw: str) -> Message | None:
    """
    反序列化词条并组装成 V11Message。
    若词条为空则返回 None。
    """
    segs = deserialize_to_segments(raw)
    if not segs:
        return None
    msg = Message()
    for seg in segs:
        msg += seg
    return msg


# ===========================================================================
# 孤立图片清理
# ===========================================================================

def collect_referenced_images(entries: dict[str, str]) -> set[str]:
    """
    从所有词条 JSON 值中提取所有本地图片的绝对路径。
    用于后续与 chat_images/ 目录对比，找出孤立文件。
    """
    referenced: set[str] = set()
    for raw in entries.values():
        try:
            segments_data: list[dict] = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        for seg in segments_data:
            if seg.get("type") == "image":
                file: str = seg.get("data", {}).get("file", "")
                if file.startswith("file://"):
                    file = file[len("file://"):]
                if file:
                    referenced.add(os.path.normpath(os.path.abspath(file)))
    return referenced


def cleanup_orphan_images(entries: dict[str, str]) -> tuple[int, int]:
    """
    清理孤立的本地图片缓存：

    1. 扫描 chat_images/ 目录，将不属于任何词条的图片移入
       chat_images1/（暂存区），并刷新其 mtime 为当前时间。
    2. 扫描 chat_images1/ 目录，删除 mtime 超过 7 天的文件。

    返回 (moved_count, deleted_count)。
    """
    os.makedirs(_STAGING_DIR, exist_ok=True)

    referenced = collect_referenced_images(entries)
    moved = 0

    # --- 第一步：把孤立文件移入暂存区 ---
    try:
        for fname in os.listdir(_CACHE_DIR):
            fpath = os.path.join(_CACHE_DIR, fname)
            if not os.path.isfile(fpath):
                continue
            abs_path = os.path.normpath(os.path.abspath(fpath))
            if abs_path not in referenced:
                dest = os.path.join(_STAGING_DIR, fname)
                try:
                    if os.path.exists(dest):
                        os.remove(dest)
                    shutil.move(fpath, dest)
                    # 刷新 mtime：记录"移入暂存区"的时间
                    os.utime(dest)
                    moved += 1
                    logger.info(f"[图片清理] 移入暂存区: {fpath} -> {dest}")
                except Exception as e:  # pylint: disable=broad-except
                    logger.warning(f"[图片清理] 移动文件失败 ({fpath}): {e}")
    except Exception as e:  # pylint: disable=broad-except
        logger.warning(f"[图片清理] 遍历 {_CACHE_DIR} 失败: {e}")

    # --- 第二步：删除暂存区中超过 7 天的文件 ---
    deleted = 0
    cutoff = time.time() - _STAGING_KEEP_DAYS * 24 * 3600
    try:
        for fname in os.listdir(_STAGING_DIR):
            fpath = os.path.join(_STAGING_DIR, fname)
            if not os.path.isfile(fpath):
                continue
            try:
                if os.path.getmtime(fpath) < cutoff:
                    os.remove(fpath)
                    deleted += 1
                    logger.info(f"[图片清理] 已删除过期暂存文件: {fpath}")
            except Exception as e:  # pylint: disable=broad-except
                logger.warning(f"[图片清理] 删除文件失败 ({fpath}): {e}")
    except Exception as e:  # pylint: disable=broad-except
        logger.warning(f"[图片清理] 遍历 {_STAGING_DIR} 失败: {e}")

    logger.info(f"[图片清理] 完成：移入暂存 {moved} 张，删除过期 {deleted} 张")
    return moved, deleted


# ===========================================================================
# 词条图片完整性检查
# ===========================================================================

def find_entries_with_missing_images(entries: dict[str, str]) -> list[str]:
    """
    遍历所有词条，返回含有至少一张本地找不到的图片的词条 key 列表（已排序）。

    "找不到"指词条 JSON 中记录的本地文件路径不存在于磁盘，
    例如文件被手动删除、或被清理任务移入了暂存区。
    """
    missing_keys: list[str] = []
    for key, raw in entries.items():
        try:
            segments_data: list[dict] = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        for seg in segments_data:
            if seg.get("type") == "image":
                file: str = seg.get("data", {}).get("file", "")
                if file.startswith("file://"):
                    file = file[len("file://"):]
                # 图片路径存在但文件不在磁盘上 → 记录此词条
                if file and not os.path.isfile(file):
                    missing_keys.append(key)
                    break  # 每个词条只记录一次
    return sorted(missing_keys)
