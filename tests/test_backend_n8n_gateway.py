from __future__ import annotations

import unittest

from backend.app.n8n_gateway import N8nWorkflowGateway


class BackendN8nGatewayTest(unittest.TestCase):
    def test_gateway_initializes_http_client_under_slots_dataclass(self) -> None:
        gateway = N8nWorkflowGateway(
            base_url="https://n8n.example.com",
            shared_secret="shared-secret",
            register_path="register",
            complete_path="complete",
        )
        try:
            self.assertIsNotNone(gateway._client)
        finally:
            gateway.close()
