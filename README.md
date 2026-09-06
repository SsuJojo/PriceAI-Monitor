# PriceAI 账号价格监控器 (PriceAI-Monitor)

通过 [PriceAI](https://priceai.cc) Price Radar V1 官方公开快照，高频监控 ChatGPT Plus 试用订阅等账号低价报价（全网最低价与精选推荐），支持价格/关键词/库存筛选、Windows 桌面通知点击直达、Bark 手机推送直达、链动小铺 (ldxp.cn) 自动下单秒级跳转，以及系统托盘常驻与开机自启。

![程序截图](docs/程序截图.png)

---

## 核心特性

- **Price Radar 官方快照监控**：定时轮询 Price Radar 数据，自动提取全网最低价 (`lowest_offer`) 及 Top 推荐报价。
- **智能去重与差量提醒**：本地比对历史记录，仅在新商品上架、降价或库存回补时提醒，避免重复刷屏。
- **直达商铺通知体系**：
  - **Windows 桌面通知**：原生 WinRT Toast 通知，点击卡片直接在默认浏览器打开对应商铺商品页。
  - **Bark 手机推送**：支持独立开关控制与推送直达链接，点击通知跳转商铺。
  - **Webhook / Telegram**：支持自定义 Webhook 与 Telegram Bot。
- **链动小铺秒级自动下单**：
  - 命中规则时直接通过 API 提交订单并唤起支付页，抢先锁定库存。
  - 自动下单成功后自动暂停监控，避免重复下单；付款完成后可一键继续。
- **系统托盘与常驻后台**：
  - 点击窗口右上角 `✕` 最小化到系统托盘，不占任务栏空间。
  - 单击/双击托盘图标唤醒主界面，右键菜单安全退出。
- **内置开机自启切换**：
  - GUI 界面内置开机自启开关，无需管理员提权或手动配置计划任务，一键写入用户启动项。
- **现代工程管理与单文件运行**：
  - 采用现代 Python 包管理工具 `uv` 统一管理环境与依赖。
  - 提供开箱即用的 Release 单文件绿色版可执行程序（`.exe`），无需安装 Python 即可运行。

---

## 下载与运行

### 方式一：下载打包好的绿色免安装版（推荐）

前往 [Releases 页面](https://github.com/SsuJojo/PriceAI-Monitor/releases) 下载最新发布的 `PriceAI-Monitor.exe`：
1. 下载后放入任意文件夹。
2. 双击 `PriceAI-Monitor.exe` 即可直接打开监控面板。
3. 可在界面内直接开启「开机自动启动 PriceAI 监控器」，开机静默进入托盘。

### 方式二：使用 `uv` 源码运行

本项目使用 [uv](https://docs.astral.sh/uv/) 进行依赖管理：

1. **克隆仓库**
   ```bash
   git clone https://github.com/SsuJojo/PriceAI-Monitor.git
   cd PriceAI-Monitor
   ```

2. **安装 uv（若尚未安装）**
   ```powershell
   # Windows PowerShell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

3. **同步依赖并启动**
   ```powershell
   # 安装依赖
   uv sync

   # 启动 GUI 界面
   uv run python settings_gui.py
   ```
   也可以双击项目根目录下的 `start_monitor.bat` 快捷启动。

---

## 界面与参数说明

### 监控条件
- **最高价格**：报价 ≤ 该金额时触发（如 `15` 元）。
- **最低价格**：过滤异常低价，设为 `0` 表示不限。
- **刷新间隔**：查询间隔秒数（PriceAI 官方限制最短为 60 秒）。
- **最低库存**：库存必须 ≥ 该数值才告警。
- **报价有效时间**：只接受最近 N 分钟内刷新的报价，`0` 表示不限。

### 关键词过滤
- **包含关键词**：必须包含全部指定的关键词（支持分行或逗号分隔）。
- **排除关键词**：命中任一排除词即忽略（如排除“网页”、“日抛”等）。

### 提醒通知设置
- **Windows 桌面通知**：开启后弹出 WinRT Toast，点击通知卡片直达商铺。
- **Bark 手机推送**：支持独立开关、自定义 Bark Key 和推送标题，带直达链接。

### 自动下单（链动小铺）
- 开启后输入联系方式（手机号/邮箱）与查询安全密码。
- 监控到目标商品时将调用 API 自动创建订单并拉起浏览器支付页，同时自动暂停监控。

### 系统与自启
- **开机自动启动**：勾选后写入注册表 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`，开机自启并最小化至托盘。

---

## 开发者打包说明

如需自行打包单文件可执行文件，使用 `uv` 内置的 PyInstaller：

```powershell
uv run pyinstaller -F -w -n PriceAI-Monitor settings_gui.py
```

打包完成后的可执行文件位于 `dist/PriceAI-Monitor.exe`。

---

## 免责声明

本项目仅供个人学习与自动化技术交流，使用者需自行遵守相关平台（包括但不限于 PriceAI、链动小铺、各卡网商户及 OpenAI）的服务条款与规范。作者不对因使用本工具而产生的任何交易、经济损失或法律后果承担责任。
