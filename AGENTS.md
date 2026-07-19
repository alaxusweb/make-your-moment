# Monthly sticker production contract

This repository is a reusable Codex project for printable monthly sticker
sheets. Read these files before changing a theme or month:

1. `docs/PRODUCTION_SPEC.md`
2. `docs/MONTHLY_WORKFLOW.md`
3. `docs/DOWNLOAD_PACKAGE_SPEC.md`
4. `docs/QA_CHECKLIST.md`
5. The target `output/releases/<theme>/<year-month>/manifest.json`

## Non-negotiable rules

- Write `manifest.json` before generating any artwork. The manifest fixes the
  theme, the day labels, the bonus subjects, and every `sticker-NN.png`
  filename; artwork is then generated to fill those named slots. Never generate
  images first and back-fill a manifest to match whatever came out. Slot 35 in
  particular must be drawn knowing it is the concept seal, because it needs
  clear space for the concept text.
- Use a 3072 x 2048 px, 300 dpi, sRGB RGBA canvas with a transparent background.
- Use a 7 x 5 grid with 35 positions and at least 24 px cutting clearance.
- Fill the month day count first (28-31). Fill the remaining positions with
  theme-related bonuses; position 35 is always the theme/month concept seal.
- Keep every clean sticker as one independent transparent PNG. Never compose a
  final sheet directly from a crowded generation or a low-resolution upscale.
- Day stickers use `和名 / Romaji`. Bonuses have no labels.
- Build PDF and PNG from the same manifest and coordinates. The PDF is created
  first; the delivery PNG is the exact 300 dpi rasterization of that PDF.
- Only day-sticker labels are editable PDF text. Artwork, title, label frames,
  bonuses, and concept text are one fixed raster design layer.
- A locally installed system font is acceptable for editable labels. Never copy
  an operating-system font file into the customer download.
- The alignment PDF is QA-only. Never place it in `customer/`.
- Do not add chroma sources, group redraws, extraction tests, old grids, or
  other intermediate files to this template or customer output.
- Use original, non-branded artwork. Reject copyrighted characters, logos,
  trademarks, watermarks, and copied commercial sticker designs.

## Required completion gate

Run both commands and do not report completion until both succeed:

```sh
scripts/build.sh --manifest output/releases/<theme>/<year-month>/manifest.json
scripts/verify.sh --manifest output/releases/<theme>/<year-month>/manifest.json
```

Then visually inspect the customer PNG and the QA alignment PDF at full size.
