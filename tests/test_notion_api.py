from __future__ import annotations

import unittest

from automation.notion_api import NotionClient


class NotionClientTest(unittest.TestCase):
    def test_client_initializes_under_slots_dataclass(self) -> None:
        with NotionClient(token="test-token", api_version="2026-03-11") as client:
            self.assertEqual(client._client.base_url.host, "api.notion.com")


if __name__ == "__main__":
    unittest.main()
