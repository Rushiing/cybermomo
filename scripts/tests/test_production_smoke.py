import json
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from production_smoke import Response, run_checks  # noqa: E402


FRONTEND = "https://cybermomo-app.up.railway.app"
BACKEND = "https://cybermomo-production.up.railway.app"


class ProductionSmokeTests(unittest.TestCase):
    def test_all_read_only_checks_pass(self):
        responses = {
            f"{BACKEND}/healthz": Response(200, {}, b'{"ok": true}'),
            f"{FRONTEND}/": Response(200, {}, b"<title>CyberMOMO</title>"),
            f"{FRONTEND}/api/auth/me": Response(
                401,
                {},
                json.dumps({"detail": "未登录"}, ensure_ascii=False).encode(),
            ),
            f"{FRONTEND}/api/auth/google/login": Response(
                302,
                {
                    "location": (
                        "https://accounts.google.com/o/oauth2/v2/auth?"
                        "redirect_uri=https%3A%2F%2Fcybermomo-app.up.railway.app%2F"
                        "api%2Fauth%2Fgoogle%2Fcallback"
                    ),
                    "set-cookie": "cm_oauth_state=test; HttpOnly; Secure",
                },
                b"",
            ),
        }

        def requester(url, _timeout):
            return responses[url]

        checks = run_checks(FRONTEND, BACKEND, 1, True, requester=requester)

        self.assertTrue(all(check.ok for check in checks))
        self.assertEqual(
            [check.name for check in checks],
            ["backend_health", "frontend_home", "frontend_api_proxy", "oauth_redirect"],
        )

    def test_proxy_failure_is_reported_without_stopping_other_checks(self):
        def requester(url, _timeout):
            if url.endswith("/healthz"):
                return Response(200, {}, b'{"ok": true}')
            if url.endswith("/api/auth/me"):
                return Response(502, {}, b"bad gateway")
            return Response(200, {}, b"CyberMOMO")

        checks = run_checks(FRONTEND, BACKEND, 1, False, requester=requester)

        self.assertEqual(len(checks), 3)
        self.assertTrue(checks[0].ok)
        self.assertTrue(checks[1].ok)
        self.assertFalse(checks[2].ok)
        self.assertIn("got 502", checks[2].detail)

    def test_oauth_rejects_old_callback_domain(self):
        def requester(url, _timeout):
            if url.endswith("/healthz"):
                return Response(200, {}, b'{"ok": true}')
            if url.endswith("/api/auth/me"):
                return Response(
                    401,
                    {},
                    json.dumps({"detail": "未登录"}, ensure_ascii=False).encode(),
                )
            if url.endswith("/api/auth/google/login"):
                return Response(
                    302,
                    {
                        "location": (
                            "https://accounts.google.com/o/oauth2/v2/auth?"
                            "redirect_uri=https%3A%2F%2Fcybermomo.up.railway.app%2F"
                            "api%2Fauth%2Fgoogle%2Fcallback"
                        ),
                        "set-cookie": "cm_oauth_state=test",
                    },
                    b"",
                )
            return Response(200, {}, b"CyberMOMO")

        checks = run_checks(FRONTEND, BACKEND, 1, True, requester=requester)

        self.assertFalse(checks[-1].ok)
        self.assertIn("formal domain", checks[-1].detail)


if __name__ == "__main__":
    unittest.main()
