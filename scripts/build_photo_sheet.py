#!/usr/bin/env python3
"""Build the listing sheet image (rank-2 product photo) from a delivery PNG.

The customer sheet PNG is a 300 dpi transparent RGBA file. Etsy product photos
are opaque JPEGs, so this flattens the sheet onto a solid background, scales it
down, and writes a 72 dpi JPEG for `output/releases/<theme>/<year-month>/marketing/`.

Background is a near-white ivory by default: it reads as a clean catalogue photo
and keeps the white die-cut borders faintly visible. The sheet's month title is
drawn in a pale colour, so on a light background it becomes subtle; that is an
accepted trade-off. Pass --background '#ffffff' for pure white, or any hex for a
darker card. See docs/LISTING_SHEET_IMAGE_SPEC.md.

The delivery sheet is far larger than a product photo needs, so it is scaled so
its long edge is --long-edge px (default 1200).

The output name must contain "photo-sheet" so that listing.py upload picks it up
as image rank 2 (rank 1 is the eyecatch). This tool never touches customer/.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    if len(value) != 6:
        raise ValueError(f"background must be a 6-digit hex colour, got {value!r}")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def build_photo_sheet(
    input_path: Path,
    output_path: Path,
    *,
    background: str = "#f5f2ec",
    long_edge: int = 1200,
    quality: int = 90,
    dpi: int = 72,
) -> None:
    source = Image.open(input_path).convert("RGBA")
    if long_edge and max(source.size) > long_edge:
        scale = long_edge / max(source.size)
        new_size = (round(source.width * scale), round(source.height * scale))
        source = source.resize(new_size, Image.LANCZOS)
    canvas = Image.new("RGB", source.size, _hex_to_rgb(background))
    canvas.paste(source, (0, 0), source)  # alpha channel as the paste mask
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(
        output_path,
        format="JPEG",
        quality=quality,
        dpi=(dpi, dpi),
        optimize=True,
        progressive=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path,
                        help="customer delivery PNG (transparent, 300 dpi)")
    parser.add_argument("--output", required=True, type=Path,
                        help="marketing JPEG path; name must contain 'photo-sheet'")
    parser.add_argument("--background", default="#f5f2ec",
                        help="solid background hex colour (default near-white ivory)")
    parser.add_argument("--long-edge", type=int, default=1200,
                        help="scale so the long edge is this many px (default 1200)")
    parser.add_argument("--quality", type=int, default=90)
    args = parser.parse_args()

    if "photo-sheet" not in args.output.name:
        parser.error("--output name must contain 'photo-sheet' so upload finds it")

    build_photo_sheet(
        args.input,
        args.output,
        background=args.background,
        long_edge=args.long_edge,
        quality=args.quality,
    )
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
