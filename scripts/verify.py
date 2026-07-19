#!/usr/bin/env python3
"""Verify one theme/month customer package and its QA PDF."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops
from pypdf import PdfReader


def read_manifest(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def resolve_paths(project_root: Path, manifest: dict[str, Any]) -> dict[str, Path]:
    artifacts = manifest["artifacts"]
    customer_dir = project_root / artifacts["customer_directory"]
    qa_dir = project_root / artifacts["qa_directory"]
    return {
        "individual_dir": project_root / artifacts["individual_directory"],
        "png": customer_dir / artifacts["png_filename"],
        "pdf": customer_dir / artifacts["pdf_filename"],
        "alignment_pdf": qa_dir / artifacts["alignment_pdf_filename"],
    }


def check_individuals(paths: dict[str, Path], manifest: dict[str, Any]) -> None:
    items = manifest["day_stickers"] + manifest["bonuses"]
    if len(items) != 35:
        raise AssertionError(f"expected 35 individual stickers, got {len(items)}")
    for item in items:
        path = paths["individual_dir"] / item["source"]
        if not path.exists():
            raise AssertionError(f"missing individual sticker: {path}")
        with Image.open(path) as image:
            if image.mode != "RGBA":
                raise AssertionError(f"individual is not RGBA: {path} mode={image.mode}")
            corners = [
                image.getpixel((0, 0))[3],
                image.getpixel((image.width - 1, 0))[3],
                image.getpixel((0, image.height - 1))[3],
                image.getpixel((image.width - 1, image.height - 1))[3],
            ]
            if any(corners):
                raise AssertionError(f"individual has nontransparent corner: {path}")


def check_png(path: Path, manifest: dict[str, Any]) -> None:
    canvas = manifest["canvas"]
    with Image.open(path) as image:
        if image.size != (canvas["width_px"], canvas["height_px"]):
            raise AssertionError(f"wrong PNG size: {image.size}")
        if image.mode != "RGBA":
            raise AssertionError(f"PNG must be RGBA, got {image.mode}")
        dpi = image.info.get("dpi")
        if not dpi or any(abs(value - canvas["dpi"]) > 0.2 for value in dpi):
            raise AssertionError(f"PNG dpi metadata is wrong: {dpi}")
        corners = [
            image.getpixel((0, 0))[3],
            image.getpixel((image.width - 1, 0))[3],
            image.getpixel((0, image.height - 1))[3],
            image.getpixel((image.width - 1, image.height - 1))[3],
        ]
        if any(corners):
            raise AssertionError(f"PNG corners are not transparent: {corners}")


def dereference(value: Any) -> Any:
    return value.get_object() if hasattr(value, "get_object") else value


def check_pdf(path: Path, manifest: dict[str, Any]) -> None:
    reader = PdfReader(path)
    if reader.is_encrypted:
        raise AssertionError("customer PDF must not be encrypted")
    if len(reader.pages) != 1:
        raise AssertionError(f"customer PDF must be one page, got {len(reader.pages)}")
    page = reader.pages[0]
    canvas = manifest["canvas"]
    expected_width = canvas["width_px"] / canvas["dpi"] * 72
    expected_height = canvas["height_px"] / canvas["dpi"] * 72
    actual_width = float(page.mediabox.width)
    actual_height = float(page.mediabox.height)
    if abs(actual_width - expected_width) > 0.01 or abs(actual_height - expected_height) > 0.01:
        raise AssertionError(
            f"wrong PDF page size: {(actual_width, actual_height)}"
        )

    extracted = page.extract_text() or ""
    expected_labels = [
        f"{item['japanese_name']} / {item['romaji']}"
        for item in manifest["day_stickers"]
    ]
    missing = [label for label in expected_labels if label not in extracted]
    if missing:
        raise AssertionError(f"missing editable labels: {missing}")
    forbidden = [
        manifest["theme"]["title_line"],
        "\n".join(manifest["theme"]["concept_lines"]),
    ]
    if any(text in extracted for text in forbidden):
        raise AssertionError("title or concept text is unexpectedly editable")

    resources = dereference(page["/Resources"])
    fonts = dereference(resources.get("/Font", {}))
    has_embedded_unicode_font = False
    for font_reference in fonts.values():
        font = dereference(font_reference)
        descriptor_reference = font.get("/FontDescriptor")
        descriptor = dereference(descriptor_reference) if descriptor_reference else {}
        embedded = any(key in descriptor for key in ("/FontFile", "/FontFile2", "/FontFile3"))
        unicode_map = "/ToUnicode" in font
        if embedded and unicode_map:
            has_embedded_unicode_font = True
            break
    if not has_embedded_unicode_font:
        raise AssertionError("no embedded Unicode font found for editable labels")

    xobjects = dereference(resources.get("/XObject", {}))
    has_soft_mask = False
    for object_reference in xobjects.values():
        image_object = dereference(object_reference)
        if image_object.get("/Subtype") == "/Image" and "/SMask" in image_object:
            has_soft_mask = True
            break
    if not has_soft_mask:
        raise AssertionError("PDF raster design does not contain an alpha soft mask")


def compare_pdf_render_to_png(
    pdf_path: Path, png_path: Path, manifest: dict[str, Any]
) -> None:
    pdftocairo = shutil.which("pdftocairo")
    if not pdftocairo:
        raise AssertionError("pdftocairo is required for PDF/PNG comparison")
    canvas = manifest["canvas"]
    with tempfile.TemporaryDirectory(prefix="sticker-verify-") as temporary_directory:
        prefix = Path(temporary_directory) / "render"
        subprocess.run(
            [
                pdftocairo,
                "-png",
                "-transp",
                "-singlefile",
                "-scale-to-x",
                str(canvas["width_px"]),
                "-scale-to-y",
                str(canvas["height_px"]),
                str(pdf_path),
                str(prefix),
            ],
            check=True,
        )
        with Image.open(prefix.with_suffix(".png")) as rendered, Image.open(png_path) as png:
            difference = ImageChops.difference(rendered.convert("RGBA"), png.convert("RGBA"))
            if difference.getbbox() is not None:
                raise AssertionError("customer PNG does not exactly match the customer PDF render")


def build_parser(project_root: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=project_root
        / "output/releases/japanese-summer-flowers/2026-07/manifest.json",
    )
    return parser


def main() -> int:
    project_root = Path(__file__).resolve().parent.parent
    args = build_parser(project_root).parse_args()
    manifest = read_manifest(args.manifest.resolve())
    paths = resolve_paths(project_root, manifest)

    check_individuals(paths, manifest)
    check_png(paths["png"], manifest)
    check_pdf(paths["pdf"], manifest)
    if not paths["alignment_pdf"].exists():
        raise AssertionError(f"missing QA alignment PDF: {paths['alignment_pdf']}")
    check_pdf(paths["alignment_pdf"], manifest)
    compare_pdf_render_to_png(paths["pdf"], paths["png"], manifest)

    print("PASS: 35 clean individual RGBA stickers")
    print("PASS: 3072x2048 RGBA PNG with transparent corners and 300 dpi metadata")
    print("PASS: one-page PDF with editable day labels only")
    print("PASS: embedded Unicode label font and raster alpha soft mask")
    print("PASS: customer PNG exactly matches the customer PDF render")
    print("PASS: QA alignment PDF exists and matches the page contract")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        sys.exit(1)
