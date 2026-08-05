# -*- coding: utf-8 -*-
"""
ChatGPT Plus 价格监控器（无账号过滤版）

从 config.json 读取配置（参考 config.example.json）：
  simple_monitor.url
  simple_monitor.alarm_below_price
  simple_monitor.check_interval_seconds
  simple_monitor.bark_key
  simple_monitor.bark_title
"""

import json
import re
import urllib.request
import time
import winsound
from datetime import datetime
import urllib.parse
from pathlib import Path

CONFIG_PATH = Path(__file__).with_name("config.json")


def load_config() -> dict:
    with CONFIG_PATH.open(encoding="utf-8-sig") as f:
        return json.load(f)

def parse_price(html: str) -> list[float]:
    """从 HTML 中提取所有 ¥ 价格"""
    matches = re.findall(r"[¥￥]\s*([0-9]+(?:\.[0-9]+)?)", html)
    return [float(m) for m in matches if m]

def notify_low_price(bark_key: str, bark_title: str, low_price: float, all_prices: list[float]):
    """触发通知"""
    body = f"ChatGPT Plus 价格低于阈值！\n当前最低：¥{low_price:.2f}\n页面所有价格：{' '.join([f'¥{p:.2f}' for p in all_prices])}"
    encoded_body = urllib.parse.quote(body)

    bark_url = f"https://api.day.app/{bark_key}/{urllib.parse.quote(bark_title)}/{encoded_body}"

    print(f"\n{'='*60}")
    print(f"🚨 价格报警！{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   最低价格：¥{low_price:.2f}")
    print(f"   页面价格：{' | '.join([f'¥{p:.2f}' for p in all_prices])}")
    print(f"{'='*60}\n")

    winsound.Beep(800, 400)
    winsound.Beep(1000, 400)
    winsound.Beep(1200, 600)

    try:
        req = urllib.request.Request(bark_url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"✅ Bark 推送已发送（状态码: {resp.status})")
    except Exception as e:
        print(f"❌ Bark 推送失败：{e}")

def main():
    cfg = load_config().get("simple_monitor", {})
    url = cfg.get("url", "https://priceai.cc/products/chatgpt-plus?back=platform%3DChatGPT")
    alarm_below = float(cfg.get("alarm_below_price", 14.0))
    interval = int(cfg.get("check_interval_seconds", 3600))
    bark_key = cfg.get("bark_key", "")
    bark_title = cfg.get("bark_title", "ChatGPT Plus 价格报警")

    print("=== ChatGPT Plus 价格监控器启动（无账号过滤版）===\n")

    while True:
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"}
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                html = resp.read().decode("utf-8", errors="replace")

            prices = parse_price(html)
            if not prices:
                print("⚠️  未找到任何价格标签")
                time.sleep(interval)
                continue

            min_price = min(prices)
            all_prices_str = " | ".join([f"¥{p:.2f}" for p in prices])
            print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 最低：¥{min_price:.2f} | 页面价格：{all_prices_str}")

            if min_price < alarm_below:
                notify_low_price(bark_key, bark_title, min_price, prices)

        except Exception as e:
            print(f"❌ 检查失败：{e}")

        time.sleep(interval)

if __name__ == "__main__":
    main()
