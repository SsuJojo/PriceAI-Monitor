"""链动小铺 (ldxp.cn) 自动下单模块

通过 API 直调实现秒级下单，无需网页解析。
"""
import json
import re
import urllib.parse
import urllib.request
import urllib.error
import webbrowser
from typing import Any

BASE_URL = "https://pay.ldxp.cn"
DEFAULT_TIMEOUT = 10


class OrderError(Exception):
    """下单流程异常"""


def _api_post(path: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    """调用链动小铺 POST API"""
    url = BASE_URL + path
    body = json.dumps(data or {}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise OrderError(f"HTTP {exc.code}: {exc.reason}") from exc
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise OrderError(f"请求失败: {exc}") from exc


def extract_goods_key(url: str) -> str | None:
    """从链动小铺商品 URL 中提取 goods_key。

    支持格式:
      https://pay.ldxp.cn/item/7p246r
      https://www.ldxp.cn/item/7p246r
      https://pay.ldxp.cn/item/7p246r/TRADE123
    """
    match = re.search(r"/item/([a-zA-Z0-9]+)", url)
    return match.group(1) if match else None


def is_ldxp_url(url: str) -> bool:
    """判断 URL 是否为链动小铺链接"""
    return "ldxp.cn" in url


def fetch_goods_info(goods_key: str) -> dict[str, Any]:
    """获取商品详情"""
    result = _api_post("/shopApi/Shop/goodsInfo", {"goods_key": goods_key})
    if result.get("code") != 1:
        raise OrderError(result.get("msg", "商品不存在"))
    return result["data"]


def get_user_channel(token: str) -> list[dict[str, Any]]:
    """获取卖家支持的支付渠道列表"""
    result = _api_post("/shopApi/Shop/getUserChannel", {"token": token})
    if result.get("code") != 1:
        raise OrderError(result.get("msg", "获取支付渠道失败"))
    return result.get("data", [])


def select_channel(channels: list[dict[str, Any]], preferred: str = "alipay") -> dict[str, Any] | None:
    """从支付渠道列表中选择合适的渠道，优先支付宝"""
    if not channels:
        return None
    # 优先匹配支付宝
    for ch in channels:
        name = str(ch.get("name", "")).lower()
        if "alipay" in name or "支付宝" in name:
            return ch
    # 其次匹配微信
    if preferred == "wechat":
        for ch in channels:
            name = str(ch.get("name", "")).lower()
            if "wechat" in name or "微信" in name:
                return ch
    # 默认返回第一个
    return channels[0]


def create_order(
    goods_key: str,
    channel_id: int,
    contact: str,
    query_password: str = "",
) -> dict[str, Any]:
    """创建订单

    返回值包含:
      trade_no     - 订单号
      total_amount - 应付金额
      payurl       - 支付链接（需在浏览器中打开）
    """
    payload: dict[str, Any] = {
        "goods_key": goods_key,
        "quantity": 1,
        "coupon_code": "",
        "channel_id": channel_id,
        "contact": contact,
        "extend": {},
    }
    if query_password:
        payload["query_password"] = query_password

    result = _api_post("/shopApi/Pay/order", payload)
    if result.get("code") != 1:
        raise OrderError(result.get("msg", "下单失败"))
    return result["data"]


def auto_order(
    url: str,
    contact: str,
    query_password: str = "",
    preferred_channel: str = "alipay",
) -> dict[str, Any]:
    """自动下单主流程

    从 URL 提取商品 -> 查询详情 -> 选支付渠道 -> 下单 -> 打开支付页

    返回 dict:
      success: bool
      goods_name: str
      trade_no: str
      total_amount: float
      payurl: str (已打开)
      message: str
    """
    goods_key = extract_goods_key(url)
    if not goods_key:
        return {"success": False, "message": f"无法从 URL 提取商品 key: {url}"}

    # 1. 查询商品详情
    try:
        goods_info = fetch_goods_info(goods_key)
    except OrderError as exc:
        return {"success": False, "message": str(exc), "goods_key": goods_key}

    goods_name = goods_info.get("name", "未知商品")
    seller_token = ""
    user_info = goods_info.get("user", {})
    if isinstance(user_info, dict):
        seller_token = str(user_info.get("token", ""))

    # 2. 获取支付渠道
    try:
        channels = get_user_channel(seller_token)
    except OrderError as exc:
        return {"success": False, "message": str(exc), "goods_name": goods_name}

    channel = select_channel(channels, preferred=preferred_channel)
    if not channel:
        return {"success": False, "message": "无可用支付渠道", "goods_name": goods_name}

    channel_id = int(channel.get("id", 0))

    # 3. 下单
    try:
        order_data = create_order(goods_key, channel_id, contact, query_password)
    except OrderError as exc:
        return {"success": False, "message": str(exc), "goods_name": goods_name}

    trade_no = str(order_data.get("trade_no", ""))
    total_amount = float(order_data.get("total_amount", 0))
    payurl = str(order_data.get("payurl", ""))

    # 4. 打开支付页 + 商品详情页
    if total_amount > 0 and payurl:
        webbrowser.open(url)
        webbrowser.open(payurl)

    return {
        "success": True,
        "goods_name": goods_name,
        "trade_no": trade_no,
        "total_amount": total_amount,
        "payurl": payurl,
        "channel_name": str(channel.get("name", "")),
        "message": f"下单成功: {goods_name} | ¥{total_amount} | {trade_no}",
    }
