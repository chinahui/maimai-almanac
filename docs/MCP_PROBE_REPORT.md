# MCD MCP 实测报告

> 实测时间：2026-10-21 11:53，账号：个人测试账号，全部为只读调用（未下单、未取消，仅有「领券」以外无副作用操作）。
> **本报告已隐去全部账户数值与券名**，只保留字段结构与结论。
> 环境：`https://mcp.mcd.cn`，Streamable HTTP，`Authorization: Bearer <token>`。

## 1. 连通性

| 项 | 结果 |
|---|---|
| initialize | 200，`serverInfo = mcd-mcp v1.0.0`，`protocolVersion 2025-03-26`，capabilities 仅 `tools`（无 resources/prompts） |
| tools/list | **35 个工具**，全部带 `inputSchema` + `outputSchema` |
| 鉴权格式 | **必须带 `Bearer ` 前缀**。裸 token → `403 / code 400003 校验鉴权authToken必填!`；缺头 → `403 / code 0001 系统错误` |
| 传输特征 | 无状态，单次 POST 即可，无 `Mcp-Session-Id` 回传要求 |

## 2. 逐个验证结果

| 工具 | 结论 | 关键实测数据 |
|---|---|---|
| `now-time-info` | ✅ | 返回 12 个时间字段（date / datetime / dayOfWeek / timestamp / timezone …），服务器时间与本地一致 |
| `query-my-account` | ✅ | 6 个字段：可用 / 累计 / 已过期 / 已用 / 冻结 / 本月将过期；**值均为字符串**，含 1 位小数 |
| `query-my-coupons` | ✅ | 返回券名 / 面额 / `tradeDateTime`（精确到分）/「到店专用 · 外送专用」标签 + COS 签名图 URL。**无分页参数，一次返回全部持有券** |
| `available-coupons` | ✅ | 返回「已领取」/「可领取」两种状态。**能查到尚未领取的券**，这是纯 Agent 玩法里少见的钩子 |
| `query-nearby-stores` | ✅ | `searchType=1` 直接读收藏门店，无需经纬度：广州宝山大厦餐厅 `storeCode=1400037`，`reservation=true`，附 today/明日两档 `reservationTimeOptions`（午餐/下午茶/夜市/宵夜分段） |
| `query-meals` | ✅ | 16 个分类 + `meals` 映射表（约 130 个 SKU）。价格是**元、字符串**：`currentPrice` / `originalPrice` / `discountType`（早餐卡/促销/麦金卡/随单购…）/ `canWithOrder` + `withOrder` |
| `query-store-coupons` | ✅ | 返回 `couponId` + `couponCode` + `tradeDateTime` + `products[].productCode`（券与商品已绑定：一张面额券只对应特定 `productCode`） |
| `calculate-price` | ✅ | 同一 SKU：原价 `2250` → 用券后 `1190`，`discount 1060`（**单位为分**）。附 `takeWayList`（堂食 / 外带） |
| `campaign-calendar` | ✅ | 不传参返回 10-20 ~ 11-03（跨月，不止当月）；每条含标题/正文/配图，带"往期回顾 / 今日 / 日期"分组标记 |
| `mall-points-products` | ✅（有坑） | `catRuleIds=1>4` 返回 25 个商品券，50~800 积分。**其中 downTime 为 2026-03-21 / 2026-06-24 的已过期商品，`status` 仍为 2（上架）** |

未调用（有副作用或依赖用户确认）：`create-order`、`cancel-order`、`mall-create-order`、`party-order-create`、`draw-lottery`、`auto-bind-coupons`、`query-party-*`（需 spuId 链路）。

## 3. 对「麦麦黄历」的直接结论

### 3.1 四路比价已全部可算，无需人工干预

同一样本（门店 `1400037`，SKU `1440`）：

- **原价买**：22.50 元（`query-meals.currentPrice` = 22.5）
- **用券买**：11.90 元（`calculate-price` 实测 `price=1190`）
- **积分换**：账户积分够换 100 分档（3.9 元圆筒 / 10.9 元指定小食 / 6.9 元派），不够 200 分档 → 输出「还差 N 分」
- **等活动**：`campaign-calendar` 给出 10-22 丝巾周边、10-25 龙焰三件套等

四路都能落到「元」或「分」，可统一换算后排序。

### 3.2 三个必须处理的坑（直接影响 engine 正确性）

1. **单位不一致**：`query-meals` 是**元（字符串）**，`calculate-price` 是**分（整数）**。混用会差 100 倍。
2. **积分商城不自我过滤过期**：`mall-points-products` 的 `status=2` 不代表可兑，必须自己用 `downTime > now` 过滤。25 条里约 12 条已过期。这正是「黄历」该干的事——接口给的是脏数据，产品价值在清洗。
3. **券的可用性分三层**：`query-my-coupons`（我有什么券，不校验门店）→ `query-store-coupons`（这家店能用哪些）→ `calculate-price`（这单实际多少钱）。跳过第二层会把券算错。

### 3.3 可用的「时间」信号（黄历的核心素材）

- 券：`tradeDateTime` 精确到分（23:59:59 到期）→ 可做倒计时与「今日必须用掉」
- 积分：`currentMouthExpirePoint` / `nextMouthExpirePoint` → 可做「本月将过期 / 下月将过期」双档预警
- 积分商品：`upTime` / `downTime` 双端 → 可做「今日上架 / 今日将下架」
- 活动：`campaign-calendar` 的日期分组 → 可做「今日宜 / 今日忌」
- 门店：`reservationTimeOptions` 的分段时段 → 可做「此刻宜去」

## 4. 建议的调用顺序（写入 engine）

```
now-time-info                      # 基准时间，避免本地时钟漂移
→ query-nearby-stores(searchType=1) # 拿 storeCode
→ query-meals(storeCode)            # 菜单与元价
→ query-store-coupons(storeCode)    # 本店可用券（含 couponId/couponCode）
→ calculate-price(items, coupon)    # 分价，验证优惠是否真的生效
→ query-my-account                  # 积分余额与过期压力
→ mall-points-products(1>4)         # 过滤 downTime > now
→ campaign-calendar                 # 活动与临期
```

单次完整链路实测耗时约 2~3 秒（串行 7 次调用），可接受；若做 CLI，建议 `now-time-info` 与 `query-my-account` 并发。
