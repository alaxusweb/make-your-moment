#!/usr/bin/env python3
"""Listing management CLI.

Division of labour: this tool does everything mechanical — enumerating
releases, guarding the release/listing link, checking Etsy limits, and talking
to the API. Writing the actual copy is Claude's job, because that is the part
that needs to read the market document and exercise judgement.

Typical loop:
    listing.py plan                     # Claude reads this to decide what to do
    ... Claude writes listings/drafts/<theme>/<year-month>.json ...
    listing.py validate --all
    listing.py push --release <key>     # dry run
    listing.py push --release <key> --apply
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
import urllib.parse
import webbrowser
from datetime import datetime, timedelta, timezone
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))

import draft as draft_module  # noqa: E402
import etsy_api  # noqa: E402
import registry as registry_module  # noqa: E402
import release as release_module  # noqa: E402

PROJECT_ROOT = TOOLS_DIR.parent.parent
MARKET_DOC = PROJECT_ROOT / "docs/compass_artifact.md"
REGISTRY_DB = PROJECT_ROOT / "listings/registry/registry.sqlite3"
ETSY_CONFIG = PROJECT_ROOT / "listings/config/etsy.json"


def market_doc_sha256() -> str | None:
    if not MARKET_DOC.exists():
        return None
    return release_module.sha256_file(MARKET_DOC)


def decide_action(
    link: registry_module.Link | None,
    draft_state: dict[str, object],
) -> str:
    if link is None:
        return "link_required"
    if not draft_state["exists"]:
        return "write_draft"
    if draft_state["invalid"]:
        return "fix_draft"
    if draft_state["stale_manifest"]:
        return "rewrite_draft_manifest_changed"
    if draft_state["stale_market_doc"]:
        return "rewrite_draft_market_changed"
    if link.pushed_draft != draft_state["content_sha256"]:
        return "push"
    return "up_to_date"


def build_plan() -> dict[str, object]:
    registry = registry_module.Registry(REGISTRY_DB)
    market_sha = market_doc_sha256()
    entries = []

    for rel in release_module.discover_releases(PROJECT_ROOT):
        link = registry.get(rel.key)
        path = draft_module.draft_path(PROJECT_ROOT, rel.key)
        draft_state: dict[str, object] = {
            "exists": path.exists(),
            "path": str(path.relative_to(PROJECT_ROOT)),
            "invalid": False,
            "stale_manifest": False,
            "stale_market_doc": False,
            "content_sha256": None,
        }
        if path.exists():
            try:
                loaded = draft_module.load_draft(path)
                draft_state["content_sha256"] = loaded.content_sha256
                draft_state["stale_manifest"] = (
                    loaded.manifest_sha256 != rel.manifest_sha256
                )
                draft_state["stale_market_doc"] = bool(
                    market_sha
                    and loaded.market_doc_sha256
                    and loaded.market_doc_sha256 != market_sha
                )
            except (ValueError, KeyError, json.JSONDecodeError) as error:
                draft_state["invalid"] = True
                draft_state["error"] = str(error)

        entries.append(
            {
                "release_key": rel.key,
                "action": decide_action(link, draft_state),
                "manifest": {
                    "sha256": rel.manifest_sha256,
                    "path": str(rel.manifest_path.relative_to(PROJECT_ROOT)),
                    "name_ja": rel.name_ja,
                    "name_en": rel.name_en,
                    "year": rel.year,
                    "month": rel.month,
                    "month_name_en": rel.month_name_en,
                    "month_label_ja": rel.month_label_ja,
                    "total_slots": rel.total_slots,
                    "calendar_days": rel.calendar_days,
                    "bonus_total": rel.bonus_total,
                    "canvas": f"{rel.width_px}x{rel.height_px}",
                    "dpi": rel.dpi,
                    "day_japanese": rel.day_japanese,
                    "day_romaji": rel.day_romaji,
                    "bonus_subjects": rel.bonus_subjects,
                },
                "link": (
                    {
                        "listing_id": link.listing_id,
                        "listing_url": link.listing_url,
                        "pushed_at": link.pushed_at,
                        "pushed_draft": link.pushed_draft,
                    }
                    if link
                    else None
                ),
                "draft": draft_state,
            }
        )

    return {
        "market_doc": {
            "path": str(MARKET_DOC.relative_to(PROJECT_ROOT)),
            "sha256": market_sha,
            "exists": MARKET_DOC.exists(),
        },
        "draft_schema": "listings/drafts/<theme>/<year-month>.json",
        "limits": {
            "title_max_chars": draft_module.TITLE_MAX_CHARS,
            "title_focus_window": draft_module.TITLE_FOCUS_WINDOW,
            "tags_count": draft_module.TAGS_MAX_COUNT,
            "tag_max_chars": draft_module.TAG_MAX_CHARS,
        },
        "releases": entries,
    }


def command_plan(args: argparse.Namespace) -> int:
    print(json.dumps(build_plan(), ensure_ascii=False, indent=2))
    return 0


def command_status(args: argparse.Namespace) -> int:
    plan = build_plan()
    rows = plan["releases"]
    if not rows:
        print("no releases found under output/releases")
        return 0
    width = max(len(str(row["release_key"])) for row in rows)
    print(f"market doc: {plan['market_doc']['path']} "
          f"({(plan['market_doc']['sha256'] or 'missing')[:12]})")
    print()
    for row in rows:
        link = row["link"]
        listing = link["listing_id"] if link else "-"
        print(
            f"{str(row['release_key']).ljust(width)}  "
            f"{str(row['action']).ljust(30)}  listing={listing}"
        )
    return 0


def resolve_release_keys(args: argparse.Namespace) -> list[str]:
    if getattr(args, "all", False):
        return [rel.key for rel in release_module.discover_releases(PROJECT_ROOT)]
    if not args.release:
        raise SystemExit("specify --release <theme>/<year-month> or --all")
    return [args.release]


def command_validate(args: argparse.Namespace) -> int:
    market_sha = market_doc_sha256()
    failed = False
    for key in resolve_release_keys(args):
        path = draft_module.draft_path(PROJECT_ROOT, key)
        if not path.exists():
            print(f"{key}: no draft at {path.relative_to(PROJECT_ROOT)}")
            failed = True
            continue
        rel = release_module.find_release(PROJECT_ROOT, key)
        loaded = draft_module.load_draft(path)
        issues = draft_module.validate_draft(
            loaded,
            current_manifest_sha256=rel.manifest_sha256,
            current_market_doc_sha256=market_sha,
        )
        if args.allow_no_ai_disclosure:
            issues = [i for i in issues if i.scope != "compliance"]
        print(f"{key}:")
        if not issues:
            print("  OK")
        for issue in issues:
            print(f"  {issue}")
        if draft_module.has_errors(issues):
            failed = True
    return 1 if failed else 0


def command_init_draft(args: argparse.Namespace) -> int:
    """Scaffold a draft with the hashes already filled in.

    Claude should never compute these by hand; a wrong hash would silently
    defeat the staleness check that protects against pushing outdated copy.
    """
    exit_code = 0
    for key in resolve_release_keys(args):
        rel = release_module.find_release(PROJECT_ROOT, key)
        path = draft_module.draft_path(PROJECT_ROOT, key)
        if path.exists() and not args.force:
            print(f"{key}: draft already exists ({path.relative_to(PROJECT_ROOT)}); "
                  f"use --force to overwrite")
            exit_code = 1
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        scaffold = {
            "draft_version": draft_module.DRAFT_VERSION,
            "release_key": rel.key,
            "source": {
                "manifest_sha256": rel.manifest_sha256,
                "market_doc_path": str(MARKET_DOC.relative_to(PROJECT_ROOT)),
                "market_doc_sha256": market_doc_sha256(),
                "written_at": registry_module.utc_now(),
                "written_by": args.written_by,
            },
            "focus_keyword": "",
            "focus_language": "en",
            # This shop is ja-primary: updateListing writes the Japanese copy
            # and the English copy goes through the en translation endpoint.
            "primary_language": "ja",
            "listings": {
                "en": {"title": "", "description": "", "tags": [], "materials": []},
                "ja": {"title": "", "description": "", "tags": [], "materials": []},
            },
            "compliance": {
                "ai_disclosure": True,
                "note": "Artwork is generated with AI image tools and composed "
                        "deterministically; disclosed per Etsy policy.",
            },
        }
        path.write_text(
            json.dumps(scaffold, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"{key}: scaffolded {path.relative_to(PROJECT_ROOT)}")
    return exit_code


def command_authorize(args: argparse.Namespace) -> int:
    """Run the PKCE grant and store the resulting refresh token."""
    import oauth  # noqa: PLC0415 - only needed for this command

    if not ETSY_CONFIG.exists():
        print(f"no {ETSY_CONFIG.relative_to(PROJECT_ROOT)}; copy etsy.example.json "
              f"and fill in keystring first", file=sys.stderr)
        return 1
    stored = json.loads(ETSY_CONFIG.read_text(encoding="utf-8"))
    try:
        keystring = etsy_api.check_credential("keystring", stored.get("keystring"))
    except etsy_api.EtsyError as error:
        print(f"failed: {error}", file=sys.stderr)
        return 1

    redirect_uri = (
        args.redirect_uri or stored.get("redirect_uri") or oauth.DEFAULT_REDIRECT
    )
    scopes = tuple(args.scope) if args.scope else oauth.DEFAULT_SCOPES
    pkce = oauth.Pkce.generate()
    state = secrets.token_urlsafe(16)
    url = oauth.build_authorize_url(
        keystring=keystring,
        redirect_uri=redirect_uri,
        scopes=scopes,
        state=state,
        challenge=pkce.challenge,
    )

    print(f"redirect_uri : {redirect_uri}")
    print(f"scopes       : {' '.join(scopes)}")
    print("\nこの URL をブラウザで開いて承認してください:\n")
    print(f"  {url}\n")

    is_local = urllib.parse.urlparse(redirect_uri).hostname in (
        "localhost",
        "127.0.0.1",
    )
    try:
        if args.paste or not is_local:
            if not args.paste:
                print("redirect_uri が localhost ではないため paste モードで待機します。")
            print("承認後、リダイレクト先の URL 全体を貼り付けてください")
            print("（ページが開けなくてもアドレスバーの URL でかまいません）:")
            received = oauth.parse_pasted_url(input("> "))
        else:
            if not args.no_browser:
                webbrowser.open(url)
            print(f"コールバック待機中… (最大 {oauth.CALLBACK_TIMEOUT_SECONDS}s)")
            received = oauth.wait_for_callback(redirect_uri)

        if received.get("error"):
            print(f"failed: Etsy returned {received['error']}: "
                  f"{received.get('error_description', '')}", file=sys.stderr)
            return 1
        if received.get("state") != state:
            print("failed: state mismatch. Discarding this callback.", file=sys.stderr)
            return 1
        code = received.get("code")
        if not code:
            print(f"failed: no code in callback: {received}", file=sys.stderr)
            return 1

        payload = oauth.exchange_code(
            keystring=keystring,
            redirect_uri=redirect_uri,
            code=code,
            verifier=pkce.verifier,
        )
    except oauth.OAuthError as error:
        print(f"failed: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\naborted", file=sys.stderr)
        return 1

    stored["refresh_token"] = payload["refresh_token"]
    stored["access_token"] = payload.get("access_token")
    expires_in = int(payload.get("expires_in", 3600))
    stored["access_token_expires_at"] = (
        datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    ).isoformat(timespec="seconds")
    stored["redirect_uri"] = redirect_uri
    ETSY_CONFIG.write_text(
        json.dumps(stored, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"\nwrote refresh_token and access_token into "
          f"{ETSY_CONFIG.relative_to(PROJECT_ROOT)}")

    try:
        config = etsy_api.EtsyConfig.load(ETSY_CONFIG)
        shop = etsy_api.EtsyClient(config).get_shop(config.shop_id)
        print(f"verified: authorized for shop {shop.get('shop_name')} "
              f"({shop.get('shop_id')})")
    except etsy_api.EtsyError as error:
        print(f"warning: token stored but the verification call failed: {error}")
        return 1
    return 0


def command_shop_listings(args: argparse.Namespace) -> int:
    """Enumerate the shop's listings so releases can be matched to them."""
    try:
        config = etsy_api.EtsyConfig.load(ETSY_CONFIG)
        items = etsy_api.EtsyClient(config).get_shop_listings(args.state)
    except etsy_api.EtsyError as error:
        print(f"failed: {error}", file=sys.stderr)
        return 1

    registry = registry_module.Registry(REGISTRY_DB)
    linked = {link.listing_id: link.release_key for link in registry.all_links()}
    if not items:
        print(f"no {args.state} listings")
        return 0
    for item in items:
        listing_id = str(item.get("listing_id"))
        owner = linked.get(listing_id)
        print(f"listing_id={listing_id}  "
              f"{'-> ' + owner if owner else '(未紐付け)'}")
        print(f"  title: {item.get('title')}")
        print(f"  tags : {', '.join(item.get('tags') or [])}")
        print(f"  url  : {item.get('url')}")
    return 0


def command_resolve_shop(args: argparse.Namespace) -> int:
    """Find shop_id by shop name and optionally write it into etsy.json."""
    keystring, shared_secret = args.keystring, args.shared_secret
    if not (keystring and shared_secret):
        if not ETSY_CONFIG.exists():
            print(
                f"no {ETSY_CONFIG.relative_to(PROJECT_ROOT)}; pass --keystring "
                f"and --shared-secret instead",
                file=sys.stderr,
            )
            return 1
        stored = json.loads(ETSY_CONFIG.read_text(encoding="utf-8"))
        keystring = keystring or stored.get("keystring")
        shared_secret = shared_secret or stored.get("shared_secret")

    try:
        shops = etsy_api.find_shop_by_name(keystring, shared_secret, args.shop_name)
    except etsy_api.EtsyError as error:
        print(f"failed: {error}", file=sys.stderr)
        return 1

    if not shops:
        print(f"no shop matched {args.shop_name!r}")
        return 1
    for shop in shops:
        print(f"  shop_id={shop.get('shop_id')}  {shop.get('shop_name')}  "
              f"({shop.get('url', '')})")

    exact = [
        shop
        for shop in shops
        if str(shop.get("shop_name", "")).lower() == args.shop_name.lower()
    ]
    if args.write:
        if len(exact) != 1:
            print("refusing to write: name did not match exactly one shop",
                  file=sys.stderr)
            return 1
        payload = json.loads(ETSY_CONFIG.read_text(encoding="utf-8"))
        payload["shop_id"] = str(exact[0]["shop_id"])
        ETSY_CONFIG.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"wrote shop_id={payload['shop_id']} into "
              f"{ETSY_CONFIG.relative_to(PROJECT_ROOT)}")
    return 0


def command_link(args: argparse.Namespace) -> int:
    rel = release_module.find_release(PROJECT_ROOT, args.release)
    registry = registry_module.Registry(REGISTRY_DB)
    try:
        link = registry.link(
            release_key=rel.key,
            theme_slug=rel.theme_slug,
            year_month=rel.year_month,
            listing_id=args.listing_id,
            manifest_sha256=rel.manifest_sha256,
            listing_url=args.url,
            note=args.note,
            force=args.force,
        )
    except registry_module.RegistryError as error:
        print(f"refused: {error}", file=sys.stderr)
        return 1
    print(f"linked {link.release_key} -> etsy listing {link.listing_id}")
    return 0


def command_unlink(args: argparse.Namespace) -> int:
    registry = registry_module.Registry(REGISTRY_DB)
    try:
        registry.unlink(args.release)
    except registry_module.RegistryError as error:
        print(f"refused: {error}", file=sys.stderr)
        return 1
    print(f"unlinked {args.release}")
    return 0


def command_export(args: argparse.Namespace) -> int:
    registry = registry_module.Registry(REGISTRY_DB)
    registry.export_json()
    print(f"wrote {registry.json_path.relative_to(PROJECT_ROOT)}")
    return 0


def command_push(args: argparse.Namespace) -> int:
    registry = registry_module.Registry(REGISTRY_DB)
    market_sha = market_doc_sha256()
    exit_code = 0

    for key in resolve_release_keys(args):
        print(f"\n=== {key} ===")
        rel = release_module.find_release(PROJECT_ROOT, key)
        link = registry.get(key)
        if link is None:
            print("  refused: not linked. Run 'listing.py link' first.")
            exit_code = 1
            continue

        path = draft_module.draft_path(PROJECT_ROOT, key)
        if not path.exists():
            print(f"  refused: no draft at {path.relative_to(PROJECT_ROOT)}")
            exit_code = 1
            continue

        loaded = draft_module.load_draft(path)
        issues = draft_module.validate_draft(
            loaded,
            current_manifest_sha256=rel.manifest_sha256,
            current_market_doc_sha256=market_sha,
        )
        if args.allow_no_ai_disclosure:
            issues = [i for i in issues if i.scope != "compliance"]
        for issue in issues:
            print(f"  {issue}")
        if draft_module.has_errors(issues):
            print("  refused: fix the errors above before pushing")
            exit_code = 1
            continue

        # --language lets a migration push only part of a draft, e.g. while the
        # shop's default language is being changed and one slot must be left
        # untouched.
        wanted = set(args.language) if args.language else None
        primary = loaded.listings[loaded.primary_language]
        primary_fields: dict[str, object] = {
            "title": primary.title,
            "description": primary.description,
            "tags": primary.tags,
        }
        if primary.materials:
            primary_fields["materials"] = primary.materials

        push_primary = wanted is None or loaded.primary_language in wanted

        if not args.apply:
            print(f"  dry run (listing {link.listing_id}); would send:")
            if push_primary:
                print(f"    [{loaded.primary_language}] PATCH title "
                      f"({len(primary.title)} chars)")
                print(f"      {primary.title}")
                print(f"    [{loaded.primary_language}] tags ({len(primary.tags)}): "
                      f"{', '.join(primary.tags)}")
                print(f"    [{loaded.primary_language}] description: "
                      f"{len(primary.description)} chars")
            else:
                print(f"    [{loaded.primary_language}] skipped (--language)")
            for language, localized in sorted(loaded.listings.items()):
                if language == loaded.primary_language:
                    continue
                if wanted is not None and language not in wanted:
                    print(f"    [{language}] skipped (--language)")
                    continue
                print(f"    [{language}] PUT translation title: {localized.title}")
                print(f"    [{language}] tags ({len(localized.tags)}): "
                      f"{', '.join(localized.tags)}")
            print("  re-run with --apply to send this to Etsy")
            continue

        try:
            config = etsy_api.EtsyConfig.load(ETSY_CONFIG)
            client = etsy_api.EtsyClient(config)
            if push_primary:
                client.update_listing(link.listing_id, primary_fields)
                etsy_api.throttle()

            for language, localized in sorted(loaded.listings.items()):
                if language == loaded.primary_language:
                    continue
                if wanted is not None and language not in wanted:
                    continue
                client.update_translation(
                    link.listing_id,
                    language,
                    {
                        "title": localized.title,
                        "description": localized.description,
                        "tags": localized.tags,
                    },
                )
                etsy_api.throttle()

            if push_primary:
                stored = client.get_listing(link.listing_id)
                problems = etsy_api.verify_applied(primary_fields, stored)
            else:
                problems = []
            for language, localized in sorted(loaded.listings.items()):
                if language == loaded.primary_language:
                    continue
                if wanted is not None and language not in wanted:
                    continue
                stored_translation = client.get_translation(link.listing_id, language)
                problems += [
                    f"[{language}] {problem}"
                    for problem in etsy_api.verify_applied(
                        {
                            "title": localized.title,
                            "description": localized.description,
                            "tags": localized.tags,
                        },
                        stored_translation,
                    )
                ]
            if problems:
                print("  pushed, but the read-back does not match:")
                for problem in problems:
                    print(f"    {problem}")
                print("  NOT marking as pushed; inspect the listing on Etsy.")
                exit_code = 1
                continue
        except etsy_api.EtsyError as error:
            print(f"  failed: {error}")
            exit_code = 1
            continue

        if wanted is not None:
            # A partial push does not represent the whole draft, so recording it
            # as pushed would hide the languages that are still outstanding.
            print(f"  applied and verified ({', '.join(sorted(wanted))} only); "
                  f"not recorded as a full push")
        else:
            registry.mark_pushed(
                release_key=key,
                manifest_sha256=rel.manifest_sha256,
                market_doc_sha256=market_sha,
                draft_sha256=loaded.content_sha256,
            )
            print(f"  applied and verified on listing {link.listing_id}")

    return exit_code


def oauth_default_redirect() -> str:
    import oauth  # noqa: PLC0415

    return oauth.DEFAULT_REDIRECT


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", help="machine-readable state for every release")
    plan.set_defaults(func=command_plan)

    status = sub.add_parser("status", help="human-readable summary")
    status.set_defaults(func=command_status)

    init_draft = sub.add_parser(
        "init-draft", help="scaffold a draft with source hashes filled in"
    )
    init_draft.add_argument("--release")
    init_draft.add_argument("--all", action="store_true")
    init_draft.add_argument("--force", action="store_true")
    init_draft.add_argument("--written-by", default="claude-code")
    init_draft.set_defaults(func=command_init_draft)

    validate = sub.add_parser("validate", help="check drafts against Etsy limits")
    validate.add_argument("--release")
    validate.add_argument("--all", action="store_true")
    validate.add_argument("--allow-no-ai-disclosure", action="store_true")
    validate.set_defaults(func=command_validate)

    push = sub.add_parser("push", help="send a draft to Etsy (dry run by default)")
    push.add_argument("--release")
    push.add_argument("--all", action="store_true")
    push.add_argument("--apply", action="store_true", help="actually write to Etsy")
    push.add_argument(
        "--language",
        action="append",
        help="repeatable; push only these languages (partial pushes are not "
        "recorded as complete)",
    )
    push.add_argument("--allow-no-ai-disclosure", action="store_true")
    push.set_defaults(func=command_push)

    authorize = sub.add_parser(
        "authorize", help="run the OAuth PKCE grant and store the refresh token"
    )
    authorize.add_argument(
        "--redirect-uri",
        help=f"must match the app registration (default {oauth_default_redirect()})",
    )
    authorize.add_argument(
        "--scope", action="append", help="repeatable; defaults to listings_r/w shops_r"
    )
    authorize.add_argument(
        "--paste", action="store_true", help="paste the redirected URL by hand"
    )
    authorize.add_argument("--no-browser", action="store_true")
    authorize.set_defaults(func=command_authorize)

    shop_listings = sub.add_parser(
        "shop-listings", help="list the shop's Etsy listings and their link state"
    )
    shop_listings.add_argument(
        "--state", default="active", choices=("active", "draft", "inactive", "expired")
    )
    shop_listings.set_defaults(func=command_shop_listings)

    resolve_shop = sub.add_parser(
        "resolve-shop", help="find shop_id by shop name (API key only, no OAuth)"
    )
    resolve_shop.add_argument("--shop-name", required=True)
    resolve_shop.add_argument("--keystring", help="defaults to the one in etsy.json")
    resolve_shop.add_argument(
        "--shared-secret", help="defaults to the one in etsy.json"
    )
    resolve_shop.add_argument(
        "--write", action="store_true", help="save shop_id into etsy.json"
    )
    resolve_shop.set_defaults(func=command_resolve_shop)

    link = sub.add_parser("link", help="bind a release to an existing Etsy listing")
    link.add_argument("--release", required=True)
    link.add_argument("--listing-id", required=True)
    link.add_argument("--url")
    link.add_argument("--note")
    link.add_argument("--force", action="store_true")
    link.set_defaults(func=command_link)

    unlink = sub.add_parser("unlink", help="remove a release/listing link")
    unlink.add_argument("--release", required=True)
    unlink.set_defaults(func=command_unlink)

    export = sub.add_parser("export", help="rewrite registry.json from the database")
    export.set_defaults(func=command_export)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
