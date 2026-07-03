from __future__ import annotations

import random
from datetime import date, datetime, timedelta

from nonebot import on_command, on_message
from nonebot.adapters import Event, Message
from nonebot.adapters.qq import GroupAtMessageCreateEvent, GroupMessageCreateEvent
from nonebot.adapters.qq.message import Message as QQMessage, MessageSegment
from nonebot.internal.rule import Rule
from nonebot.log import logger
from nonebot.params import CommandArg

from ._core import (
    SCORE_FAIL,
    _perm, _save, _is_admin,
    _get_str, _get_bool, _get_int, _get_bytes, _get_json,
    deal_get_score, render_frequency, render_winrate2, render_game_status,
)


def _score_msg(scored: tuple[str, list[bytes]]) -> QQMessage:
    text, imgs = scored
    msg = QQMessage(text)
    for img in imgs:
        msg += MessageSegment.file_image(img)
    return msg


# 查询我
_query_me = on_command("查询我", priority=10, block=True)


@_query_me.handle()
async def _h_query_me(event: Event, args: Message = CommandArg()) -> None:
    if args.extract_plain_text().strip():
        return
    uid = event.get_user_id()
    name = _perm["playerMap"].get(uid)
    if not name:
        await _query_me.finish("请先注册或绑定")
    try:
        result = await _get_str("/getscore", {"name": name})
    except Exception as e:
        logger.error(e)
        await _query_me.finish("查询失败，请稍后再试。")
        return
    await _query_me.finish(_score_msg(deal_get_score(result)))


# 查询 <name> or 查询 @someone
_query = on_command("查询", priority=10, block=True)


@_query.handle()
async def _h_query(event: Event, args: Message = CommandArg()) -> None:
    uid = event.get_user_id()
    operator = _perm["playerMap"].get(uid)
    if not operator:
        await _query.finish("请先注册或绑定")

    for seg in args:
        if seg.type in ("mention_user", "at"):
            target_uid = seg.data.get("user_id", "") or seg.data.get("qq", "")
            target_name = _perm["playerMap"].get(target_uid)
            if not target_name:
                await _query.finish("该玩家还未绑定")
            try:
                result = await _get_str("/getscore", {"name": target_name, "operator": operator})
            except Exception as e:
                logger.error(e)
                await _query.finish("查询失败，请稍后再试。")
                return
            if result == "差距太大，无法查询":
                await _query.finish(random.choice(SCORE_FAIL))
            await _query.finish(_score_msg(deal_get_score(result)))
            return

    name = args.extract_plain_text().strip()
    if not name:
        return
    try:
        result = await _get_str("/getscore", {"name": name, "operator": operator})
    except Exception as e:
        logger.error(e)
        await _query.finish("查询失败，请稍后再试。")
        return
    if result == "差距太大，无法查询":
        await _query.finish(random.choice(SCORE_FAIL))
    await _query.finish(_score_msg(deal_get_score(result)))


# 排行
_rank = on_command("排行", priority=10, block=True)


@_rank.handle()
async def _h_rank(args: Message = CommandArg()) -> None:
    if args.extract_plain_text().strip():
        return
    try:
        img = await _get_bytes("/ranklist")
    except Exception as e:
        logger.error(e)
        return
    await _rank.finish(MessageSegment.file_image(img))


# 赛季最高分排行
_season_rank = on_command("赛季最高分排行", priority=10, block=True)


@_season_rank.handle()
async def _h_season_rank(args: Message = CommandArg()) -> None:
    if args.extract_plain_text().strip():
        return
    try:
        img = await _get_bytes("/ranklist", {"season_rank": "true"})
    except Exception as e:
        logger.error(e)
        return
    await _season_rank.finish(MessageSegment.file_image(img))


# 胜率
_winrate = on_command("胜率", priority=10, block=True)


@_winrate.handle()
async def _h_winrate(args: Message = CommandArg()) -> None:
    if args.extract_plain_text().strip():
        return
    try:
        img = await _get_bytes("/winrate")
    except Exception as e:
        logger.error(e)
        return
    await _winrate.finish(MessageSegment.file_image(img))


# 注册
_register = on_command("注册", priority=10, block=True)


@_register.handle()
async def _h_register(event: Event, args: Message = CommandArg()) -> None:
    name = args.extract_plain_text().strip()
    if not name:
        await _register.finish("命令格式：\n注册 名字")
    uid = event.get_user_id()
    old = _perm["playerMap"].get(uid)
    if old:
        await _register.finish(f"你已经注册过：{old}")
    try:
        ok = await _get_bool("/register", {"name": name})
    except Exception as e:
        logger.error(e)
        await _register.finish("注册失败，请稍后再试。")
        return
    if not ok:
        await _register.finish("用户名重复")
    _perm["playerMap"][uid] = name
    _save()
    await _register.finish("注册成功")


# 艾特
_at_player = on_command("艾特", priority=10, block=True)


@_at_player.handle()
async def _h_at_player(args: Message = CommandArg()) -> None:
    name = args.extract_plain_text().strip()
    if not name:
        await _at_player.finish("命令格式：\n艾特 游戏内的名字")
    for uid, player_name in _perm["playerMap"].items():
        if player_name == name:
            await _at_player.finish(MessageSegment.markdown(f'<qqbot-at-user id="{uid}" />'))
            return
    await _at_player.finish("没能找到此玩家，可能还未绑定")


# 重置密码
_reset_pwd = on_command("重置密码", priority=10, block=True)


@_reset_pwd.handle()
async def _h_reset_pwd(event: Event, args: Message = CommandArg()) -> None:
    name = args.extract_plain_text().strip()
    uid = event.get_user_id()
    if not name:
        player_name = _perm["playerMap"].get(uid)
        if not player_name:
            if _is_admin(event):
                await _reset_pwd.finish("重置密码 名字")
            return
        target = player_name
    else:
        if not _is_admin(event):
            return
        target = name
    try:
        result = await _get_str("/resetpwd", {"name": target})
    except Exception as e:
        logger.error(e)
        await _reset_pwd.finish("请求失败，请稍后再试。")
        return
    if result:
        await _reset_pwd.finish(result)


# 签到
_sign = on_command("签到", priority=10, block=True)


@_sign.handle()
async def _h_sign(event: Event, args: Message = CommandArg()) -> None:
    if args.extract_plain_text().strip():
        return
    uid = event.get_user_id()
    name = _perm["playerMap"].get(uid)
    if not name:
        await _sign.finish("请先注册或绑定")
    today = date.today().isoformat()
    if _perm.setdefault("signDates", {}).get(uid) == today:
        await _sign.finish("今天已经签到过了，明天再来吧")
    try:
        last_ms = await _get_int("/getlasttime", {"name": name})
    except Exception as e:
        logger.error(e)
        await _sign.finish("查询失败，请稍后再试。")
        return
    if last_ms >= 7 * 24 * 3600 * 1000:
        last_dt = datetime.now() - timedelta(milliseconds=last_ms)
        await _sign.finish(
            f"一周内未进行过游戏，无法进行签到 最近时间为：{last_dt.strftime('%Y-%m-%d %H:%M:%S')}"
        )
    energy = random.randint(0, 9) // 3 + 1
    try:
        ok = await _get_bool("/addenergy", {"name": name, "energy": str(energy)})
    except Exception as e:
        logger.error(e)
        await _sign.finish("签到失败")
        return
    if not ok:
        await _sign.finish("签到失败")
    _perm["signDates"][uid] = today
    _save()
    _msgs = {1: "太背了，获得1点精力", 2: "运气还行，获得2点精力", 3: "运气不错，获得3点精力"}
    await _sign.finish(_msgs.get(energy, f"运气爆棚，获得{energy}点精力"))


# ping
_ping = on_command("ping", priority=10, block=True)


@_ping.handle()
async def _h_ping(args: Message = CommandArg()) -> None:
    if not args.extract_plain_text().strip():
        await _ping.finish("pong")


# roll
_roll = on_command("roll", priority=10, block=True)


@_roll.handle()
async def _h_roll(args: Message = CommandArg()) -> None:
    if not args.extract_plain_text().strip():
        await _roll.finish(f"roll: {random.randint(0, 99)}")


# 活跃
_frequency = on_command("活跃", priority=10, block=True)


@_frequency.handle()
async def _h_frequency(args: Message = CommandArg()) -> None:
    if args.extract_plain_text().strip():
        return
    try:
        resp = await _get_json("/frequency")
    except Exception as e:
        logger.error(e)
        return
    img = render_frequency(resp.get("data", []), resp.get("hours", []))
    await _frequency.finish(MessageSegment.file_image(img))


# 胜率图
_winrate2 = on_command("胜率图", priority=10, block=True)


@_winrate2.handle()
async def _h_winrate2(args: Message = CommandArg()) -> None:
    if args.extract_plain_text().strip():
        return
    try:
        resp = await _get_json("/winrate2")
    except Exception as e:
        logger.error(e)
        return
    img = render_winrate2(resp.get("data", {}))
    await _winrate2.finish(MessageSegment.file_image(img))


# 观战
_watch = on_command("观战", priority=10, block=True)


@_watch.handle()
async def _h_watch(args: Message = CommandArg()) -> None:
    if args.extract_plain_text().strip():
        return
    try:
        rooms = await _get_json("/getallgames")
    except Exception as e:
        logger.error(e)
        return
    if not rooms:
        await _watch.finish("当前没有房间")
    imgs = render_game_status(rooms or [])
    if not imgs:
        await _watch.finish("当前没有房间")
    for img in imgs[:-1]:
        await _watch.send(QQMessage() + MessageSegment.file_image(img))
    await _watch.finish(QQMessage() + MessageSegment.file_image(imgs[-1]))

def _do_h_help(event: Event) -> str:
    uid = event.get_user_id()
    registered = uid in _perm["playerMap"]
    admin = _is_admin(event)

    tips: list[str] = ["查询 名字", "排行", "艾特 游戏内的名字"]
    tips += ["重置密码", "签到"] if registered else ["注册 名字"]
    if admin:
        tips += [
            "绑定 名字", "解绑 名字", "解绑所有0分玩家", "封号 名字 小时", "解封 名字",
            "禁用角色 名字", "启用角色 名字", "修改版本号 版本号",
            "强制结束所有游戏", "修改公告 公告内容", "修改出牌时间 秒数",
            "创号 名字", "增加精力 名字 数量",
        ]
    tips.sort()
    def _format_tip(tip: str) -> str:
        space_index = tip.find(" ")
        if space_index == -1:
            return f'<qqbot-cmd-input text="{tip}" show="{tip}" />'
        tip_text = tip[space_index+1:]
        tip = tip[:space_index]
        return f'<qqbot-cmd-input text="{tip} " show="{tip} " />{tip_text}'

    return "你可以使用以下功能：\n" + "\n".join(map(_format_tip, tips))

# 查看帮助
_help = on_command("查看帮助", priority=10, block=True)


@_help.handle()
async def _h_help(event: Event) -> None:
    text = _do_h_help(event)
    await _help.finish(MessageSegment.markdown(text))

# ---- 艾特机器人（无其他内容）触发帮助 ----
async def _check_at_bot_only(event: Event) -> bool:
    """Rule：@机器人且无其他有效内容（NoneBot2 已将 @bot 段剥离，直接检查剩余消息）"""
    if not isinstance(event, GroupAtMessageCreateEvent) and not isinstance(event, GroupMessageCreateEvent):
        return False
    if not event.to_me:
        return False
    for seg in event.get_message():
        if seg.type == "text":
            if seg.data.get("text", "").strip():
                return False  # 含非空文字
        else:
            return False  # 图片/表情等其他段
    return True

help_cmd = on_message(rule=Rule(_check_at_bot_only), priority=20, block=False)
@help_cmd.handle()
async def _h_help_cmd(event: Event) -> None:
    text = _do_h_help(event)
    await _help.finish(MessageSegment.markdown(text))