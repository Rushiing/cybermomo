#!/usr/bin/env python3
"""Read-only smoke checks for the public CyberMOMO production path."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


DEFAULT_FRONTEND_URL = "https://cybermomo-app.up.railway.app"
DEFAULT_BACKEND_URL = "https://cybermomo-production.up.railway.app"
MAX_BODY_BYTES = 256 * 1024


@dataclass(frozen=True)
class Response:
    status: int
    headers: dict[str, str]
    body: bytes


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str
    duration_ms: int


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def fetch(url: str, timeout: float) -> Response:
    request = Request(url, headers={"User-Agent": "CyberMOMO-production-smoke/1.0"})
    opener = build_opener(NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as response:
            return Response(
                status=response.status,
                headers={key.lower(): value for key, value in response.headers.items()},
                body=response.read(MAX_BODY_BYTES),
            )
    except HTTPError as exc:
        return Response(
            status=exc.code,
            headers={key.lower(): value for key, value in exc.headers.items()},
            body=exc.read(MAX_BODY_BYTES),
        )
    except URLError as exc:
        raise RuntimeError(f"request failed: {exc.reason}") from exc


def _timed_check(name: str, check: Callable[[], str]) -> CheckResult:
    started = time.monotonic()
    try:
        detail = check()
        ok = True
    except (AssertionError, RuntimeError, ValueError) as exc:
        detail = str(exc)
        ok = False
    return CheckResult(
        name=name,
        ok=ok,
        detail=detail,
        duration_ms=round((time.monotonic() - started) * 1000),
    )


def run_checks(
    frontend_url: str,
    backend_url: str,
    timeout: float,
    check_oauth_redirect: bool,
    requester: Callable[[str, float], Response] = fetch,
) -> list[CheckResult]:
    frontend_url = frontend_url.rstrip("/") + "/"
    backend_url = backend_url.rstrip("/") + "/"

    def backend_health() -> str:
        response = requester(urljoin(backend_url, "healthz"), timeout)
        assert response.status == 200, f"expected 200, got {response.status}"
        payload = json.loads(response.body)
        assert payload.get("ok") is True, "health payload did not contain ok=true"
        return "HTTP 200 and ok=true"

    def frontend_home() -> str:
        response = requester(frontend_url, timeout)
        assert response.status == 200, f"expected 200, got {response.status}"
        html = response.body.decode("utf-8", errors="replace")
        assert "CyberMOMO" in html, "CyberMOMO marker missing from rendered HTML"
        return "HTTP 200 and CyberMOMO marker present"

    def frontend_api_proxy() -> str:
        response = requester(urljoin(frontend_url, "api/auth/me"), timeout)
        assert response.status == 401, f"expected anonymous 401, got {response.status}"
        payload = json.loads(response.body)
        assert payload.get("detail") == "未登录", "unexpected anonymous auth response"
        return "same-origin /api reached backend and returned expected anonymous 401"

    checks = [
        _timed_check("backend_health", backend_health),
        _timed_check("frontend_home", frontend_home),
        _timed_check("frontend_api_proxy", frontend_api_proxy),
    ]

    if check_oauth_redirect:

        def oauth_redirect() -> str:
            response = requester(urljoin(frontend_url, "api/auth/google/login"), timeout)
            assert response.status in {302, 303, 307, 308}, (
                f"expected redirect, got {response.status}"
            )
            location = response.headers.get("location", "")
            parsed = urlparse(location)
            assert parsed.hostname == "accounts.google.com", "redirect host is not Google"
            redirect_uri = parse_qs(parsed.query).get("redirect_uri", [""])[0]
            expected_uri = urljoin(frontend_url, "api/auth/google/callback")
            assert redirect_uri == expected_uri, "Google redirect_uri does not use formal domain"
            assert "cm_oauth_state=" in response.headers.get("set-cookie", ""), (
                "OAuth state cookie missing"
            )
            return "Google redirect, formal callback and state cookie verified"

        checks.append(_timed_check("oauth_redirect", oauth_redirect))

    return checks


def build_report(args: argparse.Namespace, checks: list[CheckResult]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "frontend_url": args.frontend_url.rstrip("/"),
        "backend_url": args.backend_url.rstrip("/"),
        "oauth_redirect_checked": args.check_oauth_redirect,
        "ok": all(check.ok for check in checks),
        "checks": [asdict(check) for check in checks],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frontend-url", default=DEFAULT_FRONTEND_URL)
    parser.add_argument("--backend-url", default=DEFAULT_BACKEND_URL)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--check-oauth-redirect", action="store_true")
    parser.add_argument("--json-output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    checks = run_checks(
        frontend_url=args.frontend_url,
        backend_url=args.backend_url,
        timeout=args.timeout,
        check_oauth_redirect=args.check_oauth_redirect,
    )
    report = build_report(args, checks)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.json_output:
        args.json_output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
