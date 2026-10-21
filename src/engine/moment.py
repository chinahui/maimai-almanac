"""天时：判断今天是不是一个「日子」。

黄历的第一问不是「我有什么」，是「今天是什么日子」。
但 campaign-calendar 返回的十几条活动里，大部分是长期在跑的常规促销，
不构成「日子」。要挑的是**今天独有**的那一条。

挑法就是择日的逻辑：

    第 N 弹 / 限量周边 / 联名  >  上新  >  常规促销  >  什么都没有

挑出主场之后还得算两件事，天时才有推进感：

    1. 它开售几天了 —— 在售第几日，黄历里的「值日」
    2. 下一波什么时候换 —— 明日换气

没有这两条，天时就只是一个活动标题，读者不知道自己在时间轴的哪儿。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

# 波次是「日子」的最强信号：第几弹 = 第几波，天然带时间边界
WAVE = re.compile(r"第\s*[一二三四五六七八九十\d]+\s*[弹波批]")
LIMITED = ("联名", "周边", "限量", "珍藏", "同款", "徽章", "手办", "套装")
FRESH = ("上新", "回归", "首推", "上市", "新品", "全新", "登场")
ROUTINE = ("套餐", "优惠", "折扣", "立减", "仅需", "低至", "搭配", "任意")
ADDON = re.compile(r"加\s*(\d+(?:\.\d+)?)\s*元即可得")

# 营销词逐条清掉。不清的话，标题会变成「第三周周边即将开售限定主题丝巾」这种断句。
MARKETING = (
    "即将开售",
    "即将",
    "正式发售",
    "正式开售",
    "震撼来袭",
    "酷爽",
    "来啦",
    "上新",
    "登场",
    "回归",
    "上线",
    "开售",
    "开抢",
)

# 「10月15日10:45」「10月8日 10:30」都可能出现，时刻可缺
POINT = re.compile(r"(\d{1,2})\s*月\s*(\d{1,2})\s*日(?:\s*(\d{1,2})\s*[:：]\s*(\d{2}))?")

EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF\uFE0F\u2640-\u2642]+"
)

# 开售后这么久之内，仍然算「刚开售」，值得提醒
FRESH_WINDOW = 2


@dataclass
class Moment:
    """今日天时。"""

    kind: str = "平常日"  # 发售期 / 上新期 / 促销期 / 平常日
    head: str = ""  # 主场事件，压到一行
    clock: str = ""  # 「10月15日 10:45 开售」
    note: str = ""  # 「加 ¥39.9 可得」
    elapsed: int | None = None  # 开售至今第几日，0 表示今天
    others: list[str] = field(default_factory=list)  # 同场其余活动主题
    count: int = 0  # 今日活动总数

    @property
    def badge(self) -> str:
        """左上角那行小字：今天在时间轴的哪儿。"""
        if self.elapsed is None:
            return self.kind
        if self.elapsed == 0:
            return "今日开售"
        if self.elapsed <= FRESH_WINDOW:
            return f"{self.kind} · 第 {self.elapsed + 1} 日"
        return f"{self.kind} · 第 {self.elapsed + 1} 日"

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "head": self.head,
            "clock": self.clock,
            "note": self.note,
            "elapsed": self.elapsed,
            "others": self.others,
            "count": self.count,
            "badge": self.badge,
        }


def _clean(text: str) -> str:
    return EMOJI.sub("", text or "").strip()


def _points(body: str, today: date) -> list[tuple[date, str]]:
    """抠出正文里所有「M月D日 [H:MM]」，换算成具体日期。

    只有月日没有年，跨年时按「超过 180 天就算去年」倒推——
    日历窗口本身只有十几天，这个粗判足够。
    """
    out: list[tuple[date, str]] = []
    for m in POINT.finditer(body or ""):
        mo, dd, hh, mi = m.groups()
        try:
            d = date(today.year, int(mo), int(dd))
        except ValueError:
            continue  # 2月30日这种脏数据，直接丢
        if (d - today).days > 180:
            d = date(today.year - 1, int(mo), int(dd))
        if hh:
            out.append((d, f"{int(mo)}月{int(dd)}日 {int(hh):02d}:{mi} 开售"))
        else:
            out.append((d, ""))
    return out


def _score(act: dict[str, Any]) -> float:
    """一条活动有多像「日子」。"""
    title = _clean(act.get("title", ""))
    body = _clean(act.get("body", ""))
    blob = title + body

    s = 0.0
    if WAVE.search(blob):
        s += 45
    limited = sum(1 for w in LIMITED if w in blob)
    s += min(limited, 3) * 12
    if any(w in blob for w in FRESH):
        s += 20
    if any(w in blob for w in ROUTINE):
        s -= 15
    if ADDON.search(body):
        s += 10
    return s


def _core(title: str, limit: int = 14) -> str:
    """标题压成一行主线。

    两件事：先把「一口爆汁！蓝莓麦旋风」里的营销前半句扔掉，
    再清掉「即将开售」这类尾巴，最后截断。
    """
    t = _clean(title)
    t = re.sub(r"^麦当劳\s*[Xx×]\s*", "", t)
    t = re.sub(r"^麦当劳", "", t)

    # 感叹号在这里是分隔符：前半句是吆喝，后半句才是产品名
    if "！" in t or "!" in t:
        tail = re.split(r"[！!]", t, maxsplit=1)[1].strip()
        if len(tail) >= 4:
            t = tail

    for w in MARKETING:
        t = t.replace(w, "")

    # "韩式蘸酱就「酱」心有所「薯」"——引号里是玩梗，不是信息，连尾巴一起砍
    t = re.sub(r"就?\s*「[^」]*」.*$", "", t)
    t = re.sub(r"[—–]{2,}", " · ", t)
    t = re.sub(r"[！!，,。]+", "·", t)
    t = re.sub(r"·{2,}", "·", t)
    t = t.strip(" ·-")
    return t[:limit]


def _headline(title: str, body: str) -> str:
    """主场事件的一句话。

    正文第一行往往比标题更准确——标题是栏目名（"麦当劳 X PEACEMINUSONE"），
    正文第一行才是今天发生的具体事（"周边第二弹——联名徽章正式发售"）。
    """
    first = _clean((body or "").strip().split("\n")[0])
    if 6 <= len(first) <= 24 and (WAVE.search(first) or any(w in first for w in LIMITED)):
        return _core(first, 16)
    return _core(title, 14) or "今日无新事"


def build_moment(today: date, calendar: dict[str, Any]) -> Moment:
    """从今日活动里挑出主场的那个日子。"""
    entry = calendar.get(today.isoformat()) or {}
    acts = entry.get("activities") or []
    m = Moment(count=len(acts))
    if not acts:
        return m

    # 同一联名会以不同标题重复出现（"联名棒球帽" / "联名徽章"），
    # 按标题去重后再比，避免同一件事占满「同场」。
    seen: set[str] = set()
    uniq = []
    for a in acts:
        key = _core(a.get("title", ""), 20)
        if key and key not in seen:
            seen.add(key)
            uniq.append(a)

    ranked = sorted(uniq, key=_score, reverse=True)
    top = ranked[0]
    m.head = _headline(top.get("title", ""), top.get("body", ""))

    blob = f"{top.get('title', '')}{top.get('body', '')}"
    pts = _points(blob, today)

    # 已开售的取最近一次，未开售的不算「在售」
    past = [p for p in pts if p[0] <= today]
    if past:
        opened, clock = max(past)
        m.elapsed = (today - opened).days
        m.clock = clock or f"{opened.month}月{opened.day}日 开售"

    addon = ADDON.search(blob)
    if addon:
        m.note = f"加 ¥{addon.group(1)} 可得"

    has_wave = bool(WAVE.search(blob))
    has_limited = any(w in blob for w in LIMITED)
    if has_wave or has_limited:
        m.kind = "发售期" if m.elapsed is not None else "预告"
    elif any(w in blob for w in FRESH):
        m.kind = "上新期"
    else:
        m.kind = "促销期"

    m.others = [_core(a.get("title", ""), 10) for a in ranked[1:4]]
    return m


def next_wave(today: date, calendar: dict[str, Any], stop: int = 30) -> str:
    """下一波换气：几天后、哪一天、什么主题。

    和 verdict 里那段 countdown 的区别是这里只认「新主题」，
    老活动换个说法继续跑不算换气。
    """
    today_key = today.isoformat()
    today_titles = {
        _core(a.get("title", ""), 20)
        for a in (calendar.get(today_key, {}).get("activities") or [])
    }
    for day, entry in sorted(calendar.items()):
        if day <= today_key:
            continue
        gap = (date.fromisoformat(day) - today).days
        if gap > stop:
            break
        fresh = [
            a
            for a in (entry.get("activities") or [])
            if _core(a.get("title", ""), 20) not in today_titles
        ]
        if fresh:
            head = _core(fresh[0].get("title", ""), 12)
            if gap == 0:
                return f"今日 · {head}"
            return f"{gap} 天后 · {day[5:]} · {head}"
    return ""
