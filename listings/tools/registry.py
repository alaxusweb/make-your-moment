#!/usr/bin/env python3
"""Link releases to Etsy listings and refuse ambiguous or stale updates.

SQLite is the write path because its constraints enforce the one-to-one link at
the storage layer. Every mutation also rewrites registry.json so the link table
stays reviewable in git and readable without a SQLite client.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS links (
    release_key       TEXT PRIMARY KEY,
    theme_slug        TEXT NOT NULL,
    year_month        TEXT NOT NULL,
    marketplace       TEXT NOT NULL DEFAULT 'etsy',
    listing_id        TEXT NOT NULL,
    listing_url       TEXT,
    linked_manifest   TEXT NOT NULL,
    linked_at         TEXT NOT NULL,
    pushed_at         TEXT,
    pushed_manifest   TEXT,
    pushed_market_doc TEXT,
    pushed_draft      TEXT,
    note              TEXT,
    UNIQUE (marketplace, listing_id)
);
"""


@dataclass(frozen=True)
class Link:
    release_key: str
    theme_slug: str
    year_month: str
    marketplace: str
    listing_id: str
    listing_url: str | None
    linked_manifest: str
    linked_at: str
    pushed_at: str | None
    pushed_manifest: str | None
    pushed_market_doc: str | None
    pushed_draft: str | None
    note: str | None


class RegistryError(RuntimeError):
    """Raised when an operation would create an ambiguous or unsafe link."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Registry:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.json_path = database_path.with_suffix(".json")
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def all_links(self) -> list[Link]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM links ORDER BY release_key"
            ).fetchall()
        return [Link(**dict(row)) for row in rows]

    def get(self, release_key: str) -> Link | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM links WHERE release_key = ?", (release_key,)
            ).fetchone()
        return Link(**dict(row)) if row else None

    def find_by_listing_id(self, marketplace: str, listing_id: str) -> Link | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM links WHERE marketplace = ? AND listing_id = ?",
                (marketplace, listing_id),
            ).fetchone()
        return Link(**dict(row)) if row else None

    def link(
        self,
        *,
        release_key: str,
        theme_slug: str,
        year_month: str,
        listing_id: str,
        manifest_sha256: str,
        marketplace: str = "etsy",
        listing_url: str | None = None,
        note: str | None = None,
        force: bool = False,
    ) -> Link:
        """Bind one release to one Etsy listing, refusing both kinds of collision."""
        existing = self.get(release_key)
        if existing and existing.listing_id != listing_id and not force:
            raise RegistryError(
                f"{release_key} is already linked to {existing.marketplace} "
                f"listing {existing.listing_id}. Re-run with --force only if the "
                f"listing was genuinely replaced."
            )
        occupant = self.find_by_listing_id(marketplace, listing_id)
        if occupant and occupant.release_key != release_key:
            raise RegistryError(
                f"{marketplace} listing {listing_id} is already linked to "
                f"{occupant.release_key}. One listing cannot serve two releases."
            )

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO links (
                    release_key, theme_slug, year_month, marketplace, listing_id,
                    listing_url, linked_manifest, linked_at, note
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(release_key) DO UPDATE SET
                    listing_id      = excluded.listing_id,
                    listing_url     = excluded.listing_url,
                    linked_manifest = excluded.linked_manifest,
                    linked_at       = excluded.linked_at,
                    note            = excluded.note
                """,
                (
                    release_key,
                    theme_slug,
                    year_month,
                    marketplace,
                    listing_id,
                    listing_url,
                    manifest_sha256,
                    utc_now(),
                    note,
                ),
            )
        self.export_json()
        link = self.get(release_key)
        assert link is not None
        return link

    def unlink(self, release_key: str) -> None:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM links WHERE release_key = ?", (release_key,)
            )
            if cursor.rowcount == 0:
                raise RegistryError(f"{release_key} is not linked")
        self.export_json()

    def mark_pushed(
        self,
        *,
        release_key: str,
        manifest_sha256: str,
        market_doc_sha256: str | None,
        draft_sha256: str,
    ) -> None:
        """Record exactly which inputs produced the content now live on Etsy."""
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE links SET
                    pushed_at         = ?,
                    pushed_manifest   = ?,
                    pushed_market_doc = ?,
                    pushed_draft      = ?
                WHERE release_key = ?
                """,
                (
                    utc_now(),
                    manifest_sha256,
                    market_doc_sha256,
                    draft_sha256,
                    release_key,
                ),
            )
            if cursor.rowcount == 0:
                raise RegistryError(f"{release_key} is not linked")
        self.export_json()

    def export_json(self) -> None:
        payload = {
            "exported_at": utc_now(),
            "links": [asdict(link) for link in self.all_links()],
        }
        self.json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
