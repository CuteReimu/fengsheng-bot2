from __future__ import annotations

from nonebot import on_command
from nonebot.adapters import Event, Message
from nonebot.log import logger
from nonebot.params import CommandArg

from ._core import (
    _perm, _save, _is_admin,
    _get_str, _get_bool,
)

# 绑定
_bind = on_command("绑定", priority=10, block=True)


@_bind.handle()
async def _h_bind(event: Event, args: Message = CommandArg()) -> None:
    uid = event.get_user_id()
    name = args.extract_plain_text().strip()
    if not name:
        await _bind.finish("命令格式：\n绑定 名字")
    for id0, name0 in _perm["playerMap"].items():
        if id0 == uid:
            await _bind.finish("不能重复绑定")
        if name0 == name:
            await _bind.finish(f"已绑定 {name0}")
    try:
        result = await _get_str("/getscore", {"name": name})
    except Exception as e:
        logger.error(e)
        await _bind.finish("请求失败，请稍后再试。")
        return
    if result.endswith("已身死道消"):
        await _bind.finish("不存在的玩家")
    _perm["playerMap"][uid] = name
    _save()
    await _bind.finish("绑定成功")


# 解绑
_unbind = on_command("解绑", priority=10, block=True)


@_unbind.handle()
async def _h_unbind(event: Event, args: Message = CommandArg()) -> None:
    if not _is_admin(event):
        return
    target_name = args.extract_plain_text().strip()
    if not target_name:
        await _unbind.finish("命令格式：\n解绑 名字")
    for id0, name0 in _perm["playerMap"].items():
        if name0 == target_name:
            del(_perm["playerMap"][id0])
            _save()
            await _unbind.finish("解绑成功")
    await _unbind.finish("玩家没有绑定")


# 解绑所有0分玩家
_unbind_expired = on_command("解绑所有0分玩家", priority=10, block=True)


@_unbind_expired.handle()
async def _h_unbind_expired(event: Event, args: Message = CommandArg()) -> None:
    if not _is_admin(event):
        return
    if args.extract_plain_text().strip():
        return
    keep: dict[str, str] = {}
    for player_uid, name in list(_perm["playerMap"].items()):
        try:
            score = await _get_str("/getscore", {"name": name})
            if not score.endswith("已身死道消"):
                keep[player_uid] = name
        except Exception as e:
            logger.error(e)
            await _unbind_expired.finish("请求失败，请稍后再试。")
            return
    _perm["playerMap"] = keep
    _save()
    await _unbind_expired.finish("解绑成功")


# 封号
_forbid_player = on_command("封号", priority=10, block=True)


@_forbid_player.handle()
async def _h_forbid_player(event: Event, args: Message = CommandArg()) -> None:
    if not _is_admin(event):
        return
    c = args.extract_plain_text().strip()
    if not c:
        await _forbid_player.finish("命令格式：\n封号 名字 小时")
    idx = c.rfind(" ")
    if idx == -1:
        await _forbid_player.finish("命令格式：\n封号 名字 小时")
    name, hours_str = c[:idx].strip(), c[idx + 1:].strip()
    try:
        int(hours_str)
    except ValueError:
        await _forbid_player.finish("命令格式：\n封号 名字 小时")
    try:
        result = await _get_str("/forbidplayer", {"name": name, "hour": hours_str})
    except Exception as e:
        logger.error(e)
        await _forbid_player.finish("请求失败，请稍后再试。")
        return
    await _forbid_player.finish(result)


# 解封
_release_player = on_command("解封", priority=10, block=True)


@_release_player.handle()
async def _h_release_player(event: Event, args: Message = CommandArg()) -> None:
    if not _is_admin(event):
        return
    name = args.extract_plain_text().strip()
    if not name:
        await _release_player.finish("命令格式：\n解封 名字")
    try:
        result = await _get_str("/releaseplayer", {"name": name})
    except Exception as e:
        logger.error(e)
        await _release_player.finish("请求失败，请稍后再试。")
        return
    await _release_player.finish(result)


# 禁用角色
_forbid_role = on_command("禁用角色", priority=10, block=True)


@_forbid_role.handle()
async def _h_forbid_role(event: Event, args: Message = CommandArg()) -> None:
    if not _is_admin(event):
        return
    name = args.extract_plain_text().strip()
    if not name:
        await _forbid_role.finish("命令格式：\n禁用角色 名字")
    try:
        ok = await _get_bool("/forbidrole", {"name": name})
    except Exception as e:
        logger.error(e)
        await _forbid_role.finish("请求失败，请稍后再试。")
        return
    await _forbid_role.finish("禁用成功" if ok else "禁用失败")


# 启用角色
_release_role = on_command("启用角色", priority=10, block=True)


@_release_role.handle()
async def _h_release_role(event: Event, args: Message = CommandArg()) -> None:
    if not _is_admin(event):
        return
    name = args.extract_plain_text().strip()
    if not name:
        await _release_role.finish("命令格式：\n启用角色 名字")
    try:
        ok = await _get_bool("/releaserole", {"name": name})
    except Exception as e:
        logger.error(e)
        await _release_role.finish("请求失败，请稍后再试。")
        return
    await _release_role.finish("启用成功" if ok else "启用失败")


# 修改版本号
_set_version = on_command("修改版本号", priority=10, block=True)


@_set_version.handle()
async def _h_set_version(event: Event, args: Message = CommandArg()) -> None:
    if not _is_admin(event):
        return
    ver = args.extract_plain_text().strip()
    try:
        int(ver)
    except ValueError:
        await _set_version.finish("命令格式：\n修改版本号 版本号")
    try:
        await _get_str("/setversion", {"version": ver})
    except Exception as e:
        logger.error(e)
        await _set_version.finish("请求失败，请稍后再试。")
        return
    await _set_version.finish(f"版本号已修改为{ver}")


# 强制结束所有游戏
_force_end = on_command("强制结束所有游戏", priority=10, block=True)


@_force_end.handle()
async def _h_force_end(event: Event, args: Message = CommandArg()) -> None:
    if not _is_admin(event):
        return
    if args.extract_plain_text().strip():
        return
    try:
        await _get_str("/forceend")
    except Exception as e:
        logger.error(e)
        await _force_end.finish("请求失败，请稍后再试。")
        return
    await _force_end.finish("已执行")


# 修改公告
_set_notice = on_command("修改公告", priority=10, block=True)


@_set_notice.handle()
async def _h_set_notice(event: Event, args: Message = CommandArg()) -> None:
    if not _is_admin(event):
        return
    content = args.extract_plain_text().strip()
    if not content:
        await _set_notice.finish("命令格式：\n修改公告 公告内容")
    try:
        await _get_str("/setnotice", {"notice": content})
    except Exception as e:
        logger.error(e)
        await _set_notice.finish("请求失败，请稍后再试。")
        return
    await _set_notice.finish("公告已变更")


# 修改出牌时间
_set_wait = on_command("修改出牌时间", priority=10, block=True)


@_set_wait.handle()
async def _h_set_wait(event: Event, args: Message = CommandArg()) -> None:
    if not _is_admin(event):
        return
    sec_str = args.extract_plain_text().strip()
    try:
        sec = int(sec_str)
    except ValueError:
        await _set_wait.finish("命令格式：\n修改出牌时间 秒数")
        return
    if sec <= 0:
        await _set_wait.finish("出牌时间必须大于0")
    try:
        await _get_str("/updatewaitsecond", {"second": sec_str})
    except Exception as e:
        logger.error(e)
        await _set_wait.finish("请求失败，请稍后再试。")
        return
    await _set_wait.finish(f"默认出牌时间已修改为{sec_str}秒")


# 创号
_create_account = on_command("创号", priority=10, block=True)


@_create_account.handle()
async def _h_create_account(event: Event, args: Message = CommandArg()) -> None:
    if not _is_admin(event):
        return
    name = args.extract_plain_text().strip()
    if not name:
        await _create_account.finish("命令格式：\n创号 名字")
    try:
        ok = await _get_bool("/register", {"name": name})
    except Exception as e:
        logger.error(e)
        await _create_account.finish("请求失败，请稍后再试。")
        return
    await _create_account.finish("创号成功" if ok else "用户名重复")


# 增加精力
_add_energy = on_command("增加精力", priority=10, block=True)


@_add_energy.handle()
async def _h_add_energy(event: Event, args: Message = CommandArg()) -> None:
    if not _is_admin(event):
        return
    parts = args.extract_plain_text().strip().split()
    if len(parts) != 2:
        await _add_energy.finish("命令格式：\n增加精力 名字 数量")
    name, energy_str = parts[0], parts[1]
    try:
        int(energy_str)
    except ValueError:
        await _add_energy.finish("命令格式：\n增加精力 名字 数量")
    try:
        ok = await _get_bool("/addenergy", {"name": name, "energy": energy_str})
    except Exception as e:
        logger.error(e)
        await _add_energy.finish("请求失败，请稍后再试。")
        return
    await _add_energy.finish("增加精力成功" if ok else "增加精力失败")

