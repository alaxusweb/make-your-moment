#!/usr/bin/env python3
"""Turn the transparent delivery PNG into a listing photo (JPEG).

Two things make this more than a format conversion:

1. JPEG has no alpha. Converting the delivery PNG directly would flatten the
   transparent background to black. The artwork is composited onto an opaque
   background first.
2. The listing photo must not double as a free copy of the product. It is
   downscaled well below print resolution by default.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image

# Etsy renders listing photos up to roughly 1600 px wide, so anything past that
# only helps someone trying to print the shop photo instead of buying the file.
DEFAULT_WIDTH_PX = 1600
DEFAULT_QUALITY = 88
DEFAULT_BACKGROUND = "#FFFFFF"


def parse_color(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    if len(value) != 6:
        raise ValueError(f"expected #RRGGBB, got {value!r}")
    return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))


def build_photo(
    source: Path,
    output: Path,
    *,
    width_px: int,
    background: tuple[int, int, int],
    quality: int,
    square: bool,
) -> tuple[int, int]:
    with Image.open(source) as raw:
        artwork = raw.convert("RGBA")

    scale = width_px / artwork.width
    resized = artwork.resize(
        (width_px, max(1, round(artwork.height * scale))), Image.Resampling.LANCZOS
    )

    if square:
        side = max(resized.width, resized.height)
        canvas = Image.new("RGB", (side, side), background)
        canvas.paste(
            resized,
            ((side - resized.width) // 2, (side - resized.height) // 2),
            resized,
        )
    else:
        canvas = Image.new("RGB", resized.size, background)
        canvas.paste(resized, (0, 0), resized)

    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(
        output,
        format="JPEG",
        quality=quality,
        optimize=True,
        progressive=True,
        dpi=(72, 72),
    )
    return canvas.size


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True,
                        help="the transparent delivery PNG")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH_PX)
    parser.add_argument("--background", default=DEFAULT_BACKGROUND,
                        help="hex colour behind the transparent artwork")
    parser.add_argument("--quality", type=int, default=DEFAULT_QUALITY)
    parser.add_argument("--square", action="store_true",
                        help="pad to a square canvas for uncropped thumbnails")
    args = parser.parse_args()

    if not args.source.exists():
        print(f"missing source: {args.source}", file=sys.stderr)
        return 1

    size = build_photo(
        args.source,
        args.output,
        width_px=args.width,
        background=parse_color(args.background),
        quality=args.quality,
        square=args.square,
    )
    kilobytes = args.output.stat().st_size // 1024
    print(f"wrote {args.output}")
    print(f"  {size[0]}x{size[1]} px, {kilobytes} KB, background {args.background}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
