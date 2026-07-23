# 販売用シート画像仕様（商品画像 rank 2）

月次ステッカー商品の商品ページで、アイキャッチ（rank 1）に続く2枚目として使う
「シート画像」の共通仕様。購入者向けダウンロードデータではないため、`customer/`
には置かない。

## 背景と寸法の方針

納品シートPNG（`customer/`）は300dpiの**透過**RGBA。Etsyの商品写真は透過を持て
ないJPEGなので、単色背景に平坦化して書き出す。背景は**near-white（アイボリー）**を
既定とし、清潔なカタログ写真として見せる。シート上部の月タイトルは淡色寄りのため
明色背景では控えめになるが、シート本体（35枚＋ラベル）の視認性を優先した割り切り。
純白にしたい場合は `--background '#ffffff'`、濃色カードにしたい場合は任意のhexを渡す。

納品シートは商品写真に必要な解像度よりはるかに大きいので、**長辺1200px**へ縮小する。

## 固定仕様

| 項目 | 値 |
|---|---|
| ピクセル寸法 | 長辺1200pxへ縮小（例: 1200 × 800 px） |
| 解像度 | 72 dpi |
| 形式 | JPEG（progressive / quality 90） |
| カラーモード | RGB |
| アルファチャンネル | なし |
| 背景色 | `#f5f2ec`（near-white アイボリー・既定） |
| 保存先 | `output/releases/<theme>/<year-month>/marketing/` |
| ファイル名 | `<theme>-<year-month>-photo-sheet.jpg` |

ファイル名に `photo-sheet` を含めること。`listing.py upload` は
`marketing/*eyecatch*.png` を rank 1、`marketing/*photo-sheet*.jpg` を rank 2 として
拾う（`listings/tools/listing.py` の `collect_assets`）。名前が違うと拾われない。

## 生成コマンド

```sh
python3 scripts/build_photo_sheet.py \
  --input  output/releases/<theme>/<year-month>/customer/<theme>-<year-month>-3072x2048-300dpi-transparent.png \
  --output output/releases/<theme>/<year-month>/marketing/<theme>-<year-month>-photo-sheet.jpg
```

背景色は `--background '#RRGGBB'`（既定 `#f5f2ec`）、長辺は `--long-edge`（既定 1200）で
変更できる。

既存リリースの例:

```sh
# japanese-summer-wagashi 2026-08
python3 scripts/build_photo_sheet.py \
  --input  output/releases/japanese-summer-wagashi/2026-08/customer/japanese-summer-wagashi-2026-08-3072x2048-300dpi-transparent.png \
  --output output/releases/japanese-summer-wagashi/2026-08/marketing/japanese-summer-wagashi-2026-08-photo-sheet.jpg

# japanese-summer-events 2026-08
python3 scripts/build_photo_sheet.py \
  --input  output/releases/japanese-summer-events/2026-08/customer/japanese-summer-events-2026-08-3072x2048-300dpi-transparent.png \
  --output output/releases/japanese-summer-events/2026-08/marketing/japanese-summer-events-2026-08-photo-sheet.jpg

# japanese-summer-flowers 2026-07
python3 scripts/build_photo_sheet.py \
  --input  output/releases/japanese-summer-flowers/2026-07/customer/japanese-summer-flowers-2026-07-3072x2048-300dpi-transparent.png \
  --output output/releases/japanese-summer-flowers/2026-07/marketing/japanese-summer-flowers-2026-07-photo-sheet.jpg

# japanese-landmarks 2026-08
python3 scripts/build_photo_sheet.py \
  --input  output/releases/japanese-landmarks/2026-08/customer/japanese-landmarks-2026-08-3072x2048-300dpi-transparent.png \
  --output output/releases/japanese-landmarks/2026-08/marketing/japanese-landmarks-2026-08-photo-sheet.jpg
```

## アップロード

```sh
# 新規出品時（推奨）: eyecatch と photo-sheet を marketing/ に揃えてから upload。
# rank 1,2 の画像と customer/ の納品PNG・PDFがまとめて上がる。
python3 listings/tools/listing.py upload --release <theme>/<year-month> --apply

# 後追いでシート画像だけ足す場合: ダウンロードファイルは添付済みなので --skip-files。
python3 listings/tools/listing.py upload --release <theme>/<year-month> --skip-files --apply
```

`upload_listing_image` は `overwrite=true` で送るため、rank 1 の eyecatch を再送しても
重複せず同じ内容で置き換わる。`--skip-files` を付ければ `customer/` のダウンロード
ファイルは触らないので、二重添付にならない。送信後に画像・ファイル件数を読み戻して
照合する。

## QA

- 長辺が1200pxである（例: 1200 × 800 px）。
- 72 dpiメタデータが設定されている。
- JPEGがRGBで、アルファチャンネルを持たない。
- 35枚のシールと和名/ローマ字ラベルがすべて読める。
- 透過部分が背景色（near-white）で埋まっており、黒く潰れていない。
- `marketing/` にあり、`customer/` へ混入していない。
- Etsyの読み戻しで rank 2 に入っている（rank 1 はアイキャッチ）。

確認例:

```sh
sips -g pixelWidth -g pixelHeight -g dpiWidth -g hasAlpha -g format \
  output/releases/<theme>/<year-month>/marketing/<theme>-<year-month>-photo-sheet.jpg
```
