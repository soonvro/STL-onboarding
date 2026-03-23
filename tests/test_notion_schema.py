from __future__ import annotations

import unittest

from automation.notion_schema import CREATABLE_DATABASE_PROPERTIES, DATABASE_PROPERTY_SPECS


class NotionSchemaTest(unittest.TestCase):
    def test_request_id_is_not_in_required_schema(self) -> None:
        self.assertNotIn("RequestId", DATABASE_PROPERTY_SPECS)
        self.assertNotIn("RequestId", CREATABLE_DATABASE_PROPERTIES)


if __name__ == "__main__":
    unittest.main()
