from __future__ import annotations

import unittest

from backend.core.application import SourceGovernanceService
from backend.core.domain import AccessMethod, KeywordRule, MonitoredAccount, SourceConfig, SourceType
from backend.core.infrastructure import (
    InMemoryKeywordRuleRepository,
    InMemoryMonitoredAccountRepository,
    InMemorySourceConfigRepository,
)


class SourceGovernanceServiceTestCase(unittest.TestCase):
    def test_filters_enabled_records(self) -> None:
        service = SourceGovernanceService(
            source_repository=InMemorySourceConfigRepository(
                [
                    SourceConfig(
                        id="news-main",
                        name="News Main",
                        source_type=SourceType.NEWS,
                        access_method=AccessMethod.API,
                        language="en",
                        region="global",
                        weight=1.0,
                        poll_interval_minutes=30,
                        enabled=True,
                    ),
                    SourceConfig(
                        id="x-main",
                        name="X Main",
                        source_type=SourceType.X,
                        access_method=AccessMethod.API,
                        language="en",
                        region="global",
                        weight=0.8,
                        poll_interval_minutes=15,
                        enabled=False,
                    ),
                ]
            ),
            keyword_rule_repository=InMemoryKeywordRuleRepository(
                [
                    KeywordRule("kw-1", "openai", "company", "openai", 1, True),
                    KeywordRule("kw-2", "rumor", "noise", "rumor", 2, False),
                ]
            ),
            monitored_account_repository=InMemoryMonitoredAccountRepository(
                [
                    MonitoredAccount("acct-1", "x", "@openai", "OpenAI", "company", 1.0, True),
                    MonitoredAccount("acct-2", "x", "@noise", "Noise", "misc", 0.3, False),
                ]
            ),
        )

        self.assertEqual(["news-main"], [item.id for item in service.list_sources(enabled=True)])
        self.assertEqual(["kw-1"], [item.id for item in service.list_keyword_rules()])
        self.assertEqual(["acct-1"], [item.id for item in service.list_monitored_accounts()])


if __name__ == "__main__":
    unittest.main()
