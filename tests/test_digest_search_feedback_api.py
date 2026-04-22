from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from services.api.app import create_app


class DigestSearchFeedbackApiTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(create_app())

    def test_get_today_digest(self) -> None:
        response = self.client.get("/api/digests/today")
        payload = response.json()

        self.assertEqual(200, response.status_code)
        self.assertIn("digest_date", payload)
        self.assertGreaterEqual(len(payload["event_ids"]), 1)

    def test_search_events(self) -> None:
        response = self.client.get("/api/search", params={"q": "reasoning"})
        payload = response.json()

        self.assertEqual(200, response.status_code)
        self.assertGreaterEqual(payload["meta"]["total"], 1)
        self.assertTrue(any("reasoning" in item["event_title"].lower() for item in payload["items"]))

    def test_submit_feedback(self) -> None:
        response = self.client.post(
            "/api/feedback",
            json={
                "target_type": "event",
                "target_id": "openai-releases-a-new-reasoning-model",
                "feedback_type": "favorite",
                "comment": "值得继续跟踪",
            },
        )
        payload = response.json()

        self.assertEqual(201, response.status_code)
        self.assertEqual("event", payload["target_type"])
        self.assertEqual("favorite", payload["feedback_type"])
        self.assertIn("id", payload)
        self.assertIn("created_at", payload)


if __name__ == "__main__":
    unittest.main()
