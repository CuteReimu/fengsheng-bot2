from __future__ import annotations

import asyncio
from pathlib import Path

import yaml
from nonebot import get_bot, get_driver, on_command
from nonebot.adapters import Event
from nonebot.adapters.qq import Bot
from nonebot.adapters.qq.event import GroupMessageCreateEvent
from nonebot.log import logger

from ._core import _get_json

# ── persistence ───────────────────────────────────────────────────────────────

_DATA_PATH = Path("data/com.fengsheng.bot/PushGroups.yml")
_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)


def _load() -> set[str]:
    if _DATA_PATH.exists():
        try:
            return set(yaml.safe_load(_DATA_PATH.read_text()) or [])
        except Exception:
            pass
    return set()


def _save() -> None:
    _DATA_PATH.write_text(yaml.dump(list(_group_ids), allow_unicode=True))


_group_ids: set[str] = _load()

# ── polling ───────────────────────────────────────────────────────────────────

_POLL_INTERVAL = 10


async def _poll_once() -> None:
    if not _group_ids:
        return
    try:
        msgs = await _get_json("/getgroupmessages")
    except Exception as e:
        logger.error(f"getgroupmessages failed: {e}")
        return
    if not msgs:
        return
    bot = get_bot()
    if not isinstance(bot, Bot):
        return
    for gid in _group_ids:
        for msg in msgs:
            try:
                await bot.send_to_group(group_openid=gid, message=msg)
            except Exception as e:
                logger.warning(f"push to group {gid} failed: {e}")


async def _poll_loop() -> None:
    while True:
        await asyncio.sleep(_POLL_INTERVAL)
        try:
            await _poll_once()
        except Exception as e:
            logger.error(f"push poll loop error: {e}")


driver = get_driver()


@driver.on_startup
async def _start_poll() -> None:
    asyncio.create_task(_poll_loop())


# ── subscribe / unsubscribe ───────────────────────────────────────────────────

_subscribe = on_command("订阅战况", priority=10, force_whitespace=True, block=True)


@_subscribe.handle()
async def _h_subscribe(event: Event) -> None:
    if not isinstance(event, GroupMessageCreateEvent):
        await _subscribe.finish("请在群聊中使用该命令")
        return
    gid = event.group_openid
    if gid in _group_ids:
        await _subscribe.finish("本群已订阅战况推送")
        return
    _group_ids.add(gid)
    _save()
    await _subscribe.finish("已订阅战况推送")


_unsubscribe = on_command("取消订阅战况", priority=10, force_whitespace=True, block=True)


@_unsubscribe.handle()
async def _h_unsubscribe(event: Event) -> None:
    if not isinstance(event, GroupMessageCreateEvent):
        await _unsubscribe.finish("请在群聊中使用该命令")
        return
    gid = event.group_openid
    if gid not in _group_ids:
        await _unsubscribe.finish("本群还未订阅战况推送")
        return
    _group_ids.discard(gid)
    _save()
    await _unsubscribe.finish("已取消订阅战况推送")
