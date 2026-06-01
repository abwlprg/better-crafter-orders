"""Unit tests for the temporary admin API key guard."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "functions"))
import api


class TestAdminApiKeyGuard(unittest.TestCase):
    def setUp(self) -> None:
        self._old_key = os.environ.get("ADMIN_API_KEY")

    def tearDown(self) -> None:
        if self._old_key is None:
            os.environ.pop("ADMIN_API_KEY", None)
        else:
            os.environ["ADMIN_API_KEY"] = self._old_key

    def test_health_remains_public(self) -> None:
        os.environ.pop("ADMIN_API_KEY", None)

        result = api.health()

        self.assertEqual(result["status"], "ok")

    def test_route_dependencies_are_applied_to_protected_endpoints(self) -> None:
        routes = {getattr(route, "path", ""): route for route in api.app.routes}
        protected_paths = {
            "/api/batch-orders",
            "/api/append-to-onedrive",
            "/api/gmail-webhook",
            "/api/clear-onedrive-rows",
            "/api/daily-update",
            "/api/renew-gmail-watch",
        }

        for path in protected_paths:
            dependant = routes[path].dependant
            self.assertTrue(
                any(dep.call is api.require_admin_api_key for dep in dependant.dependencies),
                f"{path} should require the admin API key",
            )

        health_dependant = routes["/api/health"].dependant
        self.assertFalse(
            any(dep.call is api.require_admin_api_key for dep in health_dependant.dependencies)
        )

    def test_missing_admin_key_fails_closed(self) -> None:
        os.environ.pop("ADMIN_API_KEY", None)

        with self.assertRaises(HTTPException) as ctx:
            api.require_admin_api_key("unit-test-admin-key")

        self.assertEqual(ctx.exception.status_code, 403)

    def test_placeholder_admin_key_fails_closed(self) -> None:
        os.environ["ADMIN_API_KEY"] = "placeholder_local_admin_api_key"

        with self.assertRaises(HTTPException) as ctx:
            api.require_admin_api_key("placeholder_local_admin_api_key")

        self.assertEqual(ctx.exception.status_code, 403)

    def test_missing_header_is_rejected(self) -> None:
        os.environ["ADMIN_API_KEY"] = "unit-test-admin-key"

        with self.assertRaises(HTTPException) as ctx:
            api.require_admin_api_key(None)

        self.assertEqual(ctx.exception.status_code, 401)

    def test_wrong_header_is_rejected(self) -> None:
        os.environ["ADMIN_API_KEY"] = "unit-test-admin-key"

        with self.assertRaises(HTTPException) as ctx:
            api.require_admin_api_key("wrong-key")

        self.assertEqual(ctx.exception.status_code, 401)

    def test_correct_header_passes_guard(self) -> None:
        os.environ["ADMIN_API_KEY"] = "unit-test-admin-key"

        api.require_admin_api_key("unit-test-admin-key")


if __name__ == "__main__":
    unittest.main()
