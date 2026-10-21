"""像素风手机卡片。

设计目标和竖排版完全不同：

    竖排版 = 桌面阅读 / 海报感 / 信息全
    像素版 = 手机屏幕 / 一眼看完 / 信息砍到三层

手机上的硬约束是「一张图看 3 秒」，所以这里只保留三层：
    1. 宜什么、忌什么（最大，占上半屏）
    2. 券还剩几天、积分还有多少（数字）
    3. 一句判词

尺寸取 1080×1440（3:4），和手机相册、朋友圈、小红书的默认竖图比例一致，
发出去不会被裁掉两边。

配色取麦当劳官方：红 #DA291C、黄 #FFC72C、深棕 #27251F。
像素感靠三件事堆出来，不靠字体：
    硬边框（无圆角）+ 阶梯硬阴影 + 点阵底纹。
中文没有好的像素字体，硬套会变成马赛克糊字，所以正文用苹方粗体保证可读，
像素只做「界面语言」。
"""

from __future__ import annotations

import html
import re
from typing import Any

from engine.verdict import Verdict, chinese_day

W, H = 1080, 1440

RED = "#DA291C"
YELLOW = "#FFC72C"
DARK = "#27251F"
CREAM = "#FFF8E7"
CREAM_DEEP = "#FFEFC8"
WHITE = "#FFFFFF"
MUTED = "#7A7367"

EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF\uFE0F\u2640-\u2642]+"
)

MONTH_CN = ["", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十", "十一", "十二"]

# 8-bit 金拱门：7 列点阵，手工排的，缩放到任何尺寸都是硬边
M_GLYPH = [
    "1000001",
    "1100011",
    "1110111",
    "1101011",
    "1100011",
    "1100011",
    "1100011",
]

# 8-bit 汉堡：面包 / 生菜 / 肉 / 面包，四层色带。纯装饰，用来补「卡通」这一口气
BURGER_GLYPH = [
    "..PPPP..",
    ".PPPPPP.",
    "PPPPPPPP",
    "GGGGGGGG",
    "MMMMMMMM",
    ".PPPPPP.",
]


def _e(text: Any) -> str:
    return html.escape(str(text or ""))


def _clean(text: Any, limit: int | None = None) -> str:
    out = EMOJI.sub("", str(text or "")).strip()
    out = re.sub(r"\s{2,}", " ", out)
    return out[:limit] if limit else out


def _pixels(rows: list[str], palette: dict[str, str], cell: float) -> str:
    """把字符点阵翻译成 SVG 方块。字符 . 表示透明。"""
    rects = []
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            color = palette.get(ch)
            if not color:
                continue
            rects.append(
                f'<rect x="{x * cell:.2f}" y="{y * cell:.2f}" '
                f'width="{cell:.2f}" height="{cell:.2f}" fill="{color}"/>'
            )
    return "".join(rects)


def _pixel_m(size: int = 62, color: str = YELLOW) -> str:
    cell = size / 7
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" '
        f'shape-rendering="crispEdges" xmlns="http://www.w3.org/2000/svg">'
        + _pixels(M_GLYPH, {"1": color}, cell)
        + "</svg>"
    )


def _pixel_burger(width: int = 40) -> str:
    cell = width / 8
    h = cell * len(BURGER_GLYPH)
    palette = {"P": "#E8A33D", "G": "#5A9E45", "M": "#6B3E20"}
    return (
        f'<svg width="{width}" height="{h:.1f}" viewBox="0 0 {width} {h:.1f}" '
        f'shape-rendering="crispEdges" xmlns="http://www.w3.org/2000/svg">'
        + _pixels(BURGER_GLYPH, palette, cell)
        + "</svg>"
    )


def _chips(tags: list[str], tone: str) -> str:
    """每个标签一个像素块，横排。不竖排——手机上竖着读太累。"""
    if not tags:
        return '<div class="chip empty">—</div>'
    return "".join(f'<div class="chip {tone}">{_e(t)}</div>' for t in tags)


def render_html(v: Verdict, meta: dict[str, Any] | None = None) -> str:
    meta = meta or {}

    yi_tags = [_clean(f.tag, 2) for f in v.yi][:2] or ["按兵"]
    ji_tags = [_clean(f.tag, 2) for f in v.ji][:2] or ["造次"]

    # 第一层：天时。今天是什么日子——黄历的第一问，不再是注脚。
    m = v.moment
    head = _clean(m.head or "今日无新事", 18)
    badge = _clean(m.badge or "平常日", 16)
    clock = _clean(m.clock, 20)
    note = _clean(m.note, 14)
    crew = [x for x in (_clean(o, 9) for o in (m.others or [])) if x][:3]

    meta_line = " · ".join(b for b in (clock, note) if b)
    crew_line = f"同场 {m.count} 场 · " + " / ".join(crew) if crew and m.count > 1 else ""

    # 字号跟着字数走：天时标题不能换行，换行就散了。
    # 按「视觉宽度」算——中文 1、英文数字 0.55、空格 0.35，否则中英混排会偏小。
    def _vw(s: str) -> float:
        return sum(0.35 if c.isspace() else 0.55 if c.isascii() else 1.0 for c in s)

    hsize = max(46, min(88, int(930 / max(_vw(head), 1))))

    motto = _clean(v.motto or "按兵不动。", 22)
    # 「最坑」只能占一条窄栏：先把商品名摘掉，只留数字
    worst = _clean(re.sub(r"「[^」]*」", "", v.worst.detail), 40) if v.worst else ""
    worst = worst.replace("只有最优档的", "仅最优档").replace("  ", " ")
    countdown = _clean(v.countdown or "", 26)

    # 最后一层：卦象。账户自己的数字，退成一行注脚，
    # 因为「已蒸发多少」是复盘，不是黄历该抢的位置。
    slots = v.slots or {}
    point_txt = _clean(slots.get("分", "0"), 8)
    coupon_txt = re.sub(r"\s*·\s*剩\s*", "剩 ", _clean(slots.get("券", ""), 12)).strip()
    decay_txt = _clean(slots.get("腐", ""), 12).replace("已蒸发", "").replace("分", "").strip()

    bits = [f"账上 {point_txt} 分"]
    if coupon_txt:
        bits.append(f"券 {coupon_txt}")
    if decay_txt and decay_txt != "无":
        bits.append(f"月内已腐 {decay_txt} 分")
    ledger = "，".join(bits)

    # 每条判断都得能追到工具，这是项目的硬规矩；顺带把底部空白填了
    srcs = sorted(
        {f.source for f in (v.yi + v.ji + ([v.worst] if v.worst else [])) if f.source}
    )
    src_line = f"依据 {' / '.join(srcs)} 判定" if srcs else ""

    # 示例图要标明「非真实账户」，否则容易被当成真实数据传播
    source_note = meta.get("source_note")
    note_html = f'<div class="mark">{_e(source_note)}</div>' if source_note else ""

    gaps = ""
    if v.notes:
        gaps = '<div class="gaps">数据缺口：' + _e("、".join(_clean(n, 10) for n in v.notes)) + "</div>"

    month = int(v.day[5:7])
    day = int(v.day[8:10])

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>麦麦黄历 {_e(v.day)}</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html, body {{ background:{DARK}; margin:0; }}
  body {{ font-family:"PingFang SC","Hiragino Sans GB","Heiti SC",sans-serif;
         -webkit-font-smoothing:antialiased; overflow-x:hidden; }}
  .wrap {{ width:{W}px; height:{H}px; transform-origin:top left; }}
  .page {{ position:relative; width:{W}px; height:{H}px; background:{CREAM};
          display:flex; flex-direction:column; overflow:hidden; }}

  /* 手机浏览器直接打开时整屏缩放，字不会小到看不清。
     阈值 900px 是为了避开截图 viewport（1080），否则出图会被缩放。 */
  @media (max-width:900px) {{
    .wrap {{ transform:scale(calc(100vw / 1080));
             height:calc(100vw * 1440 / 1080); }}
  }}

  /* 点阵底纹：像素感的地基。压到几乎看不见，只负责「不空」 */
  .dots {{ position:absolute; inset:0;
           background-image:radial-gradient({DARK} 2px, transparent 2px);
           background-size:28px 28px; opacity:.065; pointer-events:none; }}

  /* ---------- 顶栏 ---------- */
  .top {{ position:relative; background:{DARK}; padding:30px 40px 26px;
          display:flex; align-items:center; gap:18px; }}
  .logo {{ flex:0 0 auto; background:{RED}; padding:9px; line-height:0;
           box-shadow:5px 5px 0 {YELLOW}; }}
  .top::after {{ content:""; position:absolute; left:0; right:0; bottom:-14px; height:14px;
                 background:{YELLOW}; }}
  .brand {{ flex:1; }}
  .brand .nm {{ font-size:44px; font-weight:800; color:{YELLOW}; letter-spacing:.05em;
                line-height:1.12; }}
  .brand .sub {{ margin-top:6px; font-size:18px; color:#8E897D; letter-spacing:.18em; }}
  .date {{ text-align:right; }}
  .date .d {{ font-size:54px; font-weight:800; color:{WHITE}; line-height:1;
              font-variant-numeric:tabular-nums; }}
  .date .w {{ margin-top:8px; font-size:20px; color:{YELLOW}; letter-spacing:.08em; }}

  /* ---------- 天时区：第一层。今天是什么日子 ---------- */
  .sky {{ position:relative; margin:50px 36px 0; border:7px solid {DARK};
          background:{WHITE}; box-shadow:12px 12px 0 {DARK};
          padding:34px 28px 30px; }}
  .badge {{ display:inline-block; background:{RED}; color:{YELLOW};
            font-size:26px; font-weight:800; padding:8px 15px;
            letter-spacing:.06em; line-height:1.15; }}
  .head {{ margin-top:22px; font-weight:900; color:{DARK}; line-height:1.14;
           letter-spacing:.01em; }}
  .meta {{ margin-top:18px; font-size:26px; font-weight:800; color:{RED}; line-height:1.3; }}
  .crew {{ margin-top:14px; font-size:20px; font-weight:600; color:{MUTED}; line-height:1.4; }}

  /* ---------- 判决区：第二层。天时定了，才轮到宜忌 ---------- */
  .verdict {{ position:relative; display:flex; gap:16px; margin:44px 36px 0; }}
  .box {{ flex:1; min-height:272px; border:7px solid {DARK}; box-shadow:10px 10px 0 {DARK};
          padding:18px 14px 22px; display:flex; flex-direction:column;
          align-items:center; justify-content:center; gap:16px; }}
  .box.yi {{ background:{RED}; }}
  .box.ji {{ background:{YELLOW}; }}
  .box .hd {{ font-size:74px; font-weight:900; line-height:.9; letter-spacing:.02em; }}
  .box.yi .hd {{ color:{YELLOW}; text-shadow:5px 5px 0 {DARK}; }}
  .box.ji .hd {{ color:{DARK}; text-shadow:4px 4px 0 {WHITE}; }}
  .chips {{ display:flex; flex-direction:column; gap:9px; width:100%; }}
  .chip {{ font-size:47px; font-weight:800; text-align:center; padding:11px 4px;
           letter-spacing:.08em; line-height:1.1; }}
  .box.yi .chip {{ background:{YELLOW}; color:{DARK}; }}
  .box.ji .chip {{ background:{DARK}; color:{YELLOW}; }}
  .chip.empty {{ opacity:.45; }}

  /* ---------- 判词：只此一句，不拆碎 ---------- */
  .motto {{ position:relative; margin:34px 36px 0; border:7px solid {DARK};
            background:{YELLOW}; box-shadow:10px 10px 0 {DARK};
            min-height:196px; padding:22px 24px;
            display:flex; align-items:center; justify-content:center; }}
  .motto .q {{ font-size:46px; font-weight:900; color:{DARK}; letter-spacing:.02em;
               line-height:1.34; text-align:center; }}

  /* ---------- 最坑：窄条，只留一行 ---------- */
  .worst {{ position:relative; margin:28px 36px 0; background:{DARK};
            padding:14px 18px; display:flex; gap:12px; align-items:flex-start; }}
  .worst .tag {{ flex:0 0 auto; font-size:18px; font-weight:800; color:{WHITE};
                 background:{RED}; padding:4px 8px; letter-spacing:.06em;
                 line-height:1.2; }}
  .worst .tx {{ font-size:22px; color:{CREAM}; line-height:1.32; font-weight:600; }}

  /* ---------- 卦象：账本退到最后一行 ---------- */
  .ledger {{ position:relative; margin:26px 36px 0; font-size:21px; font-weight:700;
             color:{MUTED}; letter-spacing:.03em; line-height:1.5; }}
  .src-line {{ position:relative; margin:14px 36px 0; font-size:17px; color:#8C8578;
               letter-spacing:.02em; line-height:1.5; }}
  .gaps {{ position:relative; margin:10px 36px 0; font-size:16px; color:#8C8578; }}
  .mark {{ position:relative; margin:auto 36px 0; text-align:center; font-size:16px;
           color:#8C8578; letter-spacing:.1em; padding:16px 0 14px; }}

  /* ---------- 底栏 ---------- */
  .foot {{ position:relative; margin-top:auto; background:{DARK};
           padding:24px 36px; display:flex; align-items:center; gap:14px; }}
  .foot .cd {{ flex:1; font-size:23px; color:{YELLOW}; font-weight:700; }}
  .foot .src {{ font-size:16px; color:#8E897D; letter-spacing:.04em; }}
  .foot .bt {{ flex:0 0 auto; line-height:0; }}
</style></head>
<body><div class="wrap"><div class="page"><div class="dots"></div>

  <div class="top">
    <div class="logo">{_pixel_m(52)}</div>
    <div class="brand">
      <div class="nm">麦麦黄历</div>
      <div class="sub">MAIMAI ALMANAC</div>
    </div>
    <div class="date">
      <div class="d">{month:02d}·{day:02d}</div>
      <div class="w">{_e(v.weekday)} · {MONTH_CN[month]}月{chinese_day(day)}</div>
    </div>
  </div>

  <div class="sky">
    <div class="badge">{_e(badge)}</div>
    <div class="head" style="font-size:{hsize}px">{_e(head)}</div>
    {f'<div class="meta">{_e(meta_line)}</div>' if meta_line else ''}
    {f'<div class="crew">{_e(crew_line)}</div>' if crew_line else ''}
  </div>

  <div class="verdict">
    <div class="box yi">
      <div class="hd">宜</div>
      <div class="chips">{_chips(yi_tags, "yi")}</div>
    </div>
    <div class="box ji">
      <div class="hd">忌</div>
      <div class="chips">{_chips(ji_tags, "ji")}</div>
    </div>
  </div>

  <div class="motto"><div class="q">{_e(motto)}</div></div>

  {f'<div class="worst"><span class="tag">最坑</span><div class="tx">{_e(worst)}</div></div>' if worst else ''}

  <div class="ledger">{_e(ledger)}</div>
  {f'<div class="src-line">{_e(src_line)}</div>' if src_line else ''}
  {gaps}

  {note_html}

  <div class="foot">
    <div class="cd">{_e(countdown) or "日历里没有更近的新事"}</div>
    <div class="bt">{_pixel_burger(46)}</div>
  </div>
</div></div></body></html>"""
