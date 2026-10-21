"""竖排历书卡片。

刻意做得像一页真的历书：纸色、双线框、印章红、宋体竖排。
但每一个字都是账本算出来的，不是抄来的黄历。
"""

from __future__ import annotations

import html
import re
from typing import Any

# 卡片上不出现 emoji：宋体渲染成黑白方块，很难看
EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF\uFE0F\u2640-\u2642]+"
)


def _clean(text: Any, limit: int | None = None) -> str:
    out = EMOJI.sub("", str(text or "")).strip()
    out = re.sub(r"\s{2,}", " ", out)
    return out[:limit] if limit else out

from engine.verdict import Verdict, chinese_day

W, H = 1080, 1440

PAPER = "#F6F1E4"
PAPER_DEEP = "#EFE7D3"
INK = "#2B2622"
INK_SOFT = "#6B6257"
SEAL = "#A63A2E"
GOLD = "#B08A4A"
RULE = "#4A4238"

MONTH_CN = ["", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十", "十一", "十二"]


def _e(text: Any) -> str:
    return html.escape(str(text or ""))


def _tags(items: list[str], tone: str) -> str:
    """每个标签独立成列，标签内逐字堆叠。

    不用 writing-mode：竖排的换行行为依赖盒高，在 flex 里不可预测，
    一个字一个 div 反而稳定。
    """
    cls = "yi" if tone == "yi" else "ji"
    cols = "".join(
        f'<div class="tag {cls}">' + "".join(f"<i>{_e(ch)}</i>" for ch in t) + "</div>"
        for t in items
    )
    return f'<div class="tags">{cols}</div>'


def render_html(v: Verdict, meta: dict[str, Any] | None = None) -> str:
    meta = meta or {}
    activities = meta.get("activities") or []

    yi_tags = [f.tag for f in v.yi][:3] or ["按兵"]
    ji_tags = [f.tag for f in v.ji][:3] or ["造次"]

    findings = []
    for item in (v.yi + v.ji)[:5]:
        is_yi = item in v.yi
        findings.append(
            f'<div class="note"><span class="note-idx {"yi" if is_yi else "ji"}">'
            f'{"宜" if is_yi else "忌"}</span>'
            f'<span class="note-text">{_e(item.detail)}</span>'
            f'<span class="note-src">{_e(item.source)}</span></div>'
        )

    slots = "".join(
        f'<div class="slot"><span class="slot-k">{_e(k)}</span>'
        f'<span class="slot-v">{_e(val)}</span></div>'
        for k, val in (v.slots or {}).items()
    )

    act_html = ""
    if activities:
        rows = []
        for act in activities[:3]:
            title = _clean(act.get("title", ""), 24)
            kind = _clean(act.get("kind", ""), 6)
            rows.append(
                f'<div class="act"><span class="act-t">{_e(title)}</span>'
                f'<span class="act-p">{_e(kind)}</span></div>'
            )
        total = meta.get("activity_total") or len(activities)
        act_html = (
            f'<div class="acts"><div class="acts-head">今日在跑 · {total} 场，取前三</div>'
            + "".join(rows)
            + "</div>"
        )

    timeline = meta.get("timeline") or []
    tl_html = ""
    if timeline:
        cells = []
        for cell in timeline:
            on = "on" if cell["count"] else ""
            today = "today" if cell["today"] else ""
            badge = f'<span class="tl-n">{cell["count"]}</span>' if cell["count"] else ""
            cells.append(
                f'<div class="tl-cell {on} {today}">'
                f'<span class="tl-d">{cell["day"]}</span>'
                f'<i class="tl-dot"></i>'
                f'<span class="tl-w">{cell["week"]}</span>{badge}</div>'
            )
        tl_html = (
            '<div class="tl"><div class="tl-head">未来七日 · 有活动的日子</div>'
            f'<div class="tl-row">{"".join(cells)}</div></div>'
        )

    worst = ""
    if v.worst:
        worst = f'<div class="worst"><span>今日最坑</span>{_e(v.worst.detail)}</div>'

    notes = ""
    if v.notes:
        notes = '<div class="gaps">数据缺口 · ' + "；".join(_e(n) for n in v.notes) + "</div>"

    month = int(v.day[5:7])
    day = int(v.day[8:10])
    countdown = _clean(v.countdown or v.headline or "", 30)

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ width:{W}px; height:{H}px; background:{PAPER}; overflow:hidden;
         font-family:"Songti SC","STSong","Source Han Serif SC",serif; }}
  .page {{ position:relative; width:{W}px; height:{H}px; background:{PAPER}; }}
  .frame {{ position:absolute; inset:28px; border:3px solid {RULE}; }}
  .frame::after {{ content:""; position:absolute; inset:7px; border:1px solid {RULE}; opacity:.5; }}
  .inner {{ position:relative; height:100%; display:flex; flex-direction:column;
            padding:52px 60px 58px; }}
  .top {{ display:flex; justify-content:space-between; align-items:flex-start; }}
  .ganzhi {{ font-size:31px; letter-spacing:.22em; color:{INK}; }}
  .solar {{ font-size:18px; color:{INK_SOFT}; letter-spacing:.16em; margin-top:12px; }}
  .seal {{ width:96px; height:96px; border:2.5px solid {SEAL}; border-radius:5px;
           display:grid; grid-template-columns:1fr 1fr; grid-template-rows:1fr 1fr;
           place-items:center; color:{SEAL}; font-size:23px; line-height:1;
           letter-spacing:0; padding:8px; }}
  .seal span {{ display:block; }}
  .title {{ margin-top:26px; text-align:center; }}
  .title h1 {{ font-size:80px; font-weight:400; letter-spacing:.34em; color:{INK};
               text-indent:.34em; line-height:1.1; }}
  .title .sub {{ margin-top:10px; font-size:15px; letter-spacing:.46em; color:{GOLD};
                 text-indent:.46em; }}
  .rule {{ margin:22px 0 18px; height:0; border-top:1.5px solid {RULE}; position:relative; }}
  .rule::after {{ content:""; position:absolute; left:0; right:0; top:4px;
                  border-top:1px solid {RULE}; opacity:.35; }}
  .cols {{ display:flex; justify-content:space-between; align-items:flex-start;
           min-height:236px; }}
  .col {{ display:flex; flex-direction:column; align-items:center; gap:14px; }}
  .col-head {{ font-size:37px; letter-spacing:.06em; }}
  .col.yi .col-head {{ color:{SEAL}; }}
  .col.ji .col-head {{ color:{INK_SOFT}; }}
  .tags {{ display:flex; flex-direction:row-reverse; align-items:flex-start;
           gap:18px; height:auto; }}
  .col {{ flex:0 0 auto; }}
  .tag {{ display:flex; flex-direction:column; align-items:center; gap:5px;
          font-size:37px; line-height:1.06; flex:0 0 auto; }}
  .tag i {{ font-style:normal; display:block; }}
  .tag.yi {{ color:{SEAL}; }}
  .tag.ji {{ color:{INK_SOFT}; }}
  .slots {{ display:flex; flex-direction:column; justify-content:center; gap:15px;
            height:200px; padding-left:34px; border-left:1px solid rgba(74,66,56,.25); }}
  .slot {{ display:flex; align-items:center; gap:11px; }}
  .slot-k {{ font-size:15px; color:{GOLD}; border:1px solid {GOLD}; width:25px; height:25px;
             display:flex; align-items:center; justify-content:center; border-radius:3px;
             flex:0 0 auto; }}
  .slot-v {{ font-size:18px; color:{INK}; letter-spacing:.03em; white-space:nowrap; }}
  .notes {{ margin-top:14px; display:flex; flex-direction:column; }}
  .note {{ display:flex; align-items:baseline; gap:12px; font-size:19px; line-height:1.55;
           color:{INK}; border-bottom:1px dotted rgba(74,66,56,.28); padding:12px 0; }}
  .note-idx {{ font-size:14px; flex:0 0 auto; border:1px solid currentColor; border-radius:2px;
               padding:1px 5px; }}
  .note-idx.yi {{ color:{SEAL}; }}
  .note-idx.ji {{ color:{INK_SOFT}; }}
  .note-text {{ flex:1; }}
  .note-src {{ font-size:11px; color:{INK_SOFT}; opacity:.75;
               font-family:ui-monospace,"SF Mono",monospace; flex:0 0 auto; }}
  .acts {{ margin-top:20px; background:{PAPER_DEEP}; padding:20px 22px; }}
  .acts-head {{ font-size:13px; color:{GOLD}; letter-spacing:.2em; margin-bottom:10px; }}
  .act {{ display:flex; justify-content:space-between; gap:16px; font-size:16px;
          color:{INK}; padding:5px 0; }}
  .act-t {{ white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
  .act-p {{ color:{SEAL}; flex:0 0 auto; }}
  .worst {{ margin-top:22px; background:{PAPER_DEEP}; padding:15px 20px; font-size:17.5px;
            color:{INK}; border-left:4px solid {SEAL}; line-height:1.5; }}
  .worst span {{ color:{SEAL}; margin-right:12px; font-size:15px; letter-spacing:.1em; }}
  .gaps {{ margin-top:10px; font-size:12.5px; color:{INK_SOFT}; opacity:.8; }}
  .tl {{ margin-top:18px; }}
  .tl-head {{ font-size:13px; color:{GOLD}; letter-spacing:.2em; margin-bottom:12px; }}
  .tl-row {{ display:flex; justify-content:space-between; align-items:flex-start;
             border-top:1px solid rgba(74,66,56,.22); padding-top:14px; }}
  .tl-cell {{ display:flex; flex-direction:column; align-items:center; gap:7px;
              flex:1; position:relative; }}
  .tl-d {{ font-size:19px; color:{INK_SOFT}; }}
  .tl-dot {{ width:9px; height:9px; border-radius:50%; background:transparent;
             border:1px solid rgba(74,66,56,.35); display:block; }}
  .tl-cell.on .tl-dot {{ background:{SEAL}; border-color:{SEAL}; }}
  .tl-cell.on .tl-d {{ color:{INK}; }}
  .tl-cell.today .tl-d {{ color:{SEAL}; font-size:21px; }}
  .tl-w {{ font-size:12px; color:{INK_SOFT}; }}
  .tl-n {{ font-size:11.5px; color:{SEAL}; letter-spacing:.04em; }}
  .motto {{ margin-top:auto; padding-top:16px; text-align:center; font-size:30px; color:{INK};
            letter-spacing:.14em; line-height:1.6; }}
  .motto::before {{ content:"「"; color:{GOLD}; }}
  .motto::after {{ content:"」"; color:{GOLD}; }}
  .foot {{ margin-top:18px; padding-top:0; display:flex; justify-content:space-between;
           align-items:flex-end; font-size:13.5px; color:{INK_SOFT}; letter-spacing:.06em;
           gap:20px; }}
  .count {{ font-size:16.5px; color:{INK}; flex:1; }}
  .src {{ flex:0 0 auto; }}
</style></head>
<body><div class="page"><div class="frame"></div>
  <div class="inner">
    <div class="top">
      <div>
        <div class="ganzhi">{_e(v.ganzhi)} · {MONTH_CN[month]}月 · {chinese_day(day)}</div>
        <div class="solar">{_e(v.day)} · {_e(v.weekday)}</div>
      </div>
      <div class="seal"><span>麦</span><span>麦</span><span>黄</span><span>历</span></div>
    </div>

    <div class="title">
      <h1>今日判</h1>
      <div class="sub">DAILY VERDICT</div>
    </div>

    <div class="rule"></div>

    <div class="cols">
      <div class="col yi">
        <div class="col-head">宜</div>{_tags(yi_tags, "yi")}
      </div>
      <div class="col ji">
        <div class="col-head">忌</div>{_tags(ji_tags, "ji")}
      </div>
      <div class="slots">{slots}</div>
    </div>

    <div class="notes">{"".join(findings)}</div>
    {act_html}
    {tl_html}
    {worst}
    {notes}
    <div class="motto">{_e(v.motto or "")}</div>

    <div class="foot">
      <div class="count">{_e(countdown)}</div>
      <div class="src">据 campaign-calendar 等 4 个 MCP 工具</div>
    </div>
  </div>
</div></body></html>"""
