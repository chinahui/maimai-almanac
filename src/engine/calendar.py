"""活动日历的解析与抓取。

MCP 的 campaign-calendar 返回的是给人看的 markdown，不是 JSON。
这里做两件事：

1. 把 markdown 解析成结构化活动记录
2. 用 specifiedDate 作为锚点沿时间线爬行，去重合并成完整日历

实测时间线窗口很窄（约 15 天，过去不可回溯），所以「历史周期律」不存在，
只能靠每日快照慢慢攒。这个限制是硬约束，不要试图用推测绕过。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Iterable

DAY_HEADER = re.compile(r"^####[ \t]*(\d{4})年(\d{1,2})月(\d{1,2})日[ \t]*(.*)$", re.M)
TITLE = re.compile(r"\*\*活动标题\*\*[：:]\s*(.+)")
CONTENT = re.compile(r"\*\*活动内容介绍\*\*[：:]\s*([\s\S]*?)(?=\*\*活动图片介绍\*\*|\Z)")
IMAGE = re.compile(r'<img\s+src="([^"]+)"')

STATUS_PAST = {"往期回顾", "往期", "已结束"}
STATUS_TODAY = {"今日"}
STATUS_FUTURE = {"即将开始", "未来", "待开始", "敬请期待"}


@dataclass
class Activity:
    title: str
    body: str = ""
    image: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"title": self.title, "body": self.body, "image": self.image}


@dataclass
class ActivityDay:
    day: str
    status: str = ""
    activities: list[Activity] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.day,
            "status": self.status,
            "activities": [a.to_dict() for a in self.activities],
        }


def classify(raw: str) -> str:
    raw = raw.strip()
    if raw in STATUS_PAST or "往期" in raw:
        return "past"
    if raw in STATUS_TODAY or "今日" in raw:
        return "today"
    if raw in STATUS_FUTURE or "即将" in raw or "未来" in raw:
        return "future"
    return "scheduled"


def parse_calendar(text: str, today: str | None = None) -> list[ActivityDay]:
    """把 campaign-calendar 的 markdown 拆成按天分组的活动。"""
    if not text:
        return []
    marks = list(DAY_HEADER.finditer(text))
    days: list[ActivityDay] = []
    for idx, mark in enumerate(marks):
        y, m, d, raw_status = mark.groups()
        day = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
        end = marks[idx + 1].start() if idx + 1 < len(marks) else len(text)
        block = text[mark.end() : end]
        days.append(
            ActivityDay(
                day=day,
                status=classify(raw_status) or _status_by_date(day, today),
                activities=_parse_block(block),
            )
        )
    return days


def _status_by_date(day: str, today: str | None) -> str:
    if not today:
        return "scheduled"
    if day < today:
        return "past"
    if day == today:
        return "today"
    return "future"


def _parse_block(block: str) -> list[Activity]:
    titles = list(TITLE.finditer(block))
    items: list[Activity] = []
    for i, tm in enumerate(titles):
        end = titles[i + 1].start() if i + 1 < len(titles) else len(block)
        chunk = block[tm.end() : end]
        body_match = CONTENT.search(chunk)
        body = body_match.group(1).strip() if body_match else ""
        body = re.sub(r"\n{3,}", "\n", body).strip()
        img_match = IMAGE.search(chunk)
        items.append(
            Activity(
                title=tm.group(1).strip().rstrip("*").strip(),
                body=body,
                image=img_match.group(1) if img_match else "",
            )
        )
    return items


def crawl(
    client: Any,
    start: date,
    end: date,
    today: str | None = None,
    progress: bool = False,
) -> dict[str, ActivityDay]:
    """沿时间线爬行。

    每次请求返回「锚点日 + 前后最近的活动日」，所以逐日推进即可覆盖整个窗口。
    同一 (日期, 标题) 只保留第一次出现的版本。
    """
    merged: dict[str, ActivityDay] = {}
    cursor = start
    while cursor <= end:
        anchor = cursor.isoformat()
        try:
            text = client.call("campaign-calendar", {"specifiedDate": anchor})
        except Exception as exc:  # noqa: BLE001
            if progress:
                print(f"  {anchor} 失败：{exc}")
            cursor += timedelta(days=1)
            continue
        if isinstance(text, str):
            for day in parse_calendar(text, today=today):
                slot = merged.setdefault(day.day, ActivityDay(day=day.day, status=day.status))
                if day.status in ("today", "future", "past"):
                    slot.status = day.status
                seen = {a.title for a in slot.activities}
                slot.activities.extend(a for a in day.activities if a.title not in seen)
        if progress and anchor.endswith(("01", "15")):
            print(f"  ...{anchor} 累计 {len(merged)} 天")
        cursor += timedelta(days=1)
    return dict(sorted(merged.items()))


def summarize(days: Iterable[ActivityDay]) -> dict[str, Any]:
    days = list(days)
    return {
        "activity_days": len(days),
        "activity_count": sum(len(d.activities) for d in days),
        "first": days[0].day if days else None,
        "last": days[-1].day if days else None,
    }
