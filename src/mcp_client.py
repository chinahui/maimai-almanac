"""麦当劳 MCP 最小客户端。

只用标准库实现 Streamable HTTP + JSON-RPC，方便任何人 clone 下来直接跑，
不需要装 SDK。

用法：
    from mcp_client import McdMCPClient
    cli = McdMCPClient()
    cli.initialize()
    print(cli.list_tools())
    print(cli.call("campaign-calendar", {}))
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from typing import Any

DEFAULT_URL = "https://mcp.mcd.cn"
PROTOCOL_VERSION = "2025-06-18"
CLIENT_INFO = {"name": "maimai-almanac", "version": "0.1.0"}


class MCPError(RuntimeError):
    """MCP 调用失败。"""


class McdMCPClient:
    def __init__(self, token: str | None = None, url: str = DEFAULT_URL, timeout: int = 30):
        self.token = token or os.environ.get("MCD_MCP_TOKEN", "").strip()
        if not self.token:
            raise MCPError("缺少 MCP Token，请先设置环境变量 MCD_MCP_TOKEN")
        self.url = url.rstrip("/")
        self.timeout = timeout
        self.session_id: str | None = None
        self._seq = 0
        self._initialized = False
        # 同一 Token 下并发请求会串号，所有往返必须串行化
        self._lock = threading.RLock()

    # ---------- 传输层 ----------

    def _post(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {self.token}",
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id

        last_err: Exception | None = None
        for attempt in range(4):
            req = urllib.request.Request(self.url, data=body, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    sid = resp.headers.get("Mcp-Session-Id")
                    if sid:
                        self.session_id = sid
                    raw = resp.read().decode("utf-8", "replace")
                    return self._decode(raw, resp.headers.get("Content-Type", ""))
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "replace")[:400]
                if exc.code == 429:
                    last_err = MCPError(f"触发限流(429)：{detail}")
                    time.sleep(2**attempt)
                    continue
                if exc.code == 401:
                    raise MCPError(f"MCP Token 无效或已过期(401)：{detail}") from exc
                raise MCPError(f"HTTP {exc.code}：{detail}") from exc
            except urllib.error.URLError as exc:
                last_err = exc
                time.sleep(1 + attempt)
        raise MCPError(f"请求失败：{last_err}")

    @staticmethod
    def _decode(raw: str, content_type: str) -> dict[str, Any] | None:
        raw = raw.strip()
        if not raw:
            return None
        if "text/event-stream" in content_type or raw.startswith(("event:", "data:", "id:")):
            messages: list[dict[str, Any]] = []
            for block in raw.split("\n\n"):
                data = "\n".join(
                    line[5:].lstrip() for line in block.splitlines() if line.startswith("data:")
                )
                if not data:
                    continue
                try:
                    messages.append(json.loads(data))
                except json.JSONDecodeError:
                    continue
            for msg in messages:
                if "result" in msg or "error" in msg:
                    return msg
            return messages[-1] if messages else None
        return json.loads(raw)

    def _rpc(self, method: str, params: dict[str, Any] | None = None) -> Any:
        with self._lock:
            self._seq += 1
            reply = self._post(
                {"jsonrpc": "2.0", "id": self._seq, "method": method, "params": params or {}}
            )
        if reply is None:
            raise MCPError(f"{method} 没有返回内容")
        if "error" in reply:
            raise MCPError(f"{method} 失败：{reply['error']}")
        return reply.get("result", {})

    # ---------- 协议层 ----------

    def initialize(self) -> dict[str, Any]:
        with self._lock:
            result = self._rpc(
                "initialize",
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": CLIENT_INFO,
                },
            )
            self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self._initialized = True
        return result

    def list_tools(self) -> list[dict[str, Any]]:
        if not self._initialized:
            self.initialize()
        return self._rpc("tools/list").get("tools", [])

    def call_raw(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self._initialized:
            self.initialize()
        return self._rpc("tools/call", {"name": name, "arguments": arguments or {}})

    def call(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        """调用工具并把 text content 解析成 Python 对象。"""
        result = self.call_raw(name, arguments)
        texts = [
            part.get("text", "")
            for part in result.get("content", [])
            if isinstance(part, dict) and part.get("type") == "text"
        ]
        joined = "\n".join(t for t in texts if t).strip()
        if not joined:
            return result
        try:
            return json.loads(joined)
        except json.JSONDecodeError:
            return joined
