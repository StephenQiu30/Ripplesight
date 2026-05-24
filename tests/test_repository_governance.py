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

    def test_no_apps_directory_as_backend_entry(self):
        apps_dir = ROOT / "apps"
        self.assertFalse(
            apps_dir.exists(),
            "检测到遗留的 apps 目录，后端交付应使用 server 作为唯一后端入口",
        )

    def test_docs_declare_server_as_only_backend_entry(self):
        docs_readme = self.read_text("docs/README.md")

        self.assertIn("server", docs_readme)
        self.assertIn("后端服务入口", docs_readme)
        self.assertIn("apps", docs_readme)


if __name__ == "__main__":
    unittest.main()
