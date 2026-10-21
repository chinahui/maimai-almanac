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

    # 三个数字：券 / 分 / 蒸发。顺序就是决策顺序，不能换。
    slots = v.slots or {}
    coupon_txt = _clean(slots.get("券", "—"), 12)
    point_txt = _clean(slots.get("分", "—"), 8)
    decay_txt = _clean(slots.get("腐", "—"), 14).replace("已蒸发", "").replace("分", "").strip()

    # 券这格最要紧：把「剩 X 天」拆出来做大字，张数退到副行
    days = re.search(r"剩\s*(\d+)\s*天", coupon_txt)
    count = re.search(r"(\d+)\s*张", coupon_txt)
    if days:
        coupon_label = "券到期"
        coupon_main = f'<span class="big">{days.group(1)}</span><span class="unit">天</span>'
    else:
        coupon_label = "可用券"
        coupon_main = f'<span class="mid">{_e(coupon_txt)}</span>'
    coupon_sub = f"{count.group(1)} 张在用" if count else ""

    motto = _clean(v.motto or "按兵不动。", 22)
    worst = _clean(v.worst.detail, 52) if v.worst else ""
    countdown = _clean(v.countdown or "", 24)

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

  /* ---------- 判决区：整张图的主角 ---------- */
  .verdict {{ position:relative; display:flex; gap:18px; padding:54px 36px 0; }}
  .box {{ flex:1; min-height:372px; border:7px solid {DARK}; box-shadow:12px 12px 0 {DARK};
          padding:24px 16px 26px; display:flex; flex-direction:column;
          align-items:center; justify-content:center; gap:18px; }}
  .box.yi {{ background:{RED}; }}
  .box.ji {{ background:{YELLOW}; }}
  .box .hd {{ font-size:92px; font-weight:900; line-height:.9; letter-spacing:.02em; }}
  .box.yi .hd {{ color:{YELLOW}; text-shadow:5px 5px 0 {DARK}; }}
  .box.ji .hd {{ color:{DARK}; text-shadow:4px 4px 0 {WHITE}; }}
  .chips {{ display:flex; flex-direction:column; gap:10px; width:100%; }}
  .chip {{ font-size:50px; font-weight:800; text-align:center; padding:14px 4px;
           letter-spacing:.08em; line-height:1.1; }}
  .box.yi .chip {{ background:{YELLOW}; color:{DARK}; }}
  .box.ji .chip {{ background:{DARK}; color:{YELLOW}; }}
  .chip.empty {{ opacity:.45; }}

  /* ---------- 数字条 ---------- */
  .nums {{ position:relative; margin:52px 36px 0; border:7px solid {DARK};
           background:{WHITE}; box-shadow:12px 12px 0 {DARK};
           display:flex; min-height:258px; }}
  .num {{ flex:1; padding:20px 8px; text-align:center;
          display:flex; flex-direction:column; justify-content:center; }}
  .num + .num {{ border-left:5px solid {DARK}; }}
  .num .lb {{ font-size:20px; color:{MUTED}; letter-spacing:.12em; font-weight:700; }}
  .num .vl {{ margin-top:14px; font-size:48px; font-weight:900; color:{DARK};
              line-height:1; font-variant-numeric:tabular-nums;
              display:flex; align-items:baseline; justify-content:center; }}
  .num .vl.hot {{ color:{RED}; }}
  .num .big {{ font-size:72px; }}
  .num .unit {{ font-size:28px; margin-left:3px; }}
  .num .mid {{ font-size:36px; }}
  .num .sub {{ margin-top:9px; font-size:22px; color:{MUTED}; font-weight:700; }}
  /* 「已蒸发」是这张图最该被看见的数字，单独加深 */
  .num .gone {{ color:{RED}; }}

  /* ---------- 判词：整块黄底菜单牌，只此一句，不拆碎 ---------- */
  .motto {{ position:relative; margin:50px 36px 0; border:7px solid {DARK};
            background:{YELLOW}; box-shadow:12px 12px 0 {DARK};
            min-height:186px; padding:24px 26px;
            display:flex; align-items:center; justify-content:center; }}
  .motto .q {{ font-size:50px; font-weight:900; color:{DARK}; letter-spacing:.02em;
               line-height:1.32; text-align:center; }}

  /* ---------- 最坑 ---------- */
  .worst {{ position:relative; margin:34px 36px 0; background:{DARK};
            padding:20px 22px; display:flex; gap:14px; align-items:flex-start; }}
  .worst .tag {{ flex:0 0 auto; font-size:19px; font-weight:800; color:{WHITE};
                 background:{RED}; padding:5px 9px; letter-spacing:.06em;
                 line-height:1.2; }}
  .worst .tx {{ font-size:25px; color:{CREAM}; line-height:1.42; font-weight:600; }}
  .gaps {{ position:relative; margin:12px 36px 0; font-size:17px; color:#8C8578; }}
  .mark {{ position:relative; margin:auto 36px 0; text-align:center; font-size:16px;
           color:#8C8578; letter-spacing:.1em; padding-bottom:14px; }}

  /* ---------- 底栏 ---------- */
  .foot {{ position:relative; margin-top:auto; background:{DARK};
           padding:24px 36px; display:flex; align-items:center; gap:14px; }}
  .foot .cd {{ flex:1; font-size:24px; color:{YELLOW}; font-weight:700; }}
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

  <div class="nums">
    <div class="num">
      <div class="lb">{coupon_label}</div>
      <div class="vl hot">{coupon_main}</div>
      <div class="sub">{coupon_sub}</div>
    </div>
    <div class="num">
      <div class="lb">可用积分</div>
      <div class="vl"><span class="mid">{_e(point_txt)}</span><span class="unit">分</span></div>
      <div class="sub">在账上</div>
    </div>
    <div class="num">
      <div class="lb">已蒸发</div>
      <div class="vl gone"><span class="mid">{_e(decay_txt or "0")}</span><span class="unit">分</span></div>
      <div class="sub">忘掉的</div>
    </div>
  </div>

  <div class="motto"><div class="q">{_e(motto)}</div></div>

  {f'<div class="worst"><span class="tag">最坑</span><div class="tx">{_e(worst)}</div></div>' if worst else ''}
  {gaps}

  {note_html}

  <div class="foot">
    <div class="cd">{_e(countdown) or "今天没有更近的活动"}</div>
    <div class="bt">{_pixel_burger(46)}</div>
  </div>
</div></div></body></html>"""
