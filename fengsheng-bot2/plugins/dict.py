from pathlib import Path

import yaml
from nonebot import on_command, on_message, require
from nonebot.adapters import Event
from nonebot.adapters.qq import GroupMessageCreateEvent, C2CMessageCreateEvent
from nonebot.log import logger
from nonebot.params import CommandArg

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler  # noqa: E402

from ..utils.dict_tfidf import get_familiar_value, add_into_dict
from ..utils.dict_entry import serialize_message, build_message, cleanup_orphan_images, find_entries_with_missing_images
from ._core import _is_admin


# ── dict data store ───────────────────────────────────────────────────────────

_DICT_DATA_PATH = Path("data/com.fengsheng.bot/QunDb.yml")
_DICT_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)


def _load_dict() -> dict[str, str]:
    if _DICT_DATA_PATH.exists():
        try:
            data = yaml.safe_load(_DICT_DATA_PATH.read_text()) or {"data": {}}
            print(f"successfully load {len(data['data'])} data")
            return {str(k): str(v) for k, v in data["data"].items()}
        except Exception:
            pass
    return {}


def _save_dict() -> None:
    _DICT_DATA_PATH.write_text(yaml.dump({"data": _dict_data}, allow_unicode=True, default_flow_style=False))


_dict_data: dict[str, str] = _load_dict()

# 待添加词条队列：key=user_id, value=词条名
_add_db_qq_list: dict[str, str] = {}


def _deal_key(s: str) -> str:
    return s.strip().lower()


# ── dict message handlers ─────────────────────────────────────────────────────

_tfidf_tracker = on_message(priority=1, block=False)


@_tfidf_tracker.handle()
async def _handle_tfidf(event: Event) -> None:
    if not isinstance(event, GroupMessageCreateEvent):
        return
    raw_text = event.get_plaintext().strip()
    if raw_text:
        add_into_dict(raw_text)


_dict_callback = on_message(priority=5, block=False)


@_dict_callback.handle()
async def _handle_dict_callback(event: Event) -> None:
    if not isinstance(event, C2CMessageCreateEvent):
        return
    user_id = event.get_user_id()
    if user_id not in _add_db_qq_list:
        return
    key = _add_db_qq_list.pop(user_id)
    buf = serialize_message(event.get_message())
    _dict_data[key] = buf
    _save_dict()
    await _dict_callback.finish("编辑词条成功")


_dict_fallback = on_message(priority=20, block=False)


@_dict_fallback.handle()
async def _handle_dict_fallback(event: Event) -> None:
    if not isinstance(event, GroupMessageCreateEvent):
        return
    raw_text = event.get_plaintext().strip()
    if not raw_text:
        return
    s = get_familiar_value(_dict_data, _deal_key(raw_text))
    if not s:
        return
    msg = build_message(s)
    if msg:
        await _dict_fallback.finish(msg)


# ── dict commands ─────────────────────────────────────────────────────────────

_search_dict_cmd = on_command("查询词条", aliases={"搜索词条"}, force_whitespace=True, priority=10, block=True)


@_search_dict_cmd.handle()
async def _handle_search_dict(args=CommandArg()) -> None:
    content = args.extract_plain_text().strip()
    key = _deal_key(content)
    if key:
        await _deal_search_dict(_search_dict_cmd, key)


_add_dict_cmd = on_command("添加词条", force_whitespace=True, priority=10, block=True)


@_add_dict_cmd.handle()
async def _handle_add_dict(event: Event, args=CommandArg()) -> None:
    if not _is_admin(event):
        return
    content = args.extract_plain_text().strip()
    key = _deal_key(content)
    if key:
        await _deal_add_dict(_add_dict_cmd, event.get_user_id(), key)


_modify_dict_cmd = on_command("修改词条", force_whitespace=True, priority=10, block=True)


@_modify_dict_cmd.handle()
async def _handle_modify_dict(event: Event, args=CommandArg()) -> None:
    if not _is_admin(event):
        return
    content = args.extract_plain_text().strip()
    key = _deal_key(content)
    if key:
        await _deal_modify_dict(_modify_dict_cmd, event.get_user_id(), key)


_delete_dict_cmd = on_command("删除词条", force_whitespace=True, priority=10, block=True)


@_delete_dict_cmd.handle()
async def _handle_delete_dict(event: Event, args=CommandArg()) -> None:
    if not _is_admin(event):
        return
    content = args.extract_plain_text().strip()
    key = _deal_key(content)
    if key:
        await _deal_remove_dict(_delete_dict_cmd, key)


_missing_img_cmd = on_command("列出过期图片", force_whitespace=True, priority=10, block=True)


@_missing_img_cmd.handle()
async def _handle_missing_img(event: Event) -> None:
    if not _is_admin(event):
        return
    missing = find_entries_with_missing_images(_dict_data)
    if not missing:
        await _missing_img_cmd.finish("所有词条的图片均正常，未发现缺失文件。")
        return
    total = len(missing)
    display = missing[:50]
    lines = [f"{i + 1}. {k}" for i, k in enumerate(display)]
    header = f"以下 {total} 个词条存在图片文件缺失：\n"
    suffix = f"\n（仅显示前 50 条，共 {total} 条）" if total > 50 else ""
    await _missing_img_cmd.finish(header + "\n".join(lines) + suffix)


# ── dict CRUD helpers ─────────────────────────────────────────────────────────

async def _deal_add_dict(matcher, user_id: str, key: str) -> None:
    if "." in key:
        await matcher.finish("词条名称中不能包含 . 符号")
        return
    if key in _dict_data:
        await matcher.finish("词条已存在")
    else:
        await matcher.send("请输入要添加的内容")
        _add_db_qq_list[user_id] = key


async def _deal_modify_dict(matcher, user_id: str, key: str) -> None:
    if key not in _dict_data:
        await matcher.finish("词条不存在")
    else:
        await matcher.send("请输入要修改的内容")
        _add_db_qq_list[user_id] = key


async def _deal_remove_dict(matcher, key: str) -> None:
    if key not in _dict_data:
        await matcher.finish("词条不存在")
        return
    del _dict_data[key]
    _save_dict()
    await matcher.finish("删除词条成功")


async def _deal_search_dict(matcher, key: str) -> None:
    res = sorted([k for k in _dict_data if key in k])
    if res:
        num = len(res)
        if num > 10:
            res = res[:10]
            res[9] += f"\n等{num}个词条"
        lines = [f"{i + 1}. {r}" for i, r in enumerate(res)]
        await matcher.finish("搜索到以下词条：\n" + "\n".join(lines))
    else:
        await matcher.finish(f"搜索不到词条({key})")


# ── cron: cleanup orphan images ───────────────────────────────────────────────

async def _cron_cleanup_images() -> None:
    logger.info("[cron] 开始清理孤立词条图片")
    try:
        moved, deleted = cleanup_orphan_images(_dict_data)
        logger.info(f"[cron] 图片清理完成：移入暂存 {moved} 张，删除过期 {deleted} 张")
    except Exception as e:
        logger.error(f"[cron] 词条图片清理失败: {e}")


scheduler.add_job(
    _cron_cleanup_images,
    "cron",
    hour=4,
    minute=0,
    second=0,
    id="cleanup_orphan_images",
    timezone="Asia/Shanghai",
)