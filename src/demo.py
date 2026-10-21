"""生成脱敏示例卡片。

真实卡片里有券名、积分余额、过期积分，属于个人信息，不能对外传播。
这个脚本用一组合成数据渲染同样版式，只用于 README、朋友圈、评审预览。

数据刻意与真实账户不同，并且底栏标注「示例数据」，避免误导。
判决逻辑与真实运行完全一致，只是输入换成了假账户。
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from engine.moment import Moment  # noqa: E402
from engine.verdict import Finding, Verdict, ganzhi_year  # noqa: E402
from render.pixel import render_html  # noqa: E402

WEEKDAYS = "一二三四五六日"


def build_demo() -> Verdict:
    today = date.today()
    v = Verdict(
        day=today.isoformat(),
        weekday="周" + WEEKDAYS[today.weekday()],
        ganzhi=ganzhi_year(today.year) + "年",
    )
    v.yi = [
        Finding("清券", "「麦辣鸡腿堡」券只剩 1 天，过期即归零", "query-my-coupons", 90),
        Finding("兑换", "50 分换 ¥6.9 派，每分 0.138 元，是基准的 2.5 倍", "mall-points-products", 70),
    ]
    v.ji = [
        Finding("囤券", "3 张券都在 1 天内到期，别再领新的", "query-my-coupons", 80),
        Finding("加购", "「联名周边」要加 ¥39.9 才得，非必需就别凑", "campaign-calendar", 45),
    ]
    v.slots = {"券": "3 张 · 剩 1 天", "分": "1250", "腐": "已蒸发 480 分"}
    v.moment = Moment(
        kind="发售期",
        head="周边第二弹 · 联名徽章",
        clock="10月15日 10:45 开售",
        note="加 ¥39.9 可得",
        elapsed=6,
        others=["蓝莓爆爆珠麦旋风", "灰焰圆筒", "韩式蘸酱"],
        count=14,
    )
    v.headline = v.moment.head
    v.motto = "先清券，再兑换。今日不宜囤。"
    v.countdown = "1 天后 · 10-22 · 第三周周边开售"
    v.worst = Finding(
        "硬换",
        "800 分只换到 ¥21.9 组合，每分 0.027 元，只有最优档的 20%",
        "mall-points-products",
        60,
    )
    return v


def main() -> int:
    from almanac import ensure_dir, to_png

    out = ROOT / "out"
    ensure_dir(out)

    verdict = build_demo()
    html = render_html(verdict, {"source_note": "示例数据 · 非真实账户"})

    html_path = out / "demo.html"
    html_path.write_text(html, encoding="utf-8")
    print(f"已生成 {html_path}")

    png = out / "demo.png"
    to_png(html_path, png, 1080, 1440)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
