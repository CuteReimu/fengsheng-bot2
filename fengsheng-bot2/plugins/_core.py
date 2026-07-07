from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import httpx
import matplotlib
import yaml
from nonebot import get_driver
from nonebot.adapters import Event

matplotlib.use("Agg")
matplotlib.rcParams["axes.unicode_minus"] = False

# Register simhei font for matplotlib (same search logic as _get_font)
import matplotlib.font_manager as _mpl_fm

def _register_mpl_font() -> None:
    for _root in [Path("."), Path("/usr/share/fonts")]:
        if not _root.is_dir():
            continue
        for _fp in _root.rglob("simhei.ttf"):
            try:
                _mpl_fm.fontManager.addfont(str(_fp))
                matplotlib.rcParams["font.family"] = _mpl_fm.FontProperties(fname=str(_fp)).get_name()
                return
            except Exception:
                pass

_register_mpl_font()
from nonebot.adapters.qq import C2CMessageCreateEvent

try:
    from pydantic import BaseModel
    from nonebot import get_plugin_config

    class _Cfg(BaseModel):
        fengsheng_url: str = "http://127.0.0.1:9094"

    _plugin_cfg = get_plugin_config(_Cfg)
    FENGSHENG_URL: str = _plugin_cfg.fengsheng_url.rstrip("/")
except Exception:
    _raw = get_driver().config
    FENGSHENG_URL = str(getattr(_raw, "fengsheng_url", "http://127.0.0.1:9094")).rstrip("/")

# ── persistence ───────────────────────────────────────────────────────────────

_DATA_PATH = Path("data/com.fengsheng.bot/PermData.yml")
_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)


def _load() -> dict:
    if _DATA_PATH.exists():
        try:
            data = yaml.safe_load(_DATA_PATH.read_text()) or {}
            data.setdefault("playerMap", {})
            data.setdefault("signDates", {})
            return data
        except Exception:
            pass
    return {"playerMap": {}, "signDates": {}}


def _save() -> None:
    _DATA_PATH.write_text(yaml.dump(_perm, allow_unicode=True, default_flow_style=False))


_perm: dict = _load()

# ── auth ──────────────────────────────────────────────────────────────────────


# 目前没有什么好办法获得角色在群里的身份，先只允许私聊进行管理，然后只允许管理加好友
def _is_admin(event: Event) -> bool:
    return isinstance(event, C2CMessageCreateEvent)


# ── HTTP ──────────────────────────────────────────────────────────────────────

_http = httpx.AsyncClient(timeout=30)


async def _get_result(path: str, params: dict | None = None) -> Any:
    r = await _http.get(FENGSHENG_URL + path, params=params)
    r.raise_for_status()
    j = r.json()
    e = j.get("err")
    if e:
        raise Exception(e)
    return j


async def _get_str(path: str, params: dict | None = None) -> str:
    return (await _get_result(path, params)).get("result", "")


async def _get_bool(path: str, params: dict | None = None) -> bool:
    return (await _get_result(path, params)).get("result", False)


async def _get_int(path: str, params: dict | None = None) -> int:
    return (await _get_result(path, params)).get("result", 0)


async def _get_bytes(path: str, params: dict | None = None) -> bytes:
    r = await _http.get(FENGSHENG_URL + path, params=params)
    r.raise_for_status()
    return r.content


async def _get_json(path: str, params: dict | None = None) -> Any:
    r = await _http.get(FENGSHENG_URL + path, params=params)
    r.raise_for_status()
    return r.json()


# ── score display ─────────────────────────────────────────────────────────────

_TIER_EMOJIS = {"🥉", "🥈", "🥇", "💍", "💠", "👑", "☀️", "🔥"}

SCORE_FAIL = [
    "蝼蚁之目，也敢窥天？收了你那点微末神念！",
    "萤火之光，岂配窥探皓月之辉？",
    "区区凡识，妄测天机，尔不怕道心崩毁么？",
    "蜉蝣窥天，自寻道灭。",
    "命如微尘，也配问鼎苍穹之名？",
    "此等因果，你看一眼，命承不起。",
    "妄窥尊者？尔等灵台，当惧崩摧！",
    "神念止步！此乃汝不可知、不可念之界。",
    "尔之眼界，便是天堑。",
    "仙踪缥缈，凡念勿染。",
    "你的道行，不配问他的名号。",
    "此乃天堑，蝼蚁止步。",
    "镜未磨，水未平，也敢映照大日真容？",
]

# ── table renderer ────────────────────────────────────────────────────────────


def _render_table(header: list[str], rows: list[list[str]]) -> str:
    sep = "|" + "|".join("---" for _ in header) + "|"
    lines = ["|" + "|".join(header) + "|", sep]
    for row in rows:
        lines.append("|" + "|".join(row) + "|")
    return "\n" + "\n".join(lines) + "\n"


def deal_get_score(result: str) -> tuple[str, list[bytes]]:
    is_win_rate = False
    is_history = False
    header_parts: list[str] = []
    win_rate_rows: list[list[str]] = []
    history_rows: list[list[str]] = []

    for line in result.split("\n"):
        if not line:
            continue
        if line == "---------------------------------":
            is_win_rate, is_history = (not is_win_rate and not is_history, is_win_rate)
            continue
        if line.startswith("身份\t") or (line.startswith("最近") and line.endswith("场战绩")):
            continue
        if line.startswith("剩余精力"):
            header_parts.append("，" + line)
        elif is_win_rate:
            win_rate_rows.append([s.strip() for s in line.split("\t")])
        elif is_history:
            arr = line.split(",")
            if len(arr) < 5:
                continue
            tier = arr[3]
            if any(e in tier for e in _TIER_EMOJIS):
                continue
            role = arr[0].replace("(死亡)", "")
            alive = "死亡" if "(死亡)" in arr[0] else "存活"
            identity = arr[1].replace("神秘人[", "").replace("]", "")
            history_rows.append([role, alive, identity, arr[2], tier, arr[4]])
        else:
            header_parts.append(line)

    history_rows.reverse()

    if win_rate_rows:
        header_parts.append(_render_table(["身份", "胜率", "平均胜率", "场次"], win_rate_rows))
    if history_rows:
        header_parts.append("\n***\n")
        header_parts.append(_render_table(["角色", "存活", "身份", "胜负", "段位", "分数"], history_rows))

    return "".join(header_parts).strip(), []


# ── chart renderers ───────────────────────────────────────────────────────────

def render_frequency(data: list[dict], hours: list[int]) -> bytes:
    """Render 活跃 chart: daily activity + hourly distribution in one PNG."""
    import matplotlib.pyplot as plt
    from datetime import datetime, timedelta

    if not data:
        fig, ax = plt.subplots(figsize=(8, 2))
        ax.text(0.5, 0.5, "暂无数据", ha="center", va="center", transform=ax.transAxes, fontsize=14)
        ax.axis("off")
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=100)
        plt.close(fig)
        return buf.getvalue()

    max_date = datetime.strptime(data[-1]["date"], "%Y-%m-%d")
    min_date = max_date - timedelta(days=30)

    complete: list[dict] = []
    cur = min_date
    while cur <= max_date:
        ds = cur.strftime("%Y-%m-%d")
        found = next((d for d in data if d["date"] == ds), None)
        complete.append(found or {"date": ds, "count": 0, "pc": 0})
        cur += timedelta(days=1)

    labels = [d["date"][5:] for d in complete]
    counts = [d["count"] for d in complete]
    pcs = [d["pc"] for d in complete]
    bars = [d["pc"] - d["count"] for d in complete]

    stat = complete[:-1] if len(complete) > 1 else complete
    n = max(len(stat), 1)
    ave_count = round(sum(d["count"] for d in stat) / n, 1)
    ave_pc = round(sum(d["pc"] for d in stat) / n, 1)
    ave_pc_count = round(sum(d["pc"] - d["count"] for d in stat) / n, 1)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 9), facecolor="#f5f7fa")
    fig.subplots_adjust(hspace=0.45, top=0.95, bottom=0.08, left=0.06, right=0.94)

    x = list(range(len(complete)))

    # Chart 1: daily
    ax1.set_facecolor("white")
    ax1.bar(x, bars, color=(59 / 255, 169 / 255, 120 / 255, 0.4), label="活人局系数", zorder=2, width=0.8)
    ax1.plot(x, counts, color="#e10602", label="场次", linewidth=1.5, zorder=3)
    ax1.plot(x, pcs, color="#2932e1", label="参与人次", linewidth=1.5, zorder=3)

    for i, d in enumerate(complete):
        if datetime.strptime(d["date"], "%Y-%m-%d").weekday() == 6:
            ax1.axvline(x=i, color=(59 / 255, 169 / 255, 120 / 255), linestyle="--", linewidth=1, alpha=0.7, zorder=1)

    ax1.axhline(y=ave_count, color="#e10602", linestyle="--", linewidth=1.5, alpha=0.8, zorder=4)
    ax1.axhline(y=ave_pc, color="#2932e1", linestyle="--", linewidth=1.5, alpha=0.8, zorder=4)
    ax1.axhline(y=ave_pc_count, color=(59 / 255, 169 / 255, 120 / 255), linestyle="--", linewidth=1.5, alpha=0.6, zorder=4)
    ax1.text(0.01, ave_count, f" {ave_count}", color="#e10602", fontsize=8, va="center", transform=ax1.get_yaxis_transform())
    ax1.text(0.01, ave_pc, f" {ave_pc}", color="#2932e1", fontsize=8, va="center", transform=ax1.get_yaxis_transform())
    ax1.text(0.01, ave_pc_count, f" {ave_pc_count}", color=(59 / 255, 169 / 255, 120 / 255), fontsize=8, va="center", transform=ax1.get_yaxis_transform())

    ax1.set_xticks(x)
    ax1.set_xticklabels(labels, rotation=45, ha="right", fontsize=7)
    ax1.margins(x=0.05 / 3)
    ax1.yaxis.set_label_position("right")
    ax1.yaxis.tick_right()
    ax1.legend(loc="upper left", fontsize=9)
    ax1.set_title("近期每日活跃度", fontsize=16, pad=8)
    ax1.grid(True, axis="y", alpha=0.3)
    ax1.spines["top"].set_visible(False)
    ax1.spines["left"].set_visible(False)

    # Chart 2: hourly
    ax2.set_facecolor("white")
    total = sum(hours) or 1
    hour_pcts = [round(v / total * 10000) / 100 for v in hours]
    ax2.bar(range(len(hours)), hour_pcts, color=(54 / 255, 162 / 255, 235 / 255, 0.4),
            edgecolor=(54 / 255, 162 / 255, 235 / 255), width=1.0)
    ax2.set_xlim(-0.5, len(hours) - 0.5)
    ax2.set_xticks(range(0, len(hours), 2))
    ax2.set_xticklabels([f"{h}:00" for h in range(0, len(hours), 2)], fontsize=9)
    ax2.set_ylabel("活跃系数", fontsize=12)
    ax2.set_title("全天活跃度", fontsize=16, pad=8)
    ax2.grid(True, axis="y", alpha=0.3)
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_visible(False)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=100, facecolor="#f5f7fa")
    plt.close(fig)
    return buf.getvalue()


_ROLE_CATEGORIES = [
    ["张一挺", "黄济仁", "裴玲", "阿芙罗拉", "李醒", "小九", "商玉", "邵秀", "肥原龙川", "李宁玉", "白沧浪", "连鸢", "韩梅", "SP顾小梦", "端木静", "SP李宁玉", "王富贵", "鄭文先", "程小蝶", "顾小梦", "鬼脚", "老鳖", "白小年", "老汉", "王魁", "白菲菲", "白昆山", "吴志国", "金生火", "玄青子", "毛不拔", "王田香"],
    ["秦圆圆", "SP程小蝶", "老虎", "钱敏", "SP连鸢", "盛老板", "简先生", "高桥智子", "玛利亚", "青年小九", "青年韩梅", "池镜海", "SP端木静"],
    ["陈安娜", "凌素秋", "成年韩梅", "哑炮", "陈大耳", "边云疆", "金自来", "间谍阿芙罗拉", "小铃铛", "SP白菲菲", "李书云", "成年小九", "秦无命", "SP韩梅", "SP小九", "孙守謨", "王响"],
]
_CAT_COLORS = [(59 / 255, 169 / 255, 120 / 255), (225 / 255, 6 / 255, 2 / 255), (41 / 255, 50 / 255, 225 / 255)]
_CAT_LABELS = ["基础角色", "一扩角色", "二扩角色"]


def _role_color(name: str) -> tuple:
    for i, cat in enumerate(_ROLE_CATEGORIES):
        if name in cat:
            return _CAT_COLORS[i]
    return 0.6, 0.6, 0.6


def render_winrate2(role_data: dict) -> bytes:
    """Render 胜率图 scatter chart: role appearances vs win rate."""
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    entries = [(name, v) for name, v in role_data.items() if isinstance(v, (list, tuple)) and len(v) >= 2 and v[0] > 0]
    if not entries:
        fig, ax = plt.subplots(figsize=(8, 2))
        ax.text(0.5, 0.5, "暂无数据", ha="center", va="center", transform=ax.transAxes, fontsize=14)
        ax.axis("off")
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=100)
        plt.close(fig)
        return buf.getvalue()

    xs = [v[0] for _, v in entries]
    ys = [round(v[1] / v[0] * 10000) / 100 for _, v in entries]
    names = [name for name, _ in entries]
    colors = [_role_color(name) for name, _ in entries]

    sorted_ys = sorted(ys)
    mid = len(sorted_ys) // 2
    median_y = sorted_ys[mid] if len(sorted_ys) % 2 else (sorted_ys[mid - 1] + sorted_ys[mid]) / 2
    median_y = round(median_y * 100) / 100

    fig, ax = plt.subplots(figsize=(12, 10), facecolor="#f5f7fa")
    ax.set_facecolor("white")
    ax.scatter(xs, ys, c=colors, s=60 / 9, zorder=3)

    for x_val, y_val, label, color in zip(xs, ys, names, colors):
        ax.annotate(label, (x_val, y_val), textcoords="offset points", xytext=(0, 6),
                    ha="center", fontsize=8, color=color)

    ax.axhline(y=median_y, color=(1.0, 87 / 255, 34 / 255, 0.65), linestyle="--", linewidth=2)
    x_min = min(xs) if xs else 0
    ax.text(x_min, median_y, f" {median_y}", color=(1.0, 87 / 255, 34 / 255), fontsize=9, va="center")

    legend_patches = [Patch(color=_CAT_COLORS[i], label=_CAT_LABELS[i]) for i in range(len(_CAT_LABELS))]
    ax.legend(handles=legend_patches, fontsize=10, loc="best")

    ax.set_xlabel("出场次数", fontsize=14)
    ax.set_ylabel("胜率（%）", fontsize=14)
    ax.set_title("角色出场率与胜率分布", fontsize=18, pad=12)
    ax.grid(True, alpha=0.3)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=100, facecolor="#f5f7fa")
    plt.close(fig)
    return buf.getvalue()


def render_game_status(rooms: list[dict]) -> list[str]:
    """Render game rooms as markdown tables. Returns one string per room."""
    result: list[str] = []
    for room in rooms:
        room_id = room.get("id", "?")
        turn = room.get("turn", 0)
        play_time = room.get("play_time", 0)
        if turn == 0:
            title = f"房间-{room_id}（未开局）"
        else:
            minutes = round(play_time / 60000)
            title = f"房间-{room_id}（第{turn}回合，已开局{minutes}分钟）"

        players = room.get("players", [])
        header = ["玩家", "角色", "状态", "手牌", "情报"]
        rows: list[list[str]] = []
        for p in players:
            alive = p.get("alive", True)
            is_turn = p.get("is_turn", False)
            status = "已死亡" if not alive else ("回合" if is_turn else "")
            mc = p.get("message_cards") or []
            msg_str = f"红:{mc[1]} 蓝:{mc[2]} 黑:{mc[0]}" if len(mc) >= 3 else ""
            rows.append([p.get("name", ""), p.get("role_name", ""), status, str(p.get("cards", "")), msg_str])

        result.append(title + _render_table(header, rows))

    return result
