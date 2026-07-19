#!/usr/bin/env python3
"""Build customer PNG/PDF and a QA alignment PDF from one manifest.

The raster design layer contains artwork, title, label frames, bonuses, and the
concept seal. Only day-sticker flower names are added as editable PDF text.
The customer PNG is rendered from that exact PDF, preventing layout drift.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as pdf_canvas


@dataclass(frozen=True)
class BuildPaths:
    individual_dir: Path
    customer_dir: Path
    qa_dir: Path
    png: Path
    pdf: Path
    alignment_pdf: Path


def read_manifest(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        manifest = json.load(handle)
    if manifest.get("schema_version") != 1:
        raise ValueError("manifest schema_version must be 1")
    return manifest


def resolve_build_paths(project_root: Path, manifest: dict[str, Any]) -> BuildPaths:
    artifacts = manifest["artifacts"]
    individual_dir = project_root / artifacts["individual_directory"]
    customer_dir = project_root / artifacts["customer_directory"]
    qa_dir = project_root / artifacts["qa_directory"]
    return BuildPaths(
        individual_dir=individual_dir,
        customer_dir=customer_dir,
        qa_dir=qa_dir,
        png=customer_dir / artifacts["png_filename"],
        pdf=customer_dir / artifacts["pdf_filename"],
        alignment_pdf=qa_dir / artifacts["alignment_pdf_filename"],
    )


def validate_manifest(manifest: dict[str, Any]) -> None:
    canvas = manifest["canvas"]
    layout = manifest["layout"]
    counts = manifest["counts"]
    day_stickers = manifest["day_stickers"]
    bonuses = manifest["bonuses"]

    if (canvas["width_px"], canvas["height_px"], canvas["dpi"]) != (
        3072,
        2048,
        300,
    ):
        raise ValueError("canvas must be 3072x2048 px at 300 dpi")
    if (layout["columns"], layout["rows"]) != (7, 5):
        raise ValueError("layout must be 7 columns x 5 rows")
    if len(layout["column_centers_px"]) != 7 or len(layout["row_centers_px"]) != 5:
        raise ValueError("layout center arrays must contain 7 columns and 5 rows")
    if counts["calendar_days"] != len(day_stickers):
        raise ValueError("calendar_days must equal day_stickers length")
    if counts["day_stickers"] != counts["calendar_days"]:
        raise ValueError("day_stickers count must equal calendar_days")
    if len(day_stickers) + len(bonuses) != 35:
        raise ValueError("day stickers plus bonuses must fill all 35 slots")
    if counts["total_slots"] != 35:
        raise ValueError("total_slots must be 35")
    if sum(item["kind"] == "concept" for item in bonuses) != 1:
        raise ValueError("exactly one concept seal is required")
    if bonuses[-1]["slot"] != 35 or bonuses[-1]["kind"] != "concept":
        raise ValueError("slot 35 must be the concept seal")

    all_slots = [item["slot"] for item in day_stickers + bonuses]
    if sorted(all_slots) != list(range(1, 36)):
        raise ValueError("sticker slots must be consecutive from 1 to 35")


def system_font_candidates(kind: str) -> list[tuple[Path, int]]:
    user_root = Path.home()
    if kind == "design":
        return [
            (Path("/System/Library/Fonts/Hiragino Sans GB.ttc"), 0),
            (user_root / "Library/Fonts/YuGothR.ttc", 0),
            (user_root / "Library/Fonts/ipaexg.ttf", 0),
            (Path("/Library/Fonts/Arial Unicode.ttf"), 0),
        ]
    return [
        (user_root / "Library/Fonts/YuGothR.ttc", 0),
        (user_root / "Library/Fonts/YuGothM.ttc", 0),
        (user_root / "Library/Fonts/ipaexg.ttf", 0),
        (Path("/Library/Fonts/Arial Unicode.ttf"), 0),
        (Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"), 0),
    ]


def choose_design_font(
    requested: Path | None, font_index: int, size_px: int
) -> tuple[ImageFont.FreeTypeFont, Path, int]:
    candidates = [(requested, font_index)] if requested else system_font_candidates("design")
    errors: list[str] = []
    for path, index in candidates:
        if path is None or not path.exists():
            continue
        try:
            return ImageFont.truetype(str(path), size_px, index=index), path, index
        except Exception as error:
            errors.append(f"{path}: {error}")
    raise RuntimeError("raster design font unavailable\n" + "\n".join(errors))


def register_editable_font(
    requested: Path | None, font_index: int
) -> tuple[str, Path, int]:
    candidates = [(requested, font_index)] if requested else system_font_candidates("editable")
    errors: list[str] = []
    for path, index in candidates:
        if path is None or not path.exists():
            continue
        try:
            font_name = "EditableDayLabels"
            pdfmetrics.registerFont(
                TTFont(font_name, str(path), subfontIndex=index)
            )
            return font_name, path, index
        except Exception as error:
            errors.append(f"{path}: {error}")
    raise RuntimeError("editable PDF font unavailable\n" + "\n".join(errors))


def hex_rgba(value: str, alpha: int = 255) -> tuple[int, int, int, int]:
    value = value.lstrip("#")
    if len(value) != 6:
        raise ValueError(f"expected #RRGGBB color, got {value}")
    return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4)) + (alpha,)


def resize_to_fit(image: Image.Image, max_size: tuple[int, int]) -> Image.Image:
    scale = min(1.0, max_size[0] / image.width, max_size[1] / image.height)
    size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    if size == image.size:
        return image.copy()
    return image.resize(size, Image.Resampling.LANCZOS)


def paste_centered(canvas: Image.Image, image: Image.Image, center: tuple[int, int]) -> None:
    x = round(center[0] - image.width / 2)
    y = round(center[1] - image.height / 2)
    canvas.alpha_composite(image, (x, y))


def draw_label_plate(
    draw: ImageDraw.ImageDraw,
    center: tuple[int, int],
    manifest: dict[str, Any],
) -> None:
    layout = manifest["layout"]
    typography = manifest["typography"]
    width, height = layout["label_size_px"]
    x0 = round(center[0] - width / 2)
    y0 = round(center[1] - height / 2)
    x1 = x0 + width - 1
    y1 = y0 + height - 1
    draw.rounded_rectangle(
        (x0, y0, x1, y1),
        radius=18,
        fill=hex_rgba(typography["label_outer_color"]),
    )
    draw.rounded_rectangle(
        (x0 + 6, y0 + 5, x1 - 6, y1 - 5),
        radius=13,
        fill=hex_rgba(typography["label_inner_color"]),
        outline=hex_rgba(typography["label_stroke_color"]),
        width=typography["label_stroke_px"],
    )


def line_metrics(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    char_space_px: float,
) -> tuple[float, int, int]:
    widths = [draw.textlength(character, font=font) for character in text]
    width = sum(widths) + max(0, len(text) - 1) * char_space_px
    bbox = draw.textbbox((0, 0), text, font=font)
    return width, bbox[1], bbox[3]


def draw_spaced_line(
    draw: ImageDraw.ImageDraw,
    center_x: float,
    top_y: float,
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int, int],
    char_space_px: float,
) -> int:
    total_width, bbox_top, bbox_bottom = line_metrics(draw, text, font, char_space_px)
    x = center_x - total_width / 2
    baseline_y = top_y - bbox_top
    for character in text:
        draw.text((x, baseline_y), character, font=font, fill=fill)
        x += draw.textlength(character, font=font) + char_space_px
    return bbox_bottom - bbox_top


def compose_raster_design(
    manifest: dict[str, Any],
    paths: BuildPaths,
    design_font_path: Path | None,
    design_font_index: int,
) -> tuple[Image.Image, Path, int]:
    canvas_spec = manifest["canvas"]
    layout = manifest["layout"]
    typography = manifest["typography"]
    columns = layout["column_centers_px"]
    rows = layout["row_centers_px"]

    canvas = Image.new(
        "RGBA", (canvas_spec["width_px"], canvas_spec["height_px"]), (0, 0, 1, 0)
    )
    draw = ImageDraw.Draw(canvas)

    for item in manifest["day_stickers"]:
        slot = item["slot"]
        row = (slot - 1) // 7
        column = (slot - 1) % 7
        source_path = paths.individual_dir / item["source"]
        with Image.open(source_path) as source:
            art = resize_to_fit(source.convert("RGBA"), tuple(layout["day_art_max_px"]))
        paste_centered(
            canvas,
            art,
            (columns[column], rows[row] + layout["day_art_offset_y_px"]),
        )
        draw_label_plate(
            draw,
            (columns[column], rows[row] + layout["label_offset_y_px"]),
            manifest,
        )

    for item in manifest["bonuses"]:
        slot = item["slot"]
        row = (slot - 1) // 7
        column = (slot - 1) % 7
        source_path = paths.individual_dir / item["source"]
        with Image.open(source_path) as source:
            art = resize_to_fit(source.convert("RGBA"), tuple(layout["bonus_art_max_px"]))
        paste_centered(canvas, art, (columns[column], rows[row]))

    title_font, chosen_design_font, chosen_design_index = choose_design_font(
        design_font_path, design_font_index, typography["title_font_size_px"]
    )
    draw_spaced_line(
        draw,
        canvas.width / 2,
        typography["title_top_px"],
        manifest["theme"]["title_line"],
        title_font,
        hex_rgba(typography["label_text_color"]),
        typography["title_char_space_px"],
    )

    concept_font, _, _ = choose_design_font(
        chosen_design_font, chosen_design_index, typography["concept_font_size_px"]
    )
    concept_lines = manifest["theme"]["concept_lines"]
    line_heights = [
        line_metrics(
            draw,
            line,
            concept_font,
            typography["concept_char_space_px"],
        )[2]
        - line_metrics(
            draw,
            line,
            concept_font,
            typography["concept_char_space_px"],
        )[1]
        for line in concept_lines
    ]
    total_height = sum(line_heights) + typography["concept_line_spacing_px"] * (
        len(concept_lines) - 1
    )
    concept_center_x = columns[-1] + layout["concept_text_offset_px"][0]
    concept_center_y = rows[-1] + layout["concept_text_offset_px"][1]
    line_top = concept_center_y - total_height / 2
    for line, line_height in zip(concept_lines, line_heights):
        draw_spaced_line(
            draw,
            concept_center_x,
            line_top,
            line,
            concept_font,
            hex_rgba(typography["label_text_color"]),
            typography["concept_char_space_px"],
        )
        line_top += line_height + typography["concept_line_spacing_px"]

    return canvas, chosen_design_font, chosen_design_index


def draw_editable_label(
    pdf: pdf_canvas.Canvas,
    text: str,
    center_x_px: int,
    center_y_px: int,
    manifest: dict[str, Any],
    font_name: str,
) -> None:
    canvas_spec = manifest["canvas"]
    typography = manifest["typography"]
    px_to_pt = 72.0 / canvas_spec["dpi"]
    font_size = typography["label_font_size_px"] * px_to_pt
    char_space = typography["label_char_space_px"] * px_to_pt
    width = pdfmetrics.stringWidth(text, font_name, font_size)
    width += max(0, len(text) - 1) * char_space
    center_x = center_x_px * px_to_pt
    center_y = (canvas_spec["height_px"] - center_y_px) * px_to_pt
    ascent, descent = pdfmetrics.getAscentDescent(font_name, font_size)
    baseline = center_y - (ascent + descent) / 2

    text_object = pdf.beginText()
    text_object.setFont(font_name, font_size)
    text_object.setFillColor(HexColor(typography["label_text_color"]))
    text_object.setCharSpace(char_space)
    text_object.setTextOrigin(center_x - width / 2, baseline)
    text_object.textOut(text)
    pdf.drawText(text_object)


def draw_alignment_guides(pdf: pdf_canvas.Canvas, manifest: dict[str, Any]) -> None:
    canvas_spec = manifest["canvas"]
    layout = manifest["layout"]
    px_to_pt = 72.0 / canvas_spec["dpi"]
    page_width = canvas_spec["width_px"] * px_to_pt
    page_height = canvas_spec["height_px"] * px_to_pt

    pdf.saveState()
    pdf.setLineWidth(3 * px_to_pt)
    pdf.setStrokeColor(HexColor("#FF2A1A"))
    for center_x in layout["column_centers_px"]:
        x = center_x * px_to_pt
        pdf.line(x, 0, x, page_height)
    pdf.setStrokeColor(HexColor("#00A6D6"))
    for center_y in layout["row_centers_px"]:
        y = (canvas_spec["height_px"] - center_y) * px_to_pt
        pdf.line(0, y, page_width, y)
    pdf.setStrokeColor(HexColor("#D206D0"))
    pdf.setLineWidth(2 * px_to_pt)
    pdf.setDash(7 * px_to_pt, 5 * px_to_pt)
    label_width, label_height = layout["label_size_px"]
    for item in manifest["day_stickers"]:
        slot = item["slot"]
        row = (slot - 1) // 7
        column = (slot - 1) % 7
        center_x = layout["column_centers_px"][column]
        center_y = layout["row_centers_px"][row] + layout["label_offset_y_px"]
        left = (center_x - label_width / 2) * px_to_pt
        bottom = (
            canvas_spec["height_px"] - center_y - label_height / 2
        ) * px_to_pt
        pdf.rect(
            left,
            bottom,
            label_width * px_to_pt,
            label_height * px_to_pt,
            stroke=1,
            fill=0,
        )
    pdf.restoreState()


def build_pdf(
    output_path: Path,
    raster_design: Image.Image,
    manifest: dict[str, Any],
    editable_font_name: str,
    alignment: bool,
) -> None:
    canvas_spec = manifest["canvas"]
    layout = manifest["layout"]
    px_to_pt = 72.0 / canvas_spec["dpi"]
    page_size = (
        canvas_spec["width_px"] * px_to_pt,
        canvas_spec["height_px"] * px_to_pt,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pdf = pdf_canvas.Canvas(
        str(output_path),
        pagesize=page_size,
        pageCompression=1,
        pdfVersion=(1, 4),
    )
    theme = manifest["theme"]
    pdf.setTitle(f"{theme['name_en']} - {theme['month_label_ja']}")
    pdf.setSubject("Printable sticker sheet; only day labels are editable text")
    pdf.setCreator("Sticker Production Template")
    pdf.drawImage(
        ImageReader(raster_design),
        0,
        0,
        width=page_size[0],
        height=page_size[1],
        mask="auto",
    )
    for item in manifest["day_stickers"]:
        slot = item["slot"]
        row = (slot - 1) // 7
        column = (slot - 1) % 7
        label = f"{item['japanese_name']} / {item['romaji']}"
        draw_editable_label(
            pdf,
            label,
            layout["column_centers_px"][column],
            layout["row_centers_px"][row] + layout["label_offset_y_px"],
            manifest,
            editable_font_name,
        )
    if alignment:
        draw_alignment_guides(pdf, manifest)
    pdf.showPage()
    pdf.save()


def rasterize_pdf(pdf_path: Path, png_path: Path, manifest: dict[str, Any]) -> None:
    pdftocairo = shutil.which("pdftocairo")
    if not pdftocairo:
        raise RuntimeError("pdftocairo is required to create the delivery PNG")
    canvas_spec = manifest["canvas"]
    with tempfile.TemporaryDirectory(prefix="sticker-build-") as temporary_directory:
        prefix = Path(temporary_directory) / "sheet"
        subprocess.run(
            [
                pdftocairo,
                "-png",
                "-transp",
                "-singlefile",
                "-scale-to-x",
                str(canvas_spec["width_px"]),
                "-scale-to-y",
                str(canvas_spec["height_px"]),
                str(pdf_path),
                str(prefix),
            ],
            check=True,
        )
        rendered_path = prefix.with_suffix(".png")
        with Image.open(rendered_path) as rendered:
            if rendered.size != (canvas_spec["width_px"], canvas_spec["height_px"]):
                raise ValueError(f"unexpected rasterized size: {rendered.size}")
            rendered.convert("RGBA").save(
                png_path,
                format="PNG",
                dpi=(canvas_spec["dpi"], canvas_spec["dpi"]),
                compress_level=9,
            )


def build_parser(project_root: Path) -> argparse.ArgumentParser:
    example_manifest = (
        project_root
        / "output/releases/japanese-summer-flowers/2026-07/manifest.json"
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=example_manifest)
    parser.add_argument("--design-font", type=Path)
    parser.add_argument("--design-font-index", type=int, default=0)
    parser.add_argument("--editable-font", type=Path)
    parser.add_argument("--editable-font-index", type=int)
    return parser


def main() -> int:
    project_root = Path(__file__).resolve().parent.parent
    args = build_parser(project_root).parse_args()
    manifest_path = args.manifest.resolve()
    manifest = read_manifest(manifest_path)
    validate_manifest(manifest)
    paths = resolve_build_paths(project_root, manifest)
    paths.customer_dir.mkdir(parents=True, exist_ok=True)
    paths.qa_dir.mkdir(parents=True, exist_ok=True)

    configured_design_font = manifest["typography"].get("design_font_path")
    design_font_path = args.design_font or (
        project_root / configured_design_font if configured_design_font else None
    )
    configured_editable_font = manifest["typography"].get("editable_font_path")
    editable_font_path = args.editable_font or (
        project_root / configured_editable_font if configured_editable_font else None
    )
    editable_font_index = (
        args.editable_font_index
        if args.editable_font_index is not None
        else manifest["typography"].get("editable_font_index", 0)
    )

    raster_design, chosen_design_font, chosen_design_index = compose_raster_design(
        manifest,
        paths,
        design_font_path,
        args.design_font_index,
    )
    editable_font_name, chosen_editable_font, chosen_editable_index = (
        register_editable_font(editable_font_path, editable_font_index)
    )
    build_pdf(paths.pdf, raster_design, manifest, editable_font_name, alignment=False)
    build_pdf(
        paths.alignment_pdf,
        raster_design,
        manifest,
        editable_font_name,
        alignment=True,
    )
    rasterize_pdf(paths.pdf, paths.png, manifest)

    print(f"manifest={manifest_path}")
    print(f"design_font={chosen_design_font} subfont={chosen_design_index}")
    print(f"editable_font={chosen_editable_font} subfont={chosen_editable_index}")
    print(f"customer_png={paths.png}")
    print(f"customer_pdf={paths.pdf}")
    print(f"alignment_pdf={paths.alignment_pdf}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
