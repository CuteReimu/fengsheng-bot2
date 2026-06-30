from __future__ import annotations

import io
from pathlib import Path

import httpx
import yaml
from nonebot import get_driver
from nonebot.adapters import Event
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


async def _get_result(path: str, params: dict | None = None) -> any:
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
    return (await _get_result(path, params)).get("result", bytes())


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

_FONT_SIZE = 15
_PAD_X = 10
_PAD_Y = 7
_HEADER_BG = (68, 114, 196)
_HEADER_FG = (255, 255, 255)
_ROW_BG = [(255, 255, 255), (240, 244, 251)]
_ROW_FG = (30, 30, 30)
_BORDER = (190, 190, 190)

_font_cache: dict[int, object] = {}


def _get_font(size: int):
    if size in _font_cache:
        return _font_cache[size]
    from PIL import ImageFont

    font = None
    for search_root in [Path("."), Path("/usr/share/fonts")]:
        if search_root.is_dir():
            for p in search_root.rglob("simhei.ttf"):
                try:
                    font = ImageFont.truetype(str(p), size)
                    break
                except Exception:
                    pass
        if font is not None:
            break

    if font is None:
        font = ImageFont.load_default()
    _font_cache[size] = font
    return font


def _render_table(header: list[str], rows: list[list[str]], width: int) -> bytes:
    from PIL import Image, ImageDraw

    font = _get_font(_FONT_SIZE)
    row_h = _FONT_SIZE + _PAD_Y * 2
    n_cols = len(header)
    col_w = width // n_cols
    height = (len(rows) + 1) * row_h + 1

    img = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    def _draw_row(y: int, cells: list[str], bg: tuple, fg: tuple) -> None:
        draw.rectangle([0, y, width - 1, y + row_h - 1], fill=bg)
        for i, cell in enumerate(cells[:n_cols]):
            draw.text((_PAD_X + i * col_w, y + _PAD_Y), cell, font=font, fill=fg)

    _draw_row(0, header, _HEADER_BG, _HEADER_FG)
    for r, row in enumerate(rows):
        _draw_row((r + 1) * row_h, row, _ROW_BG[r % 2], _ROW_FG)

    for r in range(len(rows) + 2):
        y = r * row_h
        draw.line([0, y, width - 1, y], fill=_BORDER)
    for c in range(n_cols + 1):
        x = c * col_w
        if c == n_cols:
            x = width - 1
        draw.line([x, 0, x, height - 1], fill=_BORDER)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


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

    imgs: list[bytes] = []
    if win_rate_rows:
        imgs.append(_render_table(["身份", "胜率", "平均胜率", "场次"], win_rate_rows, 440))
    if history_rows:
        imgs.append(_render_table(["角色", "存活", "身份", "胜负", "段位", "分数"], history_rows, 720))

    return "".join(header_parts).strip(), imgs
