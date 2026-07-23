#!/usr/bin/env python3
"""Read release manifests from output/ and expose them as listing source facts.

This module is read-only with respect to output/. The image production pipeline
owns those files; the listing tools only observe them.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MONTH_NAMES_EN = {
    1: "January",
    2: "February",
    3: "March",
    4: "April",
    5: "May",
    6: "June",
    7: "July",
    8: "August",
    9: "September",
    10: "October",
    11: "November",
    12: "December",
}


@dataclass(frozen=True)
class Release:
    """One theme/month release, derived entirely from its manifest."""

    theme_slug: str
    year_month: str
    manifest_path: Path
    manifest_sha256: str
    name_ja: str
    name_en: str
    month_label_ja: str
    calendar_days: int
    random_bonuses: int
    concept_seals: int
    total_slots: int
    width_px: int
    height_px: int
    dpi: int
    day_romaji: list[str]
    day_japanese: list[str]
    bonus_subjects: list[str]
    png_filename: str
    pdf_filename: str
    customer_directory: str

    @property
    def key(self) -> str:
        return f"{self.theme_slug}/{self.year_month}"

    @property
    def year(self) -> int:
        return int(self.year_month.split("-")[0])

    @property
    def month(self) -> int:
        return int(self.year_month.split("-")[1])

    @property
    def month_name_en(self) -> str:
        return MONTH_NAMES_EN[self.month]

    @property
    def bonus_total(self) -> int:
        return self.random_bonuses + self.concept_seals


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_release(manifest_path: Path) -> Release:
    with manifest_path.open(encoding="utf-8") as handle:
        manifest: dict[str, Any] = json.load(handle)
    if manifest.get("schema_version") != 1:
        raise ValueError(f"unsupported manifest schema_version: {manifest_path}")

    theme = manifest["theme"]
    canvas = manifest["canvas"]
    counts = manifest["counts"]
    artifacts = manifest["artifacts"]

    return Release(
        theme_slug=theme["slug"],
        year_month=theme["year_month"],
        manifest_path=manifest_path,
        manifest_sha256=sha256_file(manifest_path),
        name_ja=theme["name_ja"],
        name_en=theme["name_en"],
        month_label_ja=theme["month_label_ja"],
        calendar_days=counts["calendar_days"],
        random_bonuses=counts["random_bonuses"],
        concept_seals=counts["concept_seals"],
        total_slots=counts["total_slots"],
        width_px=canvas["width_px"],
        height_px=canvas["height_px"],
        dpi=canvas["dpi"],
        day_romaji=[item["romaji"] for item in manifest["day_stickers"]],
        day_japanese=[item["japanese_name"] for item in manifest["day_stickers"]],
        bonus_subjects=[item["subject"] for item in manifest["bonuses"]],
        png_filename=artifacts["png_filename"],
        pdf_filename=artifacts["pdf_filename"],
        customer_directory=artifacts["customer_directory"],
    )


def discover_releases(project_root: Path) -> list[Release]:
    """Find every release manifest under output/releases, sorted by key."""
    pattern = "output/releases/*/*/manifest.json"
    releases = [load_release(path) for path in sorted(project_root.glob(pattern))]
    return sorted(releases, key=lambda release: release.key)


def find_release(project_root: Path, release_key: str) -> Release:
    manifest_path = project_root / "output/releases" / release_key / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"no manifest for release: {release_key}")
    release = load_release(manifest_path)
    if release.key != release_key:
        raise ValueError(
            f"manifest theme/year_month ({release.key}) does not match its "
            f"directory ({release_key})"
        )
    return release
