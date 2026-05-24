from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RepositoryGovernanceTest(unittest.TestCase):
    def read_text(self, relative_path: str) -> str:
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_agents_declares_server_as_cross_repo_source_of_truth(self):
        agents = self.read_text("AGENTS.md")

        self.assertIn("HotKey 跨仓通用规范", agents)
        self.assertIn("hotkey-server 是跨仓库 AGENTS.md 主规范源", agents)
        self.assertIn("OpenAPI 契约事实源", agents)
        self.assertIn("Web 和小程序不得手写后端 API 类型", agents)
        self.assertIn("server -> web -> miniapp -> 回归", agents)

    def test_readme_declares_server_scope_and_validation_command(self):
        readme = self.read_text("README.md")

        self.assertIn("# hotkey-server", readme)
        self.assertIn("FastAPI 后端", readme)
        self.assertIn("Swagger/OpenAPI", readme)
        self.assertIn("python3 -m unittest discover -s tests -p 'test_repository_governance.py'", readme)


if __name__ == "__main__":
    unittest.main()
