# PriceAI 合适价格监控

这个程序通过 PriceAI Price Radar V1 官方公开快照，定时检查 ChatGPT Plus「已接码成品号」Top 5 报价。它只对**有货且满足全部规则**的商品提醒，并对相同报价去重；价格进一步下降或达到重新提醒间隔时才会再次提醒。

## 当前默认规则

- 商品：`chatgpt-plus`
- Price Radar 预设：`account_verified`（已接码成品号）
- 最高监控价格：¥10（报价小于等于 ¥10 时匹配）
- 最低库存：1
- 只接受最近 120 分钟内更新的报价
- 排除标题中的「日抛、网页号、不售后、无质保」
- 每 120 秒检查一次（持续运行模式）
- 默认使用控制台和 Windows 桌面通知

所有规则都可以在设置窗口中修改，也会保存到 `config.json`。

## 设置窗口

直接双击 `start_monitor.bat` 打开设置窗口。窗口支持：

- 设置最高监控价格，匹配规则为“报价 ≤ 监控价格”。
- 设置刷新间隔；遵循 PriceAI 文档，最短为 60 秒，建议使用 120～300 秒。
- 设置最低价格、最低库存、报价有效时间和重复提醒时间。
- 编辑必须包含和排除关键词。
- 测试扫描，不发送通知也不改变去重记录。
- 保存并启动监控，或停止当前监控。

关闭设置窗口会同时停止由该窗口启动的监控。

## 立即试跑

只看匹配结果，不发通知，也不写去重状态：

```powershell
python price_monitor.py --config config.json check --dry-run
```

实际检查并提醒一次：

```powershell
python price_monitor.py --config config.json check
```

持续运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\start_monitor.ps1
```

如需绕过设置窗口直接持续运行，也可以执行上面的 PowerShell 命令。

## 设置为 Windows 定时任务

下面的命令会创建一个每 5 分钟执行一次的任务；程序本身会去重，所以不会每次都重复提醒：

```powershell
powershell -ExecutionPolicy Bypass -File .\install_scheduled_task.ps1 -IntervalMinutes 5
```

删除任务：

```powershell
Unregister-ScheduledTask -TaskName 'PriceAI-Price-Monitor' -Confirm:$false
```

## 筛选配置

`config.json` 中常用字段：

| 字段 | 作用 |
| --- | --- |
| `max_price` | 最高监控价格；报价小于等于该值时匹配 |
| `check_interval_seconds` | 刷新间隔，不能小于 60 秒 |
| `min_price` | 排除异常低价；不需要时设为 `0` |
| `min_stock` | 最低库存；未知库存也会被排除 |
| `fresh_within_minutes` | 只看最近多少分钟更新的报价 |
| `required_keywords` | 标题/商家必须同时包含的词 |
| `excluded_keywords` | 标题/商家只要包含任意一个就排除 |
| `price_radar_latest_url` | Price Radar 快照指针地址，通常不需要修改 |
| `product_id` | 标准商品，当前为 `chatgpt-plus` |
| `preset_id` | 快速筛选预设，当前为 `account_verified` |
| `renotify_hours` | 同一报价多久后允许再次提醒；降价会立即重发 |

程序先读取 `https://data.priceai.cc/latest.json`。只有 `snapshot_id` 变化时才下载新的不可变快照，并把 ETag、快照编号和当前 Top 5 保存在 `monitor_state.json`；网络异常时会继续使用最后一次有效缓存。Price Radar V1 每个预设最多提供 5 条报价，关键词和价格条件均在本地应用。

## 远程提醒

如果程序运行在服务器上，可以在 `notifications` 中配置：

- `webhook_url`：接收 JSON POST，内容包含 `title`、`message`、`offers`。
- `telegram.bot_token` 和 `telegram.chat_id`：发送 Telegram 消息。

敏感 token 不要提交到公开仓库。`config.example.json` 可作为无敏感信息的模板。

## 关于自动购买

当前版本停在“发现合适报价并提供购买链接”，不会自动下单或付款。聚合页明确说明交易、库存、质保和售后以原平台为准；不同商家的登录、库存确认、支付和风控也不一致。建议先稳定运行提醒并人工核验，再为经过确认的单一商家设计“加入购物车/待确认下单”，不要跨平台盲目自动付款。
