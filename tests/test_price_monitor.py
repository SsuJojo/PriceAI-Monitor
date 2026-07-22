import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone

from price_monitor import (
    Offer,
    extract_price_radar_offers,
    matches_config,
    notification_candidates,
    price_radar_latest_url,
    save_state,
    load_state,
)


def make_offer(**overrides):
    value = {
        "id": "offer-1",
        "sourceTitle": "ChatGPT Plus 成品号 已接码 质保7天",
        "price": 9.81,
        "currency": "CNY",
        "status": "in_stock",
        "effectiveStatus": "available",
        "url": "https://seller.example/item/1",
        "sourceName": "示例渠道",
        "sourceStoreName": "示例商家",
        "stockCount": 15,
        "lastSeenAt": datetime.now(timezone.utc).isoformat(),
    }
    value.update(overrides)
    return Offer.from_api(value)


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "price_radar_latest_url": "https://data.priceai.cc/latest.json",
            "product_id": "chatgpt-plus",
            "preset_id": "account_verified",
            "max_price": 10,
            "min_price": 5,
            "min_stock": 1,
            "fresh_within_minutes": 120,
            "required_keywords": ["已接码"],
            "excluded_keywords": ["日抛", "不售后"],
        }

    def test_uses_official_price_radar_url(self):
        self.assertEqual(
            price_radar_latest_url(self.config),
            "https://data.priceai.cc/latest.json",
        )

    def test_extracts_verified_top_offers(self):
        raw_offer = {
            "id": "radar-1",
            "title": "ChatGPT Plus 成品号 已接码",
            "price": 9.5,
            "currency": "CNY",
            "status": "in_stock",
            "effective_status": "available",
            "url": "https://seller.example/item/radar-1",
            "source_name": "示例渠道",
            "source_store_name": "示例商家",
            "stock_count": 2,
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }
        snapshot = {
            "snapshot_id": "snapshot-1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "stale": False,
            "products": [
                {
                    "id": "chatgpt-plus",
                    "slug": "chatgpt-plus",
                    "presets": [
                        {
                            "id": "account_verified",
                            "total": 1,
                            "generated_at": datetime.now(timezone.utc).isoformat(),
                            "top_offers": [raw_offer],
                        }
                    ],
                }
            ],
        }
        offers, payload, raw = extract_price_radar_offers(
            snapshot, "chatgpt-plus", "account_verified"
        )
        self.assertEqual(len(offers), 1)
        self.assertEqual(offers[0].title, raw_offer["title"])
        self.assertEqual(offers[0].stock_count, 2)
        self.assertEqual(payload["source"], "price-radar.v1")
        self.assertEqual(raw, [raw_offer])

    def test_matching_offer(self):
        self.assertTrue(matches_config(make_offer(), self.config))
        self.assertTrue(matches_config(make_offer(price=10), self.config))

    def test_rejects_unavailable_and_excluded(self):
        self.assertFalse(matches_config(make_offer(status="out_of_stock"), self.config))
        self.assertFalse(matches_config(make_offer(sourceTitle="已接码 日抛"), self.config))
        self.assertFalse(matches_config(make_offer(price=10.01), self.config))

    def test_rejects_stale_offer_locally(self):
        stale = make_offer(lastSeenAt="2020-01-01T00:00:00Z")
        self.assertFalse(matches_config(stale, self.config))

    def test_notification_dedupe_and_price_drop(self):
        offer = make_offer()
        state = {
            "notified": {
                offer.id: {"price": 9.81, "notified_at_epoch": 1000}
            }
        }
        config = {"renotify_hours": 24}
        self.assertEqual(notification_candidates([offer], state, config, 1100), [])
        cheaper = make_offer(price=9.5)
        self.assertEqual(notification_candidates([cheaper], state, config, 1100), [cheaper])
        self.assertEqual(notification_candidates([offer], state, config, 1000 + 86400), [offer])

    def test_state_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            state = {"notified": {"one": {"price": 8.5}}}
            save_state(path, state)
            self.assertEqual(load_state(path), state)


if __name__ == "__main__":
    unittest.main()
