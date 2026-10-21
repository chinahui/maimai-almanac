"""把 MCP 的各种返回格式统一成结构化对象。

MCP 的返回有三种形态：
1. 纯 markdown 表格/列表（query-my-coupons、campaign-calendar）
2. markdown 说明 + `## Original Response` 里的原始 JSON（账户、积分商城、抽奖）
3. 一段说明文字

这里用同一套入口吃掉它们，上层不用关心格式差异。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

DATE_TIME = re.compile(r"(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})")
# 排除「0.33 元/天」这类折算价，它不是一份餐品的真实价格
MONEY = re.compile(r"(\d+(?:\.\d+)?)\s*元(?!\s*[/／]\s*[天日])")
DISCOUNT = re.compile(r"([\d.]+)\s*折")


# ---------- 通用 ----------

def extract_json(text: str) -> Any | None:
    """从 markdown 里抠出第一段完整的 JSON 对象。"""
    if not isinstance(text, str):
        return text
    start = text.find('{"success"')
    if start < 0:
        start = text.find("## Original Response")
        if start >= 0:
            start = text.find("{", start)
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def to_text(result: Any) -> str:
    """MCP 的 call_raw 结果 → 纯文本。"""
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        parts = result.get("content") or []
        return "\n".join(
            p.get("text", "") for p in parts if isinstance(p, dict) and p.get("type") == "text"
        )
    return ""


def _dt(raw: str) -> datetime | None:
    m = DATE_TIME.search(raw or "")
    if not m:
        return None
    try:
        return datetime.strptime(f"{m.group(1)} {m.group(2)}", "%Y-%m-%d %H:%M")
    except ValueError:
        return None


# ---------- 券 ----------

@dataclass
class Coupon:
    name: str
    price: float | None = None
    start: datetime | None = None
    end: datetime | None = None
    tags: list[str] = field(default_factory=list)

    @property
    def days_left(self) -> int | None:
        if not self.end:
            return None
        return (self.end.date() - datetime.now().date()).days

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "price": self.price,
            "start": self.start.isoformat() if self.start else None,
            "end": self.end.isoformat() if self.end else None,
            "tags": self.tags,
            "days_left": self.days_left,
        }


def parse_coupons(text: str) -> list[Coupon]:
    """query-my-coupons 是纯 markdown，按 `## 券名` 分段。"""
    coupons: list[Coupon] = []
    blocks = re.split(r"^##[ \t]+(?!#)", text or "", flags=re.M)
    for block in blocks[1:]:
        lines = block.strip().splitlines()
        if not lines:
            continue
        name = lines[0].strip()
        if not name or name.startswith("#"):
            continue
        coupon = Coupon(name=name)
        money = re.search(r"\*\*优惠\*\*[:：]\s*¥?\s*(\d+(?:\.\d+)?)", block)
        if money:
            coupon.price = float(money.group(1))
        period = re.search(r"\*\*有效期\*\*[:：]\s*(.+)", block)
        if period:
            stamps = DATE_TIME.findall(period.group(1))
            if stamps:
                coupon.start = datetime.strptime(" ".join(stamps[0]), "%Y-%m-%d %H:%M")
                if len(stamps) > 1:
                    coupon.end = datetime.strptime(" ".join(stamps[1]), "%Y-%m-%d %H:%M")
        tags = re.search(r"\*\*标签\*\*[:：]\s*(.+)", block)
        if tags:
            coupon.tags = [t.strip() for t in re.split(r"[、,，]", tags.group(1)) if t.strip()]
        coupons.append(coupon)
    return coupons


# ---------- 积分 ----------

@dataclass
class Account:
    available: float = 0.0
    accumulative: float = 0.0
    expired: float = 0.0
    frozen: float = 0.0
    used: float = 0.0
    expiring_this_month: float = 0.0
    expiring_next_month: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def parse_account(text: str) -> Account:
    obj = extract_json(text) or {}
    data = obj.get("data") or {}

    def num(key: str) -> float:
        try:
            return float(str(data.get(key) or 0))
        except ValueError:
            return 0.0

    return Account(
        available=num("availablePoint"),
        accumulative=num("accumulativePoint"),
        expired=num("expiredPoint"),
        frozen=num("frozenPoint"),
        used=num("usedPoint"),
        expiring_this_month=num("currentMouthExpirePoint"),
        expiring_next_month=num("nextMouthExpirePoint"),
    )


@dataclass
class Redeem:
    name: str
    point: float
    cash: float
    cat: str = ""
    status: int = 0
    down_time: str = ""

    @property
    def rate(self) -> float:
        """每 1 积分换到的面值（元）。越高越划算。"""
        return self.cash / self.point if self.point else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "point": self.point,
            "cash": self.cash,
            "cat": self.cat,
            "rate": round(self.rate, 4),
            "down_time": self.down_time,
        }


def parse_points_products(text: str, now: datetime | None = None) -> list[Redeem]:
    """只要「用积分换商品券」那类；现金商品（point=0）不算积分资产。

    两个必须绕开的坑：
    1. 积分商品的 price 字段是 0，真实面值只写在名称里（「18.8元2份麦辣鸡翅」）。
    2. MCP 会把已下架的商品继续以 status=2（上架）返回，
       必须用 downTime 自己判过期，否则会推荐一个几个月前就失效的商品。
    """
    now = now or datetime.now()
    obj = extract_json(text) or {}
    rows = obj.get("data") or []
    items: list[Redeem] = []
    for row in rows:
        name = str(row.get("spuName") or "").strip()
        try:
            point = float(str(row.get("point") or 0))
            cash = float(str(row.get("price") or 0))
        except ValueError:
            continue
        if point <= 0:
            continue
        if cash <= 0:
            found = MONEY.search(name)
            if not found:
                continue
            cash = float(found.group(1))
        down_time = str(row.get("downTime") or "")
        if down_time and _dt(down_time) and _dt(down_time) <= now:
            continue
        items.append(
            Redeem(
                name=name,
                point=point,
                cash=cash,
                cat=str(row.get("catName") or ""),
                status=int(row.get("status") or 0),
                down_time=down_time,
            )
        )
    return items


def median_rate(items: list[Redeem]) -> float:
    rates = sorted(i.rate for i in items if i.rate > 0)
    if not rates:
        return 0.0
    mid = len(rates) // 2
    return rates[mid] if len(rates) % 2 else (rates[mid - 1] + rates[mid]) / 2


# ---------- 活动里的价格情报 ----------

def price_signals(body: str) -> dict[str, Any]:
    """从活动文案里抽价格与折扣。"""
    text = (body or "").replace("\n", " ")
    prices = [float(p) for p in MONEY.findall(text)]
    discounts = [float(d) for d in DISCOUNT.findall(text)]
    return {
        "prices": prices,
        "first_price": prices[0] if prices else None,
        "min_price": min(prices) if prices else None,
        "discounts": discounts,
        "has_gift_threshold": "加" in text and "元即可得" in text,
    }
