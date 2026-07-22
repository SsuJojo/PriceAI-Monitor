#!/usr/bin/env python3
"""Monitor PriceAI product offers and notify when a rule matches."""

from __future__ import annotations

import argparse
import http.client
import json
import os
import platform
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from auto_order import auto_order, is_ldxp_url


DEFAULT_CONFIG_PATH = Path(__file__).with_name("config.json")
DEFAULT_STATE_PATH = Path(__file__).with_name("monitor_state.json")
AVAILABLE_STATUSES = {"in_stock", "low_stock"}
UNAVAILABLE_EFFECTIVE_STATUSES = {"unavailable", "stale", "failed"}
USER_AGENT = "PriceAI-Offer-Monitor/1.0 (+personal price alert)"
DEFAULT_PRICE_RADAR_URL = "https://data.priceai.cc/latest.json"


class MonitorError(RuntimeError):
    """A user-facing monitor error."""


@dataclass(frozen=True)
class Offer:
    id: str
    title: str
    price: float
    currency: str
    status: str
    effective_status: str
    url: str
    source_name: str
    source_store_name: str
    stock_count: int | None
    updated_at: str
    raw: dict[str, Any]

    @classmethod
    def from_api(cls, value: dict[str, Any]) -> "Offer | None":
        price = value.get("price")
        if not isinstance(price, (int, float)) or isinstance(price, bool):
            return None
        offer_id = str(value.get("id") or value.get("url") or "").strip()
        url = str(value.get("url") or "").strip()
        if not offer_id or not url:
            return None
        stock = value.get("stockCount", value.get("stock_count"))
        if not isinstance(stock, int) or isinstance(stock, bool):
            stock = None
        updated = (
            value.get("verifiedAt")
            or value.get("verified_at")
            or value.get("lastSeenAt")
            or value.get("last_seen_at")
            or value.get("capturedAt")
            or value.get("captured_at")
            or value.get("sourceUpdatedAt")
            or value.get("source_updated_at")
            or ""
        )
        return cls(
            id=offer_id,
            title=str(value.get("sourceTitle") or value.get("title") or "未命名商品").strip(),
            price=float(price),
            currency=str(value.get("currency") or "CNY").upper(),
            status=str(value.get("status") or "unknown"),
            effective_status=str(value.get("effectiveStatus") or value.get("effective_status") or ""),
            url=url,
            source_name=str(value.get("sourceName") or value.get("source_name") or "未知渠道").strip(),
            source_store_name=str(value.get("sourceStoreName") or value.get("source_store_name") or "").strip(),
            stock_count=stock,
            updated_at=str(updated),
            raw=value,
        )

    @property
    def seller(self) -> str:
        return self.source_store_name or self.source_name

    @property
    def fingerprint(self) -> str:
        stock = "?" if self.stock_count is None else str(self.stock_count)
        return f"{self.price:.4f}|{stock}|{self.status}|{self.effective_status}"


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise MonitorError(f"找不到配置文件：{path}") from exc
    except json.JSONDecodeError as exc:
        raise MonitorError(f"JSON 格式错误：{path}（第 {exc.lineno} 行）") from exc
    if not isinstance(value, dict):
        raise MonitorError(f"文件顶层必须是 JSON 对象：{path}")
    return value


def load_config(path: Path) -> dict[str, Any]:
    config = load_json(path)
    max_price = config.get("max_price")
    if not isinstance(max_price, (int, float)) or isinstance(max_price, bool) or max_price <= 0:
        raise MonitorError("config.json 中的 max_price 必须是大于 0 的数字")
    interval = config.get("check_interval_seconds", 60)
    if not isinstance(interval, int) or isinstance(interval, bool) or interval < 60:
        raise MonitorError("check_interval_seconds 必须是至少 60 的整数")
    return config


def normalized_words(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(word).strip().casefold() for word in value if str(word).strip()]


def price_radar_latest_url(config: dict[str, Any]) -> str:
    return str(config.get("price_radar_latest_url") or DEFAULT_PRICE_RADAR_URL).strip()


def request_json(
    url: str,
    config: dict[str, Any],
    *,
    etag: str = "",
) -> tuple[dict[str, Any] | None, str, bool]:
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    if etag:
        headers["If-None-Match"] = etag
    request = urllib.request.Request(url, headers=headers)
    timeout = float(config.get("request_timeout_seconds", 15))
    attempts = min(max(int(config.get("request_retries", 3)), 1), 5)
    last_error: BaseException | None = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read()
                response_etag = str(response.headers.get("ETag") or "")
            try:
                payload = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise MonitorError("PriceAI 返回了无法识别的 JSON 数据") from exc
            if not isinstance(payload, dict):
                raise MonitorError("PriceAI JSON 顶层不是对象")
            return payload, response_etag, False
        except urllib.error.HTTPError as exc:
            if exc.code == 304:
                return None, etag, True
            if exc.code not in {408, 429} and exc.code < 500:
                raise MonitorError(f"PriceAI Price Radar 返回 HTTP {exc.code}") from exc
            last_error = exc
        except (urllib.error.URLError, TimeoutError, http.client.IncompleteRead, OSError) as exc:
            last_error = exc
        if attempt + 1 < attempts:
            time.sleep(min(2 ** attempt, 4))

    if isinstance(last_error, urllib.error.HTTPError):
        raise MonitorError(f"PriceAI Price Radar 连续返回 HTTP {last_error.code}") from last_error
    if isinstance(last_error, urllib.error.URLError):
        raise MonitorError(f"无法连接 PriceAI Price Radar：{last_error.reason}") from last_error
    raise MonitorError(f"读取 PriceAI Price Radar 失败：{last_error}") from last_error


def extract_price_radar_offers(
    snapshot: dict[str, Any],
    product_id: str,
    preset_id: str,
) -> tuple[list[Offer], dict[str, Any], list[dict[str, Any]]]:
    products = snapshot.get("products")
    if not isinstance(products, list):
        raise MonitorError("Price Radar 快照缺少 products 列表")
    product = next(
        (
            item
            for item in products
            if isinstance(item, dict)
            and (item.get("slug") == product_id or item.get("id") == product_id)
        ),
        None,
    )
    if product is None:
        raise MonitorError(f"Price Radar 快照中找不到商品：{product_id}")

    presets = product.get("presets")
    if not isinstance(presets, list):
        raise MonitorError(f"商品 {product_id} 没有 presets 数据")
    preset = next(
        (item for item in presets if isinstance(item, dict) and item.get("id") == preset_id),
        None,
    )
    if preset is None:
        raise MonitorError(f"商品 {product_id} 没有筛选预设：{preset_id}")
    raw_offers = preset.get("top_offers")
    if not isinstance(raw_offers, list):
        raise MonitorError(f"筛选预设 {preset_id} 缺少 top_offers")

    normalized_raw = [item for item in raw_offers if isinstance(item, dict)]
    offers: list[Offer] = []
    for item in normalized_raw:
        if isinstance(item, dict):
            offer = Offer.from_api(item)
            if offer is not None:
                offers.append(offer)
    generated_at = (
        product.get("latest_seen_at")
        or product.get("snapshot_generated_at")
        or preset.get("generated_at")
        or snapshot.get("generated_at")
        or ""
    )
    payload = {
        "generatedAt": generated_at,
        "snapshotId": snapshot.get("snapshot_id"),
        "stale": bool(snapshot.get("stale", False)),
        "source": "price-radar.v1",
        "product": product_id,
        "preset": preset_id,
        "total": preset.get("total"),
    }
    return offers, payload, normalized_raw


def cached_price_radar_result(
    cache: dict[str, Any] | None,
    *,
    product_id: str,
    preset_id: str,
    degraded_message: str | None = None,
) -> tuple[list[Offer], dict[str, Any], dict[str, Any]] | None:
    if not isinstance(cache, dict) or not isinstance(cache.get("offers"), list):
        return None
    cached_payload = cache.get("payload")
    if not isinstance(cached_payload, dict):
        return None
    if cached_payload.get("product") != product_id or cached_payload.get("preset") != preset_id:
        return None
    offers = [
        offer
        for item in cache["offers"]
        if isinstance(item, dict)
        for offer in [Offer.from_api(item)]
        if offer is not None
    ]
    payload = dict(cached_payload)
    if degraded_message:
        payload["degraded"] = True
        payload["message"] = degraded_message
    return offers, payload, cache


def fetch_offers(
    config: dict[str, Any],
    cache: dict[str, Any] | None = None,
) -> tuple[list[Offer], dict[str, Any], dict[str, Any]]:
    latest_url = price_radar_latest_url(config)
    product_id = str(config.get("product_id") or "chatgpt-plus")
    preset_id = str(config.get("preset_id") or "account_verified")
    cached_etag = str(cache.get("etag") or "") if isinstance(cache, dict) else ""
    try:
        latest, etag, not_modified = request_json(latest_url, config, etag=cached_etag)
    except MonitorError as exc:
        fallback = cached_price_radar_result(
            cache,
            product_id=product_id,
            preset_id=preset_id,
            degraded_message=str(exc),
        )
        if fallback is not None:
            return fallback
        raise

    if not_modified:
        fallback = cached_price_radar_result(cache, product_id=product_id, preset_id=preset_id)
        if fallback is not None:
            return fallback
        raise MonitorError("Price Radar 返回 304，但本地没有可用缓存")
    if latest is None:
        raise MonitorError("Price Radar latest.json 响应为空")

    snapshot_id = str(latest.get("snapshot_id") or "")
    snapshot_url = str(latest.get("snapshot_url") or "")
    if not snapshot_id or not snapshot_url:
        raise MonitorError("Price Radar latest.json 缺少 snapshot_id 或 snapshot_url")
    if isinstance(cache, dict) and cache.get("snapshot_id") == snapshot_id:
        fallback = cached_price_radar_result(cache, product_id=product_id, preset_id=preset_id)
        if fallback is not None:
            updated_cache = dict(cache)
            updated_cache["etag"] = etag or cached_etag
            return fallback[0], fallback[1], updated_cache

    try:
        snapshot, _, _ = request_json(snapshot_url, config)
        if snapshot is None:
            raise MonitorError("Price Radar 快照响应为空")
        offers, payload, raw_offers = extract_price_radar_offers(snapshot, product_id, preset_id)
    except MonitorError as exc:
        fallback = cached_price_radar_result(
            cache,
            product_id=product_id,
            preset_id=preset_id,
            degraded_message=str(exc),
        )
        if fallback is not None:
            return fallback
        raise

    next_cache = {
        "etag": etag,
        "snapshot_id": snapshot_id,
        "snapshot_url": snapshot_url,
        "offers": raw_offers,
        "payload": payload,
        "cached_at": datetime.now(timezone.utc).isoformat(),
    }
    return offers, payload, next_cache


def is_available(offer: Offer) -> bool:
    return (
        offer.status in AVAILABLE_STATUSES
        and offer.effective_status not in UNAVAILABLE_EFFECTIVE_STATUSES
    )


def matches_config(offer: Offer, config: dict[str, Any]) -> bool:
    if not is_available(offer):
        return False
    if offer.price > float(config["max_price"]):
        return False
    min_price = config.get("min_price")
    if isinstance(min_price, (int, float)) and offer.price < float(min_price):
        return False
    min_stock = config.get("min_stock")
    if isinstance(min_stock, int) and (offer.stock_count is None or offer.stock_count < min_stock):
        return False
    fresh_within = config.get("fresh_within_minutes")
    if isinstance(fresh_within, (int, float)) and fresh_within > 0:
        updated_at = parse_api_time(offer.updated_at)
        if updated_at is None:
            return False
        age_seconds = (datetime.now(timezone.utc) - updated_at).total_seconds()
        if age_seconds > float(fresh_within) * 60:
            return False

    haystack = f"{offer.title} {offer.seller} {offer.source_name}".casefold()
    required = normalized_words(config.get("required_keywords"))
    excluded = normalized_words(config.get("excluded_keywords"))
    if required and not all(word in haystack for word in required):
        return False
    if any(word in haystack for word in excluded):
        return False
    return True


def parse_api_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def sort_offers(offers: Iterable[Offer]) -> list[Offer]:
    return sorted(offers, key=lambda item: (item.price, -(item.stock_count or 0), item.seller))


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"last_offers": {}}
    try:
        value = load_json(path)
    except MonitorError:
        backup = path.with_suffix(path.suffix + ".broken")
        try:
            path.replace(backup)
        except OSError:
            pass
        return {"last_offers": {}}
    if not isinstance(value.get("last_offers"), dict):
        value["last_offers"] = {}
    return value


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def notification_candidates(
    offers: list[Offer], state: dict[str, Any]
) -> list[Offer]:
    """与上次扫描对比，返回需要通知的报价（新 id 或价格降低或库存上升）。"""
    last_offers = state.get("last_offers", {})
    if not isinstance(last_offers, dict):
        last_offers = {}
    candidates: list[Offer] = []
    for offer in offers:
        previous = last_offers.get(offer.id)
        if not isinstance(previous, dict):
            candidates.append(offer)
            continue
        previous_price = previous.get("price")
        price_dropped = isinstance(previous_price, (int, float)) and offer.price < float(previous_price)
        previous_stock = previous.get("stock_count")
        stock_increased = (
            isinstance(previous_stock, (int, float))
            and isinstance(offer.stock_count, int)
            and offer.stock_count > int(previous_stock)
        )
        if price_dropped or stock_increased:
            candidates.append(offer)
    return candidates


def format_price(offer: Offer) -> str:
    symbol = "¥" if offer.currency in {"CNY", "RMB"} else f"{offer.currency} "
    return f"{symbol}{offer.price:.2f}"


def format_offer_line(offer: Offer) -> str:
    stock = "库存未知" if offer.stock_count is None else f"库存 {offer.stock_count}"
    updated = "时间未知"
    parsed = parse_api_time(offer.updated_at)
    if parsed is not None:
        seconds = int((datetime.now(timezone.utc) - parsed).total_seconds())
        if seconds < 60:
            updated = "刚刚"
        elif seconds < 3600:
            updated = f"{seconds // 60}分钟前"
        elif seconds < 86400:
            updated = f"{seconds // 3600}小时前"
        else:
            updated = f"{seconds // 86400}天前"
    return f"{format_price(offer)}｜{stock}｜更新 {updated}｜{offer.seller}｜{offer.title}\n{offer.url}"


def build_notification(offers: list[Offer], config: dict[str, Any]) -> tuple[str, str]:
    best = min(offer.price for offer in offers)
    title = f"PriceAI 发现 {len(offers)} 条合适报价，最低 ¥{best:.2f}"
    max_items = max(1, int(config.get("notification_max_items", 5)))
    lines = [format_offer_line(offer) for offer in offers[:max_items]]
    if len(offers) > max_items:
        lines.append(f"另有 {len(offers) - max_items} 条匹配报价未展开。")
    return title, "\n\n".join(lines)


def post_json(url: str, payload: dict[str, Any], timeout: float = 15) -> None:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response.read()
    except (urllib.error.URLError, TimeoutError) as exc:
        raise MonitorError(f"Webhook 发送失败：{exc}") from exc


def send_telegram(bot_token: str, chat_id: str, title: str, body: str) -> None:
    url = f"https://api.telegram.org/bot{urllib.parse.quote(bot_token, safe=':')}/sendMessage"
    data = urllib.parse.urlencode(
        {"chat_id": chat_id, "text": f"{title}\n\n{body}", "disable_web_page_preview": "true"}
    ).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            response.read()
    except (urllib.error.URLError, TimeoutError) as exc:
        raise MonitorError(f"Telegram 发送失败：{exc}") from exc


def xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def send_windows_toast(title: str, body: str) -> None:
    if platform.system() != "Windows":
        return
    short_body = body.replace("\n", " ")[:240]
    toast_xml = (
        '<toast><visual><binding template="ToastGeneric">'
        f"<text>{xml_escape(title)}</text><text>{xml_escape(short_body)}</text>"
        "</binding></visual></toast>"
    )
    script = (
        "$ErrorActionPreference='Stop';"
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null;"
        "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null;"
        "$xml=New-Object Windows.Data.Xml.Dom.XmlDocument;"
        f"$xml.LoadXml('{toast_xml.replace(chr(39), chr(39) * 2)}');"
        "$toast=[Windows.UI.Notifications.ToastNotification]::new($xml);"
        "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe').Show($toast)"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
        creationflags=int(getattr(subprocess, "CREATE_NO_WINDOW", 0)) if os.name == "nt" else 0,
    )
    if result.returncode != 0:
        raise OSError(result.stderr.strip() or f"PowerShell exited with code {result.returncode}")


def notify(offers: list[Offer], config: dict[str, Any]) -> None:
    title, body = build_notification(offers, config)
    print(f"\n{'=' * 72}\n{title}\n{'-' * 72}\n{body}\n{'=' * 72}", flush=True)

    # 自动下单优先执行，抢在所有通知之前
    try_auto_order(offers, config)

    settings = config.get("notifications") if isinstance(config.get("notifications"), dict) else {}
    errors: list[str] = []

    if settings.get("windows_toast", True):
        try:
            send_windows_toast(title, body)
        except (OSError, subprocess.SubprocessError) as exc:
            errors.append(f"Windows 通知失败：{exc}")

    webhook_url = str(settings.get("webhook_url") or "").strip()
    if webhook_url:
        try:
            post_json(
                webhook_url,
                {
                    "title": title,
                    "message": body,
                    "offers": [offer.raw for offer in offers],
                    "source": "priceai-monitor",
                },
            )
        except MonitorError as exc:
            errors.append(str(exc))

    telegram = settings.get("telegram") if isinstance(settings.get("telegram"), dict) else {}
    token = str(telegram.get("bot_token") or "").strip()
    chat_id = str(telegram.get("chat_id") or "").strip()
    if token and chat_id:
        try:
            send_telegram(token, chat_id, title, body)
        except MonitorError as exc:
            errors.append(str(exc))

    for error in errors:
        print(f"[提醒通道警告] {error}", file=sys.stderr, flush=True)


def try_auto_order(offers: list[Offer], config: dict[str, Any]) -> None:
    """对匹配的链动小铺报价执行自动下单"""
    order_cfg = config.get("auto_order")
    if not isinstance(order_cfg, dict) or not order_cfg.get("enabled"):
        return

    contact = str(order_cfg.get("contact") or "").strip()
    if not contact:
        return

    query_password = str(order_cfg.get("query_password") or "").strip()
    preferred_channel = str(order_cfg.get("preferred_channel") or "alipay").strip()

    for offer in offers:
        if not is_ldxp_url(offer.url):
            continue
        print(f"[自动下单] 开始处理: {offer.title} | {offer.url}", flush=True)
        result = auto_order(
            offer.url,
            contact=contact,
            query_password=query_password,
            preferred_channel=preferred_channel,
        )
        if result.get("success"):
            print(
                f"[自动下单] 成功: {result['message']} | 支付链接已打开",
                flush=True,
            )
            print(f"[自动下单] 支付链接: {result.get('payurl', '')}", flush=True)
        else:
            print(f"[自动下单] 失败: {result.get('message', '未知错误')}", flush=True)
        # 只处理第一个可下单的 ldxp 报价
        if result.get("success"):
            break


def check_once(
    config: dict[str, Any], state_path: Path, *, dry_run: bool = False
) -> tuple[int, int]:
    state = load_state(state_path)
    radar_cache = state.get("price_radar") if isinstance(state.get("price_radar"), dict) else None
    offers, payload, next_radar_cache = fetch_offers(config, radar_cache)
    state["price_radar"] = next_radar_cache
    matched = sort_offers(offer for offer in offers if matches_config(offer, config))
    generated_at = payload.get("generatedAt") or "未知"

    if dry_run:
        print(
            f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
            f"接口返回 {len(offers)} 条，匹配 {len(matched)} 条",
            flush=True,
        )
        for offer in matched:
            print(f"- {format_offer_line(offer)}", flush=True)
        return len(offers), len(matched)

    candidates = notification_candidates(matched, state)
    dedup_count = len(matched) - len(candidates)
    print(
        f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
        f"接口返回 {len(offers)} 条，匹配 {len(matched)} 条，去重 {dedup_count} 条",
        flush=True,
    )

    if candidates:
        notify(candidates, config)

    # 用本次匹配结果覆盖上次记录，下次扫描时用于对比
    state["last_offers"] = {
        offer.id: {"price": offer.price, "stock_count": offer.stock_count}
        for offer in matched
    }
    state["last_success_at"] = datetime.now(timezone.utc).isoformat()
    state["last_generated_at"] = generated_at
    save_state(state_path, state)
    return len(offers), len(matched)


def run_watch(config: dict[str, Any], state_path: Path) -> None:
    interval = int(config.get("check_interval_seconds", 60))
    print(f"PriceAI 监控已启动，每 {interval} 秒检查一次。按 Ctrl+C 停止。", flush=True)
    consecutive_errors = 0
    while True:
        started = time.monotonic()
        try:
            check_once(config, state_path)
            consecutive_errors = 0
        except MonitorError as exc:
            consecutive_errors += 1
            print(f"[检查失败 {consecutive_errors}] {exc}", file=sys.stderr, flush=True)
        elapsed = time.monotonic() - started
        delay = max(1.0, interval - elapsed)
        try:
            time.sleep(delay)
        except KeyboardInterrupt:
            print("\n监控已停止。", flush=True)
            return


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PriceAI 合适价格监控与提醒")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="配置文件路径")
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH, help="去重状态文件路径")
    subparsers = parser.add_subparsers(dest="command", required=True)
    check_parser = subparsers.add_parser("check", help="立即检查一次")
    check_parser.add_argument("--dry-run", action="store_true", help="只显示匹配结果，不提醒、不写状态")
    subparsers.add_parser("watch", help="持续监控")
    return parser.parse_args(argv)


def configure_output_streams() -> None:
    # Legacy Windows PowerShell commonly exposes a GBK console. Merchant names
    # may contain emoji, so keep the monitor alive even when a glyph cannot be
    # represented by the current terminal encoding.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    configure_output_streams()
    args = parse_args(argv)
    try:
        config = load_config(args.config.resolve())
        state_path = args.state.resolve()
        if args.command == "check":
            check_once(config, state_path, dry_run=args.dry_run)
        else:
            run_watch(config, state_path)
    except MonitorError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n已停止。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
