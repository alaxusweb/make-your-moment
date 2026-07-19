#!/usr/bin/env python3
"""Build a reusable square marketplace eyecatch from project assets."""

from __future__ import annotations

import argparse
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


CANVAS_SIZE = 1024
NAVY = "#082D52"
CORAL = "#EE4B2B"
TEAL = "#157A86"
GOLD = "#E8A928"
CREAM = "#FFF8E9"
INK = "#183149"


def font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size)


def alpha_crop(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    bounds = rgba.getchannel("A").getbbox()
    return rgba.crop(bounds) if bounds else rgba


def fit(image: Image.Image, max_width: int, max_height: int) -> Image.Image:
    scale = min(max_width / image.width, max_height / image.height)
    size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    return image.resize(size, Image.Resampling.LANCZOS)


def paste_center(canvas: Image.Image, image: Image.Image, center: tuple[int, int]) -> None:
    x = round(center[0] - image.width / 2)
    y = round(center[1] - image.height / 2)
    canvas.alpha_composite(image, (x, y))


def sticker_with_shadow(path: Path, size: int, angle: float) -> Image.Image:
    sticker = fit(alpha_crop(Image.open(path)), size, size)
    sticker = sticker.rotate(angle, Image.Resampling.BICUBIC, expand=True)
    shadow = Image.new("RGBA", sticker.size, (0, 0, 0, 0))
    shadow.putalpha(sticker.getchannel("A").filter(ImageFilter.GaussianBlur(8)))
    tinted = Image.new("RGBA", sticker.size, (8, 45, 82, 55))
    tinted.putalpha(shadow.getchannel("A").point(lambda value: round(value * 0.22)))
    result = Image.new("RGBA", (sticker.width + 24, sticker.height + 28), (0, 0, 0, 0))
    result.alpha_composite(tinted, (16, 20))
    result.alpha_composite(sticker, (4, 2))
    return result


def centered_text(
    draw: ImageDraw.ImageDraw,
    y: int,
    text: str,
    text_font: ImageFont.FreeTypeFont,
    fill: str,
    stroke_width: int = 0,
    stroke_fill: str | None = None,
) -> None:
    box = draw.textbbox((0, 0), text, font=text_font, stroke_width=stroke_width)
    width = box[2] - box[0]
    draw.text(
        ((CANVAS_SIZE - width) / 2, y),
        text,
        font=text_font,
        fill=fill,
        stroke_width=stroke_width,
        stroke_fill=stroke_fill,
    )


def draw_download_icon(draw: ImageDraw.ImageDraw, color: str) -> None:
    draw.line((56, 28, 56, 66), fill=color, width=8)
    draw.line((42, 52, 56, 68, 70, 52), fill=color, width=8, joint="curve")
    draw.rounded_rectangle((34, 74, 78, 83), radius=4, fill=color)


def draw_png_icon(draw: ImageDraw.ImageDraw, color: str) -> None:
    draw.rounded_rectangle((36, 22, 74, 86), radius=5, outline=color, width=6)
    draw.line((61, 22, 74, 36, 61, 36, 61, 22), fill=color, width=5)
    draw.line((44, 52, 66, 52), fill=color, width=5)
    draw.line((44, 64, 66, 64), fill=color, width=5)


def draw_pdf_icon(draw: ImageDraw.ImageDraw, color: str) -> None:
    draw.rounded_rectangle((34, 22, 70, 86), radius=5, outline=color, width=6)
    draw.line((57, 22, 70, 36, 57, 36, 57, 22), fill=color, width=5)
    draw.line((58, 70, 82, 46), fill=color, width=7)
    draw.polygon(((78, 43), (85, 50), (88, 38)), fill=color)


def make_badge(
    label_top: str,
    label_bottom: str,
    color: str,
    icon_kind: str,
    text_font: ImageFont.FreeTypeFont,
) -> Image.Image:
    badge = Image.new("RGBA", (300, 112), (0, 0, 0, 0))
    draw = ImageDraw.Draw(badge)
    draw.rounded_rectangle(
        (2, 2, 297, 109),
        radius=24,
        fill="#FFFDF7",
        outline="#E4C98F",
        width=3,
    )
    draw.ellipse((18, 12, 106, 100), fill=color)
    icon_layer = Image.new("RGBA", badge.size, (0, 0, 0, 0))
    icon_draw = ImageDraw.Draw(icon_layer)
    if icon_kind == "download":
        draw_download_icon(icon_draw, "#FFFFFF")
    elif icon_kind == "png":
        draw_png_icon(icon_draw, "#FFFFFF")
    else:
        draw_pdf_icon(icon_draw, "#FFFFFF")
    badge.alpha_composite(icon_layer)
    draw.text((122, 25), label_top, font=text_font, fill=INK)
    draw.text((122, 57), label_bottom, font=text_font, fill=INK)
    return badge


def build(args: argparse.Namespace) -> None:
    regular_font = Path(args.regular_font)
    bold_font = Path(args.bold_font)
    black_font = Path(args.black_font)

    background = Image.open(args.background).convert("RGB")
    background = background.resize((CANVAS_SIZE, CANVAS_SIZE), Image.Resampling.LANCZOS)
    canvas = background.convert("RGBA")

    title_panel = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    panel_draw = ImageDraw.Draw(title_panel)
    panel_draw.rounded_rectangle((218, 78, 806, 365), radius=48, fill=(255, 248, 233, 205))
    canvas.alpha_composite(title_panel)

    logo = fit(alpha_crop(Image.open(args.logo)), 290, 86)
    canvas.alpha_composite(logo, (28, 25))

    draw = ImageDraw.Draw(canvas)
    centered_text(draw, 88, args.title_top, font(black_font, 91), CORAL, 8, "#FFFDF7")
    centered_text(draw, 178, args.title_bottom, font(black_font, 68), NAVY, 6, "#FFFDF7")

    ribbon = (194, 270, 830, 332)
    draw.rounded_rectangle(ribbon, radius=20, fill=TEAL, outline="#FFFDF7", width=5)
    centered_text(draw, 281, args.subtitle, font(bold_font, 35), "#FFFFFF")

    count_box = (353, 342, 671, 390)
    draw.rounded_rectangle(count_box, radius=18, fill="#FFE4D8", outline=CORAL, width=3)
    centered_text(draw, 351, args.count_label, font(bold_font, 25), INK)

    sticker_ids = [int(value) for value in args.sticker_ids.split(",") if value.strip()]
    top_centers = [(97, 198), (927, 198)]
    top_ids = sticker_ids[:2]
    for sticker_id, center, angle in zip(top_ids, top_centers, (-9, 8)):
        sticker_path = Path(args.individual_dir) / f"sticker-{sticker_id:02d}.png"
        paste_center(canvas, sticker_with_shadow(sticker_path, 132, angle), center)

    rng = random.Random(202608)
    centers = [
        (106, 500), (304, 500), (510, 492), (714, 500), (915, 500),
        (112, 716), (300, 720), (500, 708), (700, 720), (905, 716),
    ]
    remaining_ids = sticker_ids[2:12]
    for sticker_id, base_center in zip(remaining_ids, centers):
        center = (base_center[0] + rng.randint(-10, 10), base_center[1] + rng.randint(-12, 12))
        angle = rng.uniform(-10, 10)
        size = rng.randint(158, 178)
        sticker_path = Path(args.individual_dir) / f"sticker-{sticker_id:02d}.png"
        paste_center(canvas, sticker_with_shadow(sticker_path, size, angle), center)

    badge_font = font(bold_font, 25)
    badges = [
        ("EASY", "DOWNLOAD", TEAL, "download", "easy-download.png"),
        ("PRINTABLE", "PNG", CORAL, "png", "printable-png.png"),
        ("EDITABLE", "PDF", GOLD, "pdf", "editable-pdf.png"),
    ]
    badge_dir = Path(args.badge_dir)
    badge_dir.mkdir(parents=True, exist_ok=True)
    for index, (top, bottom, color, icon_kind, filename) in enumerate(badges):
        badge = make_badge(top, bottom, color, icon_kind, badge_font)
        badge_path = badge_dir / filename
        if not badge_path.exists():
            badge.save(badge_path, format="PNG", dpi=(72, 72), compress_level=9)
        canvas.alpha_composite(badge, (30 + index * 332, 882))

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(output, format="PNG", dpi=(72, 72), compress_level=9)


def parser() -> argparse.ArgumentParser:
    project_root = Path(__file__).resolve().parent.parent
    release = project_root / "output/releases/japanese-summer-events/2026-08"
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--background",
        default=project_root / "branding/listing-backgrounds/japanese-summer-washi.png",
    )
    result.add_argument("--logo", default=project_root / "branding/makeyourmomentjp-logo-primary.png")
    result.add_argument("--individual-dir", default=release / "customer/individual")
    result.add_argument("--output", default=release / "marketing/japanese-summer-events-2026-08-eyecatch-1024.png")
    result.add_argument("--badge-dir", default=project_root / "branding/listing-badges")
    result.add_argument("--title-top", default="JAPANESE")
    result.add_argument("--title-bottom", default="SUMMER EVENTS")
    result.add_argument("--subtitle", default="AUGUST STICKER COLLECTION")
    result.add_argument("--count-label", default="35 DIGITAL STICKERS")
    result.add_argument("--sticker-ids", default="1,34,2,4,7,9,13,17,21,25,29,33")
    result.add_argument("--regular-font", default="/System/Library/Fonts/Supplemental/Arial.ttf")
    result.add_argument("--bold-font", default="/System/Library/Fonts/Supplemental/Arial Bold.ttf")
    result.add_argument("--black-font", default="/System/Library/Fonts/Supplemental/Arial Black.ttf")
    return result


if __name__ == "__main__":
    build(parser().parse_args())
