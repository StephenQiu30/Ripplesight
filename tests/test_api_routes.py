from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from services.api.app import create_app


class ApiRoutesTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(create_app())

    def test_list_sources_with_enabled_filter(self) -> None:
        response = self.client.get("/api/sources", params={"enabled": "true"})
        payload = response.json()

        self.assertEqual(200, response.status_code)
        self.assertEqual(2, payload["meta"]["total"])
        self.assertTrue(all(item["enabled"] for item in payload["items"]))

    def test_list_keyword_rules(self) -> None:
        response = self.client.get("/api/x/keywords")
        payload = response.json()

        self.assertEqual(200, response.status_code)
        self.assertEqual(2, len(payload["items"]))
        self.assertEqual(2, payload["meta"]["total"])

    def test_list_events_with_source_type_filter(self) -> None:
        response = self.client.get("/api/events", params={"source_type": "x"})
        payload = response.json()

        self.assertEqual(200, response.status_code)
        self.assertEqual(2, payload["meta"]["total"])

    def test_get_event_detail(self) -> None:
        list_response = self.client.get("/api/events")
        event_id = list_response.json()["items"][0]["id"]

        response = self.client.get(f"/api/events/{event_id}")
        payload = response.json()

        self.assertEqual(200, response.status_code)
        self.assertEqual(event_id, payload["id"])
        self.assertIn("summary_zh", payload)

    def test_get_today_digest(self) -> None:
        response = self.client.get("/api/digests/today")
        payload = response.json()

        self.assertEqual(200, response.status_code)
        self.assertIn("delivery_status", payload)
        self.assertEqual("assembled", payload["delivery_status"])
        self.assertIn("event_ids", payload)
        self.assertIsInstance(payload["event_ids"], list)

    def test_missing_event_returns_contract_error_shape(self) -> None:
        response = self.client.get("/api/events/does-not-exist")
        payload = response.json()

        self.assertEqual(404, response.status_code)
        self.assertEqual("event_not_found", payload["code"])
        self.assertIn("request_id", payload)


if __name__ == "__main__":
    unittest.main()
