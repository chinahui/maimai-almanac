"""麦麦黄历 CLI。

    python src/almanac.py today
    python src/almanac.py today --png out/today.png
    python src/almanac.py snapshot
    python src/almanac.py build --out out/
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from engine.calendar import crawl  # noqa: E402
from engine.parser import (  # noqa: E402
    parse_account,
    parse_coupons,
    parse_points_products,
    price_signals,
)
from engine.verdict import build_verdict  # noqa: E402
from mcp_client import McdMCPClient  # noqa: E402


def ensure_dir(path: Path) -> Path:
    """沙箱里 mkdir(exist_ok=True) 对已存在目录会误报，先判断再建。"""
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)
    return path


def load_env() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())


def fetch(client: McdMCPClient, base: date) -> dict:
    """并行取四路数据。任何一路失败都记录，不掩盖。"""
    jobs = {
        "account": ("query-my-account", {}),
        "coupons": ("query-my-coupons", {"page": "1", "pageSize": "200"}),
        "redeems": ("mall-points-products", {}),
    }
    out: dict = {}

    def run(item):
        key, (tool, args) = item
        try:
            return key, client.call(tool, args)
        except Exception as exc:  # noqa: BLE001
            return key, {"__error__": str(exc)}

    with ThreadPoolExecutor(max_workers=4) as pool:
        for key, value in pool.map(run, jobs.items()):
            out[key] = value

    out["calendar"] = {}
    try:
        days = crawl(client, base - timedelta(days=3), base + timedelta(days=14), today=base.isoformat())
        out["calendar"] = {k: v.to_dict() for k, v in days.items()}
    except Exception as exc:  # noqa: BLE001
        out["calendar_error"] = str(exc)

    return out


def collect(client: McdMCPClient, base: date | None = None):
    base = base or date.today()
    raw = fetch(client, base)

    def text_of(key):
        val = raw.get(key)
        if isinstance(val, dict) and "__error__" in val:
            return ""
        if isinstance(val, str):
            return val
        return val

    account = parse_account(text_of("account") or "")
    coupons = parse_coupons(text_of("coupons") or "")
    redeems = parse_points_products(text_of("redeems") or "")
    verdict = build_verdict(base, account, coupons, redeems, raw.get("calendar") or {})
    if raw.get("calendar_error"):
        verdict.notes.append(f"活动日历抓取失败：{raw['calendar_error'][:40]}")
    if isinstance(raw.get("account"), dict) and "__error__" in raw["account"]:
        verdict.notes.append("积分账户未取到")
    return verdict, {"account": account, "coupons": coupons, "redeems": redeems, "calendar": raw}


def card_meta(verdict, bundle) -> dict:
    """给渲染层准备活动清单：标题 + 文案里能抠到的最低价。"""
    entry = ((bundle.get("calendar") or {}).get("calendar") or {}).get(verdict.day) or {}
    acts = entry.get("activities") or []
    rows, seen = [], set()
    for act in acts:
        title = act.get("title", "")
        if title in seen:
            continue
        seen.add(title)
        rows.append({"title": title, "kind": activity_kind(act)})

    cal = (bundle.get("calendar") or {}).get("calendar") or {}
    today = date.fromisoformat(verdict.day)
    timeline = []
    for offset in range(7):
        day = today + timedelta(days=offset)
        key = day.isoformat()
        entry = cal.get(key) or {}
        count = len({a.get("title") for a in (entry.get("activities") or [])})
        timeline.append(
            {
                "day": day.day,
                "week": "一二三四五六日"[day.weekday()],
                "count": count,
                "today": offset == 0,
            }
        )
    return {"activities": rows, "activity_total": len(rows), "timeline": timeline}


def activity_kind(act: dict) -> str:
    """给活动贴一个业务类型。比从文案里抽价格可靠得多。"""
    body = act.get("body", "") or ""
    title = act.get("title", "") or ""
    blob = title + body
    if "即可得" in blob or "加购" in blob or "周边" in blob:
        return "周边"
    if "派对" in blob or "生日" in blob:
        return "派对"
    if "卡" in blob and ("元" in blob and "天" in blob):
        return "会员卡"
    if "上新" in blob or "新品" in blob or "开售" in blob:
        return "新品"
    if "折" in blob or "起" in blob:
        return "优惠"
    return "活动"


def print_verdict(v) -> None:
    print()
    print(f"  {v.ganzhi} · {v.day} · {v.weekday}")
    print("  " + "─" * 58)
    print("  宜  " + "　".join(f.tag for f in v.yi) if v.yi else "  宜  —")
    print("  忌  " + "　".join(f.tag for f in v.ji) if v.ji else "  忌  —")
    print("  " + "─" * 58)
    for item in v.yi:
        print(f"   + {item.detail}")
        print(f"     └ {item.source}")
    for item in v.ji:
        print(f"   - {item.detail}")
        print(f"     └ {item.source}")
    print("  " + "─" * 58)
    print("  " + "  ".join(f"{k} {val}" for k, val in v.slots.items()))
    if v.worst:
        print(f"  最坑  {v.worst.detail}")
    if v.countdown:
        print(f"  倒计时  {v.countdown}")
    for note in v.notes:
        print(f"  ! {note}")
    print()


STYLES = {
    # 名字: (模块, 宽, 高)
    "pixel": ("render.pixel", 1080, 1620),
    "classic": ("render.card", 1080, 1440),
}


def load_renderer(style: str):
    import importlib

    module, w, h = STYLES[style]
    return importlib.import_module(module).render_html, w, h


def to_png(html_path: Path, png_path: Path, width: int = 1080, height: int = 1620) -> bool:
    """优先用 Node 版 Playwright 截图（浏览器已在本地缓存），没有则提示。"""
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        print("未找到 node，无法出图")
        return False
    shot = Path(__file__).resolve().parent / "render" / "shot.mjs"
    env = dict(os.environ)
    env.setdefault(
        "NODE_PATH", "/Users/mac/.workbuddy/binaries/node/workspace/node_modules"
    )
    ensure_dir(png_path.parent)
    proc = subprocess.run(
        [
            node,
            str(shot),
            str(html_path.resolve()),
            str(png_path.resolve()),
            str(width),
            str(height),
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    if proc.returncode != 0:
        print("出图失败：", (proc.stderr or proc.stdout).strip()[:300])
        print("排查：确认已 npm i playwright 并 playwright install chromium")
        return False
    print(f"已出图 {png_path}")
    return True


def main() -> int:
    load_env()
    parser = argparse.ArgumentParser(prog="almanac")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_today = sub.add_parser("today", help="出今天的黄历")
    p_today.add_argument("--png", help="导出 PNG 路径")
    p_today.add_argument("--html", help="导出 HTML 路径")
    p_today.add_argument("--json", action="store_true", help="输出 JSON")
    p_today.add_argument(
        "--style",
        default="pixel",
        choices=sorted(STYLES),
        help="卡片风格：pixel=像素竖屏（默认），classic=竖排宣纸",
    )

    sub.add_parser("snapshot", help="归档今日快照")

    p_build = sub.add_parser("build", help="生成静态页")
    p_build.add_argument("--out", default="out")

    args = parser.parse_args()
    client = McdMCPClient()
    client.initialize()
    verdict, bundle = collect(client)

    if args.cmd == "today":
        if args.json:
            print(json.dumps(verdict.to_dict(), ensure_ascii=False, indent=2))
            return 0
        print_verdict(verdict)
        if args.html or args.png:
            render_html, cw, ch = load_renderer(args.style)

            out = ROOT / "out"
            ensure_dir(out)
            html_path = Path(args.html) if args.html else out / f"today-{args.style}.html"
            ensure_dir(html_path.parent)
            html_path.write_text(render_html(verdict, card_meta(verdict, bundle)), encoding="utf-8")
            print(f"已生成 {html_path}")
            if args.png:
                png = Path(args.png)
                to_png(html_path, png, cw, ch)
        return 0

    if args.cmd == "snapshot":
        folder = ROOT / "data" / "snapshots"
        ensure_dir(folder)
        payload = {
            "date": verdict.day,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "verdict": verdict.to_dict(),
            "account": {
                "available": bundle["account"].available,
                "expired": bundle["account"].expired,
                "expiring_this_month": bundle["account"].expiring_this_month,
            },
            "coupons": [
                {"name": c.name, "price": c.price, "end": c.end.isoformat() if c.end else None}
                for c in bundle["coupons"]
            ],
            "redeem_rates": sorted(
                ({"name": r.name, "point": r.point, "cash": r.cash, "rate": round(r.rate, 4)}
                 for r in bundle["redeems"]),
                key=lambda r: -r["rate"],
            ),
            "calendar": bundle["calendar"].get("calendar", {}),
        }
        target = folder / f"{verdict.day}.json"
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已归档 {target}")
        return 0

    if args.cmd == "build":
        render_html, _, _ = load_renderer("pixel")

        out = ROOT / args.out
        ensure_dir(out)
        (out / "index.html").write_text(
            render_html(verdict, card_meta(verdict, bundle)), encoding="utf-8"
        )
        print(f"已生成 {out / 'index.html'}")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
