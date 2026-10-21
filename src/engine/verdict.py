"""判决引擎：把资产、活动、价格合成一句「今天该干什么」。

世界观是 decay-first——先处理会归零的东西，再谈最优价格。
一条判决如果没有数字和来源，就不许出现在历书上。
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from datetime import date, datetime, timedelta
from typing import Any

from .moment import Moment, build_moment, next_wave
from .parser import Account, Coupon, Redeem, median_rate

STEMS = "甲乙丙丁戊己庚辛壬癸"
BRANCHES = "子丑寅卯辰巳午未申酉戌亥"
CN_NUM = "〇一二三四五六七八九"
WEEKDAYS = "一二三四五六日"

# 券的腐烂临界：剩这么多天就该动手了
DECAY_DAYS = 3
# 积分兑换率达到基准的这个倍数，才算「花得值」
GOOD_RATE_MULTIPLE = 1.5


@dataclass
class Finding:
    tag: str
    detail: str
    source: str
    weight: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"tag": self.tag, "detail": self.detail, "source": self.source}


@dataclass
class Verdict:
    day: str
    ganzhi: str
    weekday: str
    yi: list[Finding] = field(default_factory=list)
    ji: list[Finding] = field(default_factory=list)
    slots: dict[str, str] = field(default_factory=dict)
    moment: Moment = field(default_factory=Moment)
    headline: str = ""
    countdown: str = ""
    worst: Finding | None = None
    motto: str = ""
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.day,
            "ganzhi": self.ganzhi,
            "weekday": self.weekday,
            "yi": [f.to_dict() for f in self.yi],
            "ji": [f.to_dict() for f in self.ji],
            "slots": self.slots,
            "moment": self.moment.to_dict(),
            "headline": self.headline,
            "countdown": self.countdown,
            "worst": self.worst.to_dict() if self.worst else None,
            "motto": self.motto,
            "notes": self.notes,
        }


def ganzhi_year(year: int) -> str:
    """年干支。1984 为甲子，是用来验算的锚点。"""
    offset = (year - 1984) % 60
    return f"{STEMS[offset % 10]}{BRANCHES[offset % 12]}"


def chinese_day(n: int) -> str:
    """公历日转中文数字。只做排版用，不冒充农历。"""
    if n <= 10:
        return "初" + CN_NUM[n] if n < 10 else "初十"
    if n < 20:
        return "十" + CN_NUM[n - 10]
    if n == 20:
        return "二十"
    if n < 30:
        return "廿" + CN_NUM[n - 20]
    if n == 30:
        return "三十"
    return "三十" + CN_NUM[n - 30] if n > 30 else "三十一"


def _days_until(day: str, today: date) -> int:  # noqa: D103 - 保留给快照回溯用
    return (date.fromisoformat(day) - today).days


def build_verdict(
    today: date,
    account: Account,
    coupons: list[Coupon],
    redeems: list[Redeem],
    calendar: dict[str, Any],
    now: datetime | None = None,
) -> Verdict:
    v = Verdict(
        day=today.isoformat(),
        ganzhi=f"{ganzhi_year(today.year)}年",
        weekday="周" + WEEKDAYS[today.weekday()],
    )

    # ---------- 券：按腐烂程度排序 ----------
    live = [c for c in coupons if (c.days_left is None or c.days_left >= 0)]
    if live:
        soon = sorted(live, key=lambda c: c.days_left if c.days_left is not None else 999)
        first = soon[0]
        left = first.days_left
        if left is not None and left <= DECAY_DAYS:
            price = f"¥{first.price:.1f}" if first.price else ""
            v.yi.append(
                Finding(
                    tag="清券",
                    detail=f"「{first.name}」{price} 只剩 {left} 天，过期即归零",
                    source="query-my-coupons",
                    weight=90 - left * 10,
                )
            )
            if len(live) > 1:
                v.ji.append(
                    Finding(
                        tag="囤券",
                        detail=f"手上的 {len(live)} 张券都在 {soon[-1].days_left} 天内到期，别再领新的",
                        source="query-my-coupons",
                        weight=60,
                    )
                )

    # ---------- 积分：先看有没有在腐烂的 ----------
    if account.expiring_this_month > 0:
        v.yi.append(
            Finding(
                tag="用分",
                detail=f"本月将有 {account.expiring_this_month:g} 积分过期，比任何折扣都急",
                source="query-my-account",
                weight=95,
            )
        )

    # ---------- 积分兑换率：值不值 ----------
    base = median_rate(redeems)
    affordable = [r for r in redeems if r.point <= account.available] if account.available else []
    if base > 0 and affordable:
        best = max(affordable, key=lambda r: r.rate)
        if best.rate >= base * GOOD_RATE_MULTIPLE:
            v.yi.append(
                Finding(
                    tag="兑换",
                    detail=(
                        f"{best.point:g} 分换「{best.name}」（¥{best.cash:g}），"
                        f"每分 {best.rate:.3f} 元，是基准的 {best.rate / base:.1f} 倍"
                    ),
                    source="mall-points-products",
                    weight=70,
                )
            )

    if base > 0 and redeems:
        total = max(redeems, key=lambda r: r.point)
        cheap = min(
            [r for r in redeems if r.point >= total.point * 0.5] or redeems, key=lambda r: r.rate
        )
        v.worst = Finding(
            tag="硬换",
            detail=(
                f"{cheap.point:g} 分只换到 ¥{cheap.cash:g}「{cheap.name}」，"
                f"每分 {cheap.rate:.3f} 元，只有最优档的 {cheap.rate / (best_rate(redeems) or 1):.0%}"
            ),
            source="mall-points-products",
        )
        # 与「今日最坑」重复，不再单列为忌项，避免同一件事说两遍

    # ---------- 天时：今天是不是一个「日子」 ----------
    # 这一层的顺序很重要：先定今天是什么日子，再谈你该做什么。
    today_key = today.isoformat()
    todays = (calendar.get(today_key) or {}).get("activities") or []
    v.moment = build_moment(today, calendar)
    v.headline = v.moment.head or "今日无新事"
    v.countdown = next_wave(today, calendar)

    # ---------- 加价换周边：真实存在的行为陷阱 ----------
    for act in todays:
        blob = f"{act.get('title', '')}{act.get('body', '')}"
        addon = re.search(r"加\s*(\d+(?:\.\d+)?)\s*元即可得", blob)
        if addon:
            v.ji.append(
                Finding(
                    tag="加购",
                    detail=f"「{act.get('title', '')[:12]}」要加 ¥{addon.group(1)} 才得周边，非必需就别凑",
                    source="campaign-calendar",
                    weight=45,
                )
            )
            break

    # ---------- 槽位 ----------
    soon_all = [c for c in live if c.days_left is not None]
    v.slots = {
        "券": f"{len(live)} 张 · 剩 {min(c.days_left for c in soon_all)} 天" if soon_all else f"{len(live)} 张",
        "分": f"{account.available:g}",
        "腐": f"已蒸发 {account.expired:g} 分" if account.expired else "无",
    }

    # ---------- 数据缺口要明说，不许静默 ----------
    if not redeems:
        v.notes.append("积分商城未取到可兑换商品，兑换率维度缺失")
    if not calendar:
        v.notes.append("活动日历为空，等待维度缺失")
    if not live:
        v.notes.append("卡包内无可用券，腐烂维度为空")

    v.yi.sort(key=lambda f: f.weight, reverse=True)
    v.ji.sort(key=lambda f: f.weight, reverse=True)
    v.motto = _compose_motto(v)
    return v


def _compose_motto(v: "Verdict") -> str:
    """把判决压成一句人话。宁可短，不要空。"""
    yi = [f.tag for f in v.yi]
    ji = [f.tag for f in v.ji]
    parts: list[str] = []
    if "清券" in yi:
        parts.append("先清券")
    if "用分" in yi:
        parts.append("再用分")
    elif "兑换" in yi:
        parts.append("再兑换")
    if "囤券" in ji:
        parts.append("今日不宜囤")
    elif "硬换" in ji:
        parts.append("别硬换")
    if not parts:
        if yi:
            parts.append("照常吃")
        else:
            parts.append("按兵不动")
    head = "，".join(parts[:2]) + "。"
    return head + (parts[2] + "。" if len(parts) > 2 else "")


def best_rate(redeems: list[Redeem]) -> float:
    return max((r.rate for r in redeems), default=0.0)
