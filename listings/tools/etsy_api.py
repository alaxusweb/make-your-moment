#!/usr/bin/env python3
"""Minimal Etsy Open API v3 client built on the standard library.

Endpoints used (verified against developers.etsy.com, 2026-07):
  PATCH /v3/application/shops/{shop_id}/listings/{listing_id}
  PUT   /v3/application/shops/{shop_id}/listings/{listing_id}/translations/{language}
  GET   /v3/application/listings/{listing_id}
  POST  https://api.etsy.com/v3/public/oauth/token   (grant_type=refresh_token)

Etsy's own documentation is inconsistent about whether write bodies should be
form-encoded or JSON, so both are supported and every push reads the listing
back to confirm what actually landed. Never trust the 200; trust the read-back.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

API_BASE = "https://openapi.etsy.com/v3/application"
TOKEN_URL = "https://api.etsy.com/v3/public/oauth/token"
REQUIRED_SCOPE = "listings_w"

BodyEncoding = Literal["form", "json"]


class EtsyError(RuntimeError):
    pass


def check_credential(name: str, value: str) -> str:
    """Reject placeholder or malformed credentials with a readable message.

    HTTP header values must be latin-1 encodable, so an unedited Japanese
    placeholder would otherwise surface as a UnicodeEncodeError traceback.
    """
    value = (value or "").strip()
    if not value:
        raise EtsyError(f"{name} is empty in etsy.json")
    if not value.isascii() or any(character.isspace() for character in value):
        raise EtsyError(
            f"{name} still looks like the placeholder from etsy.example.json "
            f"({value!r}). Replace it with the real value from the Etsy "
            f"developer dashboard."
        )
    return value


@dataclass
class EtsyConfig:
    path: Path
    keystring: str
    shared_secret: str
    shop_id: str
    refresh_token: str
    access_token: str | None = None
    access_token_expires_at: str | None = None
    body_encoding: BodyEncoding = "form"
    # Shape of new listings, mirrored from the shop's existing products rather
    # than hardcoded, so a taxonomy or policy change is a config edit.
    listing_defaults: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> EtsyConfig:
        if not path.exists():
            raise EtsyError(
                f"missing Etsy credentials at {path}. Copy etsy.example.json to "
                f"etsy.json and fill it in."
            )
        payload = json.loads(path.read_text(encoding="utf-8"))
        missing = [
            key
            for key in ("keystring", "shared_secret", "shop_id", "refresh_token")
            if not payload.get(key)
        ]
        if missing:
            raise EtsyError(f"{path} is missing required fields: {missing}")
        return cls(
            path=path,
            keystring=check_credential("keystring", payload["keystring"]),
            shared_secret=check_credential(
                "shared_secret", payload["shared_secret"]
            ),
            shop_id=check_credential("shop_id", str(payload["shop_id"])),
            refresh_token=check_credential("refresh_token", payload["refresh_token"]),
            access_token=payload.get("access_token"),
            access_token_expires_at=payload.get("access_token_expires_at"),
            body_encoding=payload.get("body_encoding", "form"),
            listing_defaults=payload.get("listing_defaults", {}),
        )

    def save(self) -> None:
        payload = {
            "keystring": self.keystring,
            "shared_secret": self.shared_secret,
            "shop_id": self.shop_id,
            "refresh_token": self.refresh_token,
            "access_token": self.access_token,
            "access_token_expires_at": self.access_token_expires_at,
            "body_encoding": self.body_encoding,
            "listing_defaults": self.listing_defaults,
        }
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    @property
    def token_is_fresh(self) -> bool:
        if not self.access_token or not self.access_token_expires_at:
            return False
        expiry = datetime.fromisoformat(self.access_token_expires_at)
        # Refresh a minute early so a slow push cannot straddle the expiry.
        return datetime.now(timezone.utc) < expiry - timedelta(seconds=60)


def _http(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    request = urllib.request.Request(
        url, data=body, method=method, headers=headers or {}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            text = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        if error.code == 429:
            raise EtsyError(f"rate limited by Etsy (429): {detail}") from error
        raise EtsyError(f"{method} {url} failed [{error.code}]: {detail}") from error
    except urllib.error.URLError as error:
        raise EtsyError(f"{method} {url} failed: {error.reason}") from error
    return json.loads(text) if text else {}


class EtsyClient:
    def __init__(self, config: EtsyConfig) -> None:
        self.config = config
        # Observed 2026-07: this account's OAuth calls also require the shared
        # secret, not just the keystring the docs show. Start combined to avoid
        # burning a 403 round-trip; _request falls back the other way if some
        # other account behaves as documented.
        self._use_combined_key = True

    def _ensure_token(self) -> str:
        if self.config.token_is_fresh:
            assert self.config.access_token is not None
            return self.config.access_token

        body = urllib.parse.urlencode(
            {
                "grant_type": "refresh_token",
                "client_id": self.config.keystring,
                "refresh_token": self.config.refresh_token,
            }
        ).encode("utf-8")
        payload = _http(
            TOKEN_URL,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            body=body,
        )
        if "access_token" not in payload:
            raise EtsyError(f"token refresh returned no access_token: {payload}")

        self.config.access_token = payload["access_token"]
        expires_in = int(payload.get("expires_in", 3600))
        self.config.access_token_expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        ).isoformat(timespec="seconds")
        # Etsy rotates the refresh token on every use; losing it means redoing
        # the whole OAuth grant by hand.
        if payload.get("refresh_token"):
            self.config.refresh_token = payload["refresh_token"]
        self.config.save()
        return self.config.access_token

    def _headers(self, content_type: str | None = None) -> dict[str, str]:
        headers = {
            "x-api-key": (
                f"{self.config.keystring}:{self.config.shared_secret}"
                if self._use_combined_key
                else self.config.keystring
            ),
            "Authorization": f"Bearer {self._ensure_token()}",
            "Accept": "application/json",
        }
        if content_type:
            headers["Content-Type"] = f"{content_type}; charset=utf-8"
        return headers

    def _request(self, *args, **kwargs) -> dict[str, Any]:
        """Issue a request, switching x-api-key format if Etsy demands it.

        Etsy requires 'keystring:shared_secret' for unauthenticated calls but
        documents the bare keystring for OAuth calls. Rather than guess which
        applies here, start with the documented form and adopt the combined one
        the moment Etsy asks for it.
        """
        try:
            return _http(*args, **kwargs)
        except EtsyError as error:
            if "403" not in str(error) or "api-key" not in str(error).lower():
                raise
            self._use_combined_key = not self._use_combined_key
            headers = kwargs.get("headers", {})
            headers["x-api-key"] = (
                f"{self.config.keystring}:{self.config.shared_secret}"
                if self._use_combined_key
                else self.config.keystring
            )
            return _http(*args, **kwargs)

    def _encode_body(self, fields: dict[str, Any]) -> tuple[bytes, str]:
        if self.config.body_encoding == "json":
            return json.dumps(fields, ensure_ascii=False).encode("utf-8"), (
                "application/json"
            )
        form: dict[str, str] = {}
        for key, value in fields.items():
            # Etsy's form encoding takes array fields as comma-joined strings.
            form[key] = ",".join(value) if isinstance(value, list) else str(value)
        return urllib.parse.urlencode(form).encode("utf-8"), (
            "application/x-www-form-urlencoded"
        )

    def get_shop(self, shop_id: str) -> dict[str, Any]:
        return self._request(
            f"{API_BASE}/shops/{shop_id}",
            method="GET",
            headers=self._headers(),
        )

    def create_draft_listing(self, fields: dict[str, Any]) -> dict[str, Any]:
        """Create a new listing in draft state.

        Drafts are never visible to buyers, so a registration run cannot
        accidentally put an unfinished product on sale. Activating it stays a
        manual step in Shop Manager, where price and files are reviewed.
        """
        body, content_type = self._encode_body(fields)
        return self._request(
            f"{API_BASE}/shops/{self.config.shop_id}/listings",
            method="POST",
            headers=self._headers(content_type),
            body=body,
        )

    def get_shop_listings(self, state: str = "active") -> list[dict[str, Any]]:
        """Enumerate the shop's listings so folders can be matched to them."""
        query = urllib.parse.urlencode({"state": state, "limit": 100})
        payload = self._request(
            f"{API_BASE}/shops/{self.config.shop_id}/listings?{query}",
            method="GET",
            headers=self._headers(),
        )
        return payload.get("results", [])

    def get_listing(self, listing_id: str) -> dict[str, Any]:
        return self._request(
            f"{API_BASE}/listings/{listing_id}",
            method="GET",
            headers=self._headers(),
        )

    def update_listing(self, listing_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        body, content_type = self._encode_body(fields)
        return self._request(
            f"{API_BASE}/shops/{self.config.shop_id}/listings/{listing_id}",
            method="PATCH",
            headers=self._headers(content_type),
            body=body,
        )

    def update_translation(
        self, listing_id: str, language: str, fields: dict[str, Any]
    ) -> dict[str, Any]:
        body, content_type = self._encode_body(fields)
        return self._request(
            f"{API_BASE}/shops/{self.config.shop_id}/listings/{listing_id}"
            f"/translations/{language}",
            method="PUT",
            headers=self._headers(content_type),
            body=body,
        )

    def get_translation(self, listing_id: str, language: str) -> dict[str, Any]:
        return self._request(
            f"{API_BASE}/shops/{self.config.shop_id}/listings/{listing_id}"
            f"/translations/{language}",
            method="GET",
            headers=self._headers(),
        )


def find_shop_by_name(
    keystring: str, shared_secret: str, shop_name: str
) -> list[dict[str, Any]]:
    """Look up shop_id from a shop name.

    findShops needs no OAuth token, so this works before the authorization
    grant -- which matters because shop_id is not shown anywhere in Shop
    Manager. Etsy rejects unauthenticated calls that send only the keystring
    ("Shared secret is required in x-api-key header"), so the combined form is
    mandatory here even though OAuth calls use the bare keystring.
    """
    key = check_credential("keystring", keystring)
    secret = check_credential("shared_secret", shared_secret)
    # The generated client docs say "shopName"; the live API rejects that and
    # wants snake_case.
    query = urllib.parse.urlencode({"shop_name": shop_name, "limit": 25})
    payload = _http(
        f"{API_BASE}/shops?{query}",
        method="GET",
        headers={"x-api-key": f"{key}:{secret}", "Accept": "application/json"},
    )
    return payload.get("results", [])


def verify_applied(
    expected: dict[str, Any], actual: dict[str, Any]
) -> list[str]:
    """Compare what we sent against what Etsy stored. Returns mismatch messages."""
    problems: list[str] = []
    for field, want in expected.items():
        got = actual.get(field)
        if isinstance(want, list):
            if [item.strip() for item in want] != [
                str(item).strip() for item in (got or [])
            ]:
                problems.append(f"{field}: sent {want!r} but Etsy stored {got!r}")
        elif (want or "").strip() != str(got or "").strip():
            problems.append(
                f"{field}: sent {len(want or '')} chars but Etsy stored "
                f"{len(str(got or ''))} chars"
            )
    return problems


def throttle(seconds: float = 0.25) -> None:
    """Stay well inside Etsy's per-second quota when looping over releases."""
    time.sleep(seconds)
