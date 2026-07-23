#!/usr/bin/env python3
"""One-shot Etsy OAuth 2.0 PKCE authorization.

Produces the refresh_token that every later API call depends on. Two ways to
receive the callback:

  local   a throwaway HTTP server catches the redirect (needs Etsy to accept a
          http://localhost redirect_uri)
  paste   you copy the redirected URL out of the browser address bar

Paste mode always works, because even when the browser cannot load the
redirect target the address bar still carries ?code=...&state=...
"""

from __future__ import annotations

import base64
import hashlib
import http.server
import json
import secrets
import threading
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass
from pathlib import Path

TOKEN_URL = "https://api.etsy.com/v3/public/oauth/token"
CONNECT_URL = "https://www.etsy.com/oauth/connect"
DEFAULT_SCOPES = ("listings_r", "listings_w", "shops_r")
DEFAULT_REDIRECT = "http://localhost:3003/oauth/redirect"
CALLBACK_TIMEOUT_SECONDS = 300


class OAuthError(RuntimeError):
    pass


@dataclass(frozen=True)
class Pkce:
    verifier: str
    challenge: str

    @classmethod
    def generate(cls) -> Pkce:
        # RFC 7636: 43-128 chars from [A-Za-z0-9._~-]. token_urlsafe gives us
        # exactly that alphabet minus the padding.
        verifier = secrets.token_urlsafe(64)[:128]
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
        return cls(verifier=verifier, challenge=challenge)


def build_authorize_url(
    *, keystring: str, redirect_uri: str, scopes: tuple[str, ...],
    state: str, challenge: str,
) -> str:
    query = urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": keystring,
            "redirect_uri": redirect_uri,
            "scope": " ".join(scopes),
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
        # Etsy's documented example encodes the scope separator as %20, not +.
        quote_via=urllib.parse.quote,
    )
    return f"{CONNECT_URL}?{query}"


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    received: dict[str, str] = {}

    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        _CallbackHandler.received = {
            key: values[0] for key, values in params.items()
        }
        body = (
            "<html><body style='font-family:sans-serif;padding:3rem'>"
            "<h2>認可を受け取りました</h2>"
            "<p>ターミナルへ戻ってください。このタブは閉じて構いません。</p>"
            "</body></html>"
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        """Silence the default stderr access log."""


def wait_for_callback(redirect_uri: str) -> dict[str, str]:
    parsed = urllib.parse.urlparse(redirect_uri)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    _CallbackHandler.received = {}
    server = http.server.HTTPServer(("127.0.0.1", port), _CallbackHandler)
    server.timeout = CALLBACK_TIMEOUT_SECONDS

    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    thread.join(timeout=CALLBACK_TIMEOUT_SECONDS)
    server.server_close()

    if not _CallbackHandler.received:
        raise OAuthError(
            f"no callback received on port {port} within "
            f"{CALLBACK_TIMEOUT_SECONDS}s. Re-run with --paste."
        )
    return _CallbackHandler.received


def parse_pasted_url(pasted: str) -> dict[str, str]:
    parsed = urllib.parse.urlparse(pasted.strip())
    params = urllib.parse.parse_qs(parsed.query)
    if not params:
        raise OAuthError(f"no query parameters found in {pasted!r}")
    return {key: values[0] for key, values in params.items()}


def exchange_code(
    *, keystring: str, redirect_uri: str, code: str, verifier: str
) -> dict[str, object]:
    body = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "client_id": keystring,
            "redirect_uri": redirect_uri,
            "code": code,
            "code_verifier": verifier,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        TOKEN_URL,
        data=body,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise OAuthError(f"token exchange failed [{error.code}]: {detail}") from error
    if "refresh_token" not in payload:
        raise OAuthError(f"token response contained no refresh_token: {payload}")
    return payload
