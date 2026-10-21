"""MCP 探针：摸清工具的真实入参和返回结构。

拿到 Token 后第一件事就跑这个。它会把 tools/list 的完整 schema 和一组
只读工具的返回样本落到 data/probe/（已 gitignore，不会外泄）。

    export MCD_MCP_TOKEN=xxx
    export PROBE_CITY=上海市
    export PROBE_ADDRESS="上海市徐汇区虹桥路1号"
    python src/probe.py

    python src/probe.py --schema-only     # 只看 schema，不调用任何工具
    python src/probe.py --only campaign-calendar query-my-coupons
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from mcp_client import McdMCPClient, MCPError  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "probe"

# 只读、不产生任何订单或消耗的工具，可以放心探测
SAFE_TOOLS = [
    "now-time-info",
    "campaign-calendar",
    "list-nutrition-foods",
    "query-my-account",
    "query-my-coupons",
    "available-coupons",
    "mall-points-products",
    "query-lottery-info",
    "query-my-prizes",
    "order-list",
    "query-nearby-stores",
    "delivery-query-addresses",
]

# 按参数名猜默认值，降低第一次探测的失败率
GUESS = {
    "city": os.environ.get("PROBE_CITY", "上海市"),
    "cityname": os.environ.get("PROBE_CITY", "上海市"),
    "address": os.environ.get("PROBE_ADDRESS", "上海市徐汇区虹桥路1号"),
    "page": 1,
    "pageindex": 1,
    "pageno": 1,
    "pagesize": 10,
    "size": 10,
    "limit": 10,
    "count": 10,
    "type": "",
    "keyword": "",
}


def guess_arg(name: str, schema: dict[str, Any]) -> Any:
    low = name.lower()
    if low in GUESS:
        return GUESS[low]
    for key, val in GUESS.items():
        if key in low:
            return val
    enum = schema.get("enum")
    if enum:
        return enum[0]
    typ = schema.get("type")
    if typ == "integer" or typ == "number":
        return 1
    if typ == "boolean":
        return False
    if typ == "array":
        return []
    return ""


def build_args(schema: dict[str, Any], overrides: dict[str, str]) -> tuple[dict[str, Any], list[str]]:
    props = schema.get("properties", {}) or {}
    required = schema.get("required", []) or []
    args: dict[str, Any] = {}
    missing: list[str] = []
    for key in required:
        if key in overrides:
            args[key] = overrides[key]
        elif key in props:
            val = guess_arg(key, props[key])
            if val == "" or val is None:
                missing.append(key)
            args[key] = val
        else:
            args[key] = ""
            missing.append(key)
    return args, missing


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", nargs="*", default=None)
    parser.add_argument("--schema-only", action="store_true")
    parser.add_argument("--arg", nargs="*", default=[], help="k=v 覆盖，如 storeCode=12345")
    opts = parser.parse_args()

    overrides = dict(item.split("=", 1) for item in opts.arg if "=" in item)

    try:
        cli = McdMCPClient()
        info = cli.initialize()
    except MCPError as exc:
        print(f"[FATAL] {exc}")
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[OK] 已连接 {info.get('serverInfo', {})}")
    print(f"[OK] protocolVersion={info.get('protocolVersion')}")

    tools = cli.list_tools()
    (OUT_DIR / "_tools.json").write_text(
        json.dumps(tools, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[OK] tools/list -> {len(tools)} 个工具，schema 已存 _tools.json\n")

    by_name = {t["name"]: t for t in tools}
    targets = opts.only or SAFE_TOOLS

    if opts.schema_only:
        for name in targets:
            tool = by_name.get(name)
            if not tool:
                print(f"  {name:<28} 不在工具列表里")
                continue
            schema = tool.get("inputSchema", {})
            req = schema.get("required", [])
            print(f"  {name:<28} required={req}")
            print(f"     {tool.get('description', '')[:100]}")
        return 0

    print(f"{'工具':<28} {'结果'}")
    print("-" * 72)
    for name in targets:
        tool = by_name.get(name)
        if not tool:
            print(f"{name:<28} 不在工具列表里")
            continue
        args, missing = build_args(tool.get("inputSchema", {}) or {}, overrides)
        note = f"  (缺参数: {','.join(missing)})" if missing else ""
        try:
            result = cli.call_raw(name, args)
            (OUT_DIR / f"{name}.json").write_text(
                json.dumps({"args": args, "result": result}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            text = " | ".join(
                p.get("text", "")[:120]
                for p in result.get("content", [])
                if isinstance(p, dict) and p.get("type") == "text"
            )
            status = "ERR " if result.get("isError") else "OK  "
            print(f"{name:<28} {status} {text[:80]}{note}")
        except MCPError as exc:
            print(f"{name:<28} FAIL {str(exc)[:70]}{note}")
        except Exception:  # noqa: BLE001
            print(f"{name:<28} EXC  {traceback.format_exc().splitlines()[-1][:70]}")

    print(f"\n原始返回已存到 {OUT_DIR}")
    print("注意：这些文件可能含你的账户/券/订单信息，已被 .gitignore 排除，请勿提交。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
