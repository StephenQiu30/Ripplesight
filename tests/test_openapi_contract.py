from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.export_openapi import export_openapi_schema


class OpenApiContractTests(unittest.TestCase):
    def test_export_openapi_schema_writes_m1_contract_for_clients(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "openapi.json"

            export_openapi_schema(output_path)

            schema = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(schema["openapi"].split(".")[0], "3")
        self.assertIn("/api/auth/register", schema["paths"])
        self.assertIn("/api/auth/miniapp/login", schema["paths"])
        self.assertIn("/api/auth/token/refresh", schema["paths"])
        self.assertIn("/api/hotspots", schema["paths"])

        schemas = schema["components"]["schemas"]
        self.assertIn("EmailRegisterRequest", schemas)
        self.assertIn("MiniappLoginRequest", schemas)
        self.assertIn("HotspotRead", schemas)
        self.assertIn("AiAnalysisRead", schemas)
        self.assertIn("TopicIdeaRead", schemas)

        hotspot_properties = schemas["HotspotRead"]["properties"]
        self.assertIn("rank_score", hotspot_properties)
        self.assertIn("trend_score", hotspot_properties)
        self.assertIn("cluster_id", hotspot_properties)

        ai_properties = schemas["AiAnalysisRead"]["properties"]
        self.assertIn("quick_understanding", ai_properties)
        self.assertIn("topic_ideas", ai_properties)


if __name__ == "__main__":
    unittest.main()
