#!/usr/bin/env python3
"""Draft schema and Etsy constraint validation.

Claude writes drafts; this module decides whether a draft is allowed anywhere
near the Etsy API. Validation is deliberately mechanical so that a subjective
copywriting step still lands inside objective marketplace limits.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

DRAFT_VERSION = 1
SUPPORTED_LANGUAGES = ("en", "ja")

# Etsy listing limits. See developers.etsy.com updateListing / updateListingTranslation.
TITLE_MAX_CHARS = 140
TAGS_MAX_COUNT = 13
TAG_MAX_CHARS = 20
MATERIALS_MAX_COUNT = 13
MATERIAL_MAX_CHARS = 45
# Etsy allows each of these at most once in a title.
TITLE_LIMITED_ONCE = ("%", ":", "&", "+")
# Etsy tag charset: letters, numbers, whitespace, and these marks only.
TAG_EXTRA_ALLOWED = set("-'™©®")

# compass_artifact.md: the first 40 characters carry the search weight.
TITLE_FOCUS_WINDOW = 40

Level = Literal["error", "warning"]


@dataclass(frozen=True)
class Issue:
    level: Level
    scope: str
    message: str

    def __str__(self) -> str:
        marker = "ERROR" if self.level == "error" else "WARN "
        return f"{marker} [{self.scope}] {self.message}"


@dataclass(frozen=True)
class Localized:
    title: str
    description: str
    tags: list[str]
    materials: list[str]


@dataclass(frozen=True)
class Draft:
    release_key: str
    manifest_sha256: str
    market_doc_path: str | None
    market_doc_sha256: str | None
    written_at: str | None
    written_by: str | None
    focus_keyword: str | None
    focus_language: str
    primary_language: str
    listings: dict[str, Localized]
    ai_disclosure: bool
    ai_disclosure_note: str | None
    raw: dict[str, Any]

    @property
    def content_sha256(self) -> str:
        """Hash of the copy only, so re-hashing is stable across metadata edits."""
        payload = {
            language: {
                "title": localized.title,
                "description": localized.description,
                "tags": localized.tags,
                "materials": localized.materials,
            }
            for language, localized in sorted(self.listings.items())
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def draft_path(project_root: Path, release_key: str) -> Path:
    return project_root / "listings/drafts" / f"{release_key}.json"


def load_draft(path: Path) -> Draft:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if payload.get("draft_version") != DRAFT_VERSION:
        raise ValueError(
            f"unsupported draft_version in {path}: {payload.get('draft_version')}"
        )

    source = payload.get("source", {})
    compliance = payload.get("compliance", {})
    listings: dict[str, Localized] = {}
    for language, block in payload.get("listings", {}).items():
        listings[language] = Localized(
            title=block.get("title", ""),
            description=block.get("description", ""),
            tags=list(block.get("tags", [])),
            materials=list(block.get("materials", [])),
        )

    return Draft(
        release_key=payload["release_key"],
        manifest_sha256=source.get("manifest_sha256", ""),
        market_doc_path=source.get("market_doc_path"),
        market_doc_sha256=source.get("market_doc_sha256"),
        written_at=source.get("written_at"),
        written_by=source.get("written_by"),
        focus_keyword=payload.get("focus_keyword"),
        focus_language=payload.get("focus_language", "en"),
        primary_language=payload.get("primary_language", "en"),
        listings=listings,
        ai_disclosure=bool(compliance.get("ai_disclosure", False)),
        ai_disclosure_note=compliance.get("note"),
        raw=payload,
    )


def _printable(text: str) -> bool:
    return all(
        unicodedata.category(character)[0] in "LNPSZ" or character in " \t\n"
        for character in text
    )


def _validate_title(title: str, language: str, focus: str | None) -> list[Issue]:
    scope = f"{language}.title"
    issues: list[Issue] = []
    if not title.strip():
        return [Issue("error", scope, "title is empty")]
    if len(title) > TITLE_MAX_CHARS:
        issues.append(
            Issue(
                "error",
                scope,
                f"{len(title)} characters exceeds the Etsy limit of {TITLE_MAX_CHARS}",
            )
        )
    if not _printable(title):
        issues.append(Issue("error", scope, "title contains disallowed characters"))
    for character in TITLE_LIMITED_ONCE:
        count = title.count(character)
        if count > 1:
            issues.append(
                Issue(
                    "error",
                    scope,
                    f"'{character}' appears {count} times; Etsy allows it once",
                )
            )
    if focus:
        window = title[:TITLE_FOCUS_WINDOW]
        if focus.lower() not in window.lower():
            issues.append(
                Issue(
                    "warning",
                    scope,
                    f"focus keyword {focus!r} is not inside the first "
                    f"{TITLE_FOCUS_WINDOW} characters ({window!r})",
                )
            )
    return issues


def _validate_tags(tags: list[str], language: str) -> list[Issue]:
    scope = f"{language}.tags"
    issues: list[Issue] = []
    if len(tags) > TAGS_MAX_COUNT:
        issues.append(
            Issue(
                "error",
                scope,
                f"{len(tags)} tags exceeds the Etsy limit of {TAGS_MAX_COUNT}",
            )
        )
    elif len(tags) < TAGS_MAX_COUNT:
        issues.append(
            Issue(
                "warning",
                scope,
                f"only {len(tags)} of {TAGS_MAX_COUNT} tags used; unused tags are "
                f"wasted search surface",
            )
        )

    seen: dict[str, int] = {}
    for index, tag in enumerate(tags):
        if not tag.strip():
            issues.append(Issue("error", scope, f"tag {index + 1} is empty"))
            continue
        if len(tag) > TAG_MAX_CHARS:
            issues.append(
                Issue(
                    "error",
                    scope,
                    f"{tag!r} is {len(tag)} characters; Etsy allows {TAG_MAX_CHARS}",
                )
            )
        invalid = {
            character
            for character in tag
            if not (
                character.isalnum()
                or character.isspace()
                or character in TAG_EXTRA_ALLOWED
            )
        }
        if invalid:
            issues.append(
                Issue(
                    "error",
                    scope,
                    f"{tag!r} contains disallowed characters: {sorted(invalid)}",
                )
            )
        normalized = tag.strip().lower()
        if normalized in seen:
            issues.append(
                Issue(
                    "error",
                    scope,
                    f"{tag!r} duplicates tag {seen[normalized] + 1}",
                )
            )
        else:
            seen[normalized] = index
    return issues


def _validate_materials(materials: list[str], language: str) -> list[Issue]:
    scope = f"{language}.materials"
    issues: list[Issue] = []
    if len(materials) > MATERIALS_MAX_COUNT:
        issues.append(
            Issue(
                "error",
                scope,
                f"{len(materials)} materials exceeds the limit of {MATERIALS_MAX_COUNT}",
            )
        )
    for material in materials:
        if len(material) > MATERIAL_MAX_CHARS:
            issues.append(
                Issue(
                    "error",
                    scope,
                    f"{material!r} is {len(material)} characters; limit is "
                    f"{MATERIAL_MAX_CHARS}",
                )
            )
        if not all(
            character.isalnum() or character.isspace() for character in material
        ):
            issues.append(
                Issue(
                    "error",
                    scope,
                    f"{material!r} must contain only letters, numbers and spaces",
                )
            )
    return issues


def validate_draft(draft: Draft, *, current_manifest_sha256: str | None = None,
                   current_market_doc_sha256: str | None = None) -> list[Issue]:
    """Check Etsy hard limits, SEO advisories, and input freshness."""
    issues: list[Issue] = []

    if draft.primary_language not in draft.listings:
        issues.append(
            Issue(
                "error",
                "draft",
                f"primary_language {draft.primary_language!r} has no listing block",
            )
        )
    for language in draft.listings:
        if language not in SUPPORTED_LANGUAGES:
            issues.append(
                Issue("error", "draft", f"unsupported language: {language!r}")
            )

    for language, localized in sorted(draft.listings.items()):
        # The focus keyword belongs to one language's search surface, which is
        # not necessarily the primary one: this shop's listings are ja-primary
        # while the money keywords live in the en translation.
        focus = draft.focus_keyword if language == draft.focus_language else None
        issues.extend(_validate_title(localized.title, language, focus))
        if not localized.description.strip():
            issues.append(
                Issue("error", f"{language}.description", "description is empty")
            )
        issues.extend(_validate_tags(localized.tags, language))
        issues.extend(_validate_materials(localized.materials, language))

    # compass_artifact.md L90: Etsy began enforcing generative-AI disclosure on
    # 2026-01-14. Artwork in this repository is image-generated, so a draft that
    # does not disclose is a policy violation, not a style choice.
    if not draft.ai_disclosure:
        issues.append(
            Issue(
                "error",
                "compliance",
                "ai_disclosure is false. Etsy requires disclosing AI-generated "
                "artwork; set it true, or record why this release is exempt in "
                "compliance.note and re-run with --allow-no-ai-disclosure.",
            )
        )

    if current_manifest_sha256 and draft.manifest_sha256 != current_manifest_sha256:
        issues.append(
            Issue(
                "error",
                "freshness",
                "the manifest changed after this draft was written; the copy may "
                "describe stickers that no longer exist. Rewrite the draft.",
            )
        )
    if (
        current_market_doc_sha256
        and draft.market_doc_sha256
        and draft.market_doc_sha256 != current_market_doc_sha256
    ):
        issues.append(
            Issue(
                "warning",
                "freshness",
                "the market document changed after this draft was written; "
                "keywords may be stale.",
            )
        )

    return issues


def has_errors(issues: list[Issue]) -> bool:
    return any(issue.level == "error" for issue in issues)
