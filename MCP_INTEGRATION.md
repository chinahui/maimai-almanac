# MCP 接入说明

## Server

| 项 | 值 |
|---|---|
| 接入地址 | `https://mcp.mcd.cn` |
| 传输协议 | Streamable HTTP |
| 认证 | 请求头 `Authorization: Bearer <MCD_MCP_TOKEN>` |
| 限流 | 600 次/分钟，超限返回 429 |
| 工具总数 | 35（实测） |
| 范围 | 中国大陆（不含港澳台） |

Token 申请：[open.mcd.cn/mcp](https://open.mcd.cn/mcp) → 手机号登录 → 控制台 → 激活。

配置示例见 [`mcp-config.example.json`](mcp-config.example.json)。**仓库内不含任何真实 Token**，
Token 一律通过环境变量 `MCD_MCP_TOKEN` 注入，`.env` 已在 `.gitignore` 中。

## 实际使用的 Tool

本项目全部为**只读**调用，不创建订单、不消耗积分、不触发抽奖、不领券。

| Tool | 在项目中的角色 | 关键字段 |
|---|---|---|
| `campaign-calendar` | 活动时间线：今日在跑什么、未来哪天有活动 | `specifiedDate` 入参；返回按天分组的 markdown |
| `query-my-coupons` | 卡包资产：券面价与有效期 | `有效期` 起止时间、`优惠`、`标签` |
| `query-my-account` | 积分资产：可用 / 已过期 / 即将过期 | `availablePoint`、`expiredPoint`、`currentMouthExpirePoint` |
| `mall-points-products` | 积分兑换率基准：全商城兑换效率 | `spuName`、`point`、`price`、`downTime`、`status` |

### 设计但尚未接入

以下工具在当前 v0.1 判决中**未使用**，列出以免误解：

| Tool | 计划用途 |
|---|---|
| `query-meals` / `query-meal-detail` | 拉门店在售 SKU，构成可比较的商品集合 |
| `calculate-price` | 对同一商品分别按无券 / 各券试算，得到精确价差 |
| `query-store-coupons` | 券与商品编码的绑定关系（券只对特定 `productCode` 生效） |
| `now-time-info` | 服务器时间基准（当前用本地时间，误差可接受） |

## 调用流程

```
① campaign-calendar（爬行）
     以 specifiedDate 为锚点逐日推进。
     每次返回「锚点日 + 时间线上前后最近的有活动日」，逐日走完即可覆盖整个窗口。
     实测窗口 ≈ 2026-10-20 ~ 11-03，窗口外查询返回空。

② query-my-coupons / query-my-account / mall-points-products（并行）
     三路同时取，客户端用 RLock 串行化底层往返（并发会串号）。

③ engine：decay-first + 兑换率
     券的剩余天数        → 腐烂压力（≤3 天进「宜」）
     积分兑换率 vs 中位数  → 花得值不值（≥1.5 倍才进「宜」）
     活动文案中的加价门槛  → 「忌·加购」
     合成 宜 / 忌 / 槽位 / 今日最坑 / 判词

④ 快照归档
     data/snapshots/<date>.json，券码/订单号/地址一律不落盘，只留聚合量

⑤ 渲染
     终端文本 / 竖排历书 PNG（1080×1440）/ 静态页
```

## 数据质量：三个必须绕开的坑

这三条是本项目最主要的工程工作量，也是「为什么不能直接把 MCP 返回喂给模型」的答案。

### ① 已下架商品仍标记为上架

`mall-points-products` 返回的 19 个积分商品中，**12 个 `downTime` 已过期**
（最早 `2026-03-21`），`status` 却全部为 `2`（上架）。

若直接按 `status` 过滤，会推荐一个七个月前失效的商品，且它的兑换率
（0.376 元/分）恰好是全表最高——错得极具说服力。

> 处理：只信 `downTime > now`。

### ② 积分商品面值不在 `price` 字段

积分商品的 `price` 恒为 `0`，真实面值只出现在名称里（`18.8元2份麦辣鸡翅`）。
不解析名称，所有兑换率都会算成 0。

> 处理：`price` 为 0 时从 `spuName` 提取「X 元」。

### ③ 返回格式不统一

- `campaign-calendar`、`query-my-coupons`：纯 markdown，需按标题分段解析
- `query-my-account`、`mall-points-products`、`query-lottery-info`：markdown 说明 +
  `## Original Response` 里的原始 JSON

> 处理：`extract_json()` 做括号配平抠 JSON，失败则回落到 markdown 解析器。

### 附：活动文案里的价格不可直接当商品价

文案常混入非商品价格（`0.33元/天` 的会员卡日均价、权益描述里的 `9.9元麦咖啡`）。
直接取最小值会得出「今日最低 ¥0.33」这种荒唐结论。

> 处理：排除 `/天` 折算价；卡片上不再展示按活动抽取的价格，改用业务类型标签（周边 / 新品 / 会员卡）。

## 错误处理

| 码 | 含义 | 项目内的处理 |
|---|---|---|
| 401 | Token 无效或过期 | 直接失败并提示重新激活，不重试 |
| 429 | 超限流 | 指数退避重试（2s / 4s / 8s），最多 3 次 |
| 其它 | — | 该数据源降级为空，判决中标注「该维度缺失」 |

降级是硬要求：**任何一路数据缺失，历书必须显式说明，而不是假装算过。**
卡片底部有专门的「数据缺口」行，只在该维度真的缺失时出现。

## 业务价值

1. **把「券过期」从确定损失变成可拦截事件** —— 对用户是直接省钱，对品牌是券核销率提升
2. **提升活动曝光** —— 判决提到「1 天后丝巾开售」，等于把 campaign-calendar 推到用户眼前
3. **积分体系健康度** —— 兑换率基准线让用户理解积分的真实价值，减少「攒着不用」的沉默流失
4. **高频触点** —— 每日一张历书，把低频点餐变成每日一次的轻互动

## 合规

- 只读，不产生任何交易副作用
- 不存储券码、订单号、收货地址等个人数据；快照仅保留聚合统计量
- 探针原始返回写入 `data/probe/`，已 gitignore，避免个人信息进入公开仓库
- 不提供营养或医疗建议
- 抽奖仅计算期望值，措辞中性
- 项目非麦当劳官方产品，输出以官方渠道实时结果为准
