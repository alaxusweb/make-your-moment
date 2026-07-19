# 販売用アイキャッチ画像仕様

月次ステッカー商品の一覧・商品ページで使う正方形アイキャッチ画像の共通仕様。
購入者向けダウンロードデータではないため、`customer/`には置かない。

## 固定仕様

| 項目 | 値 |
|---|---|
| サイズ | 1024 × 1024 px |
| 解像度 | 72 dpi |
| 形式 | PNG |
| カラーモード | RGB |
| アルファチャンネル | なし |
| 保存先 | `output/releases/<theme>/<year-month>/marketing/` |
| ファイル名 | `<theme>-<year-month>-eyecatch-1024.png` |

## 共通レイアウト

1. 左上に`branding/makeyourmomentjp-logo-primary.png`を配置する。
2. 中央上部にテーマ英名を大きく2行で配置する。
3. リボン内に`<MONTH> STICKER COLLECTION`を配置する。
4. 総数を`35 DIGITAL STICKERS`として表示する。
5. `customer/individual/`から代表的な12枚前後を選び、角度と位置を少しずつ
   変えてランダム感のある2段構成にする。全35枚を並べる必要はない。
6. 下端に次の3つの共通マークを順番固定で配置する。
   - `EASY DOWNLOAD`
   - `PRINTABLE PNG`
   - `EDITABLE PDF`

ロゴ、シール、タイトル、マークの文字は画像生成モデルに描かせず、実素材と
システムフォントから決定的に組版する。画像生成を使う場合は、無文字の背景素材
だけに限定する。

## 共通アセット

```text
branding/
├── makeyourmomentjp-logo-primary.png
├── listing-backgrounds/
│   └── japanese-summer-washi.png
└── listing-badges/
    ├── easy-download.png
    ├── printable-png.png
    └── editable-pdf.png
```

共通背景は淡い和紙、金色の旭光、青海波、祭りの紙吹雪で構成し、文字、ロゴ、
シール、商品モックアップを含めない。3つのバッジは月やテーマを問わず同じものを
再利用する。

## 生成コマンド

共通スクリプト：

```text
scripts/build_listing_eyecatch.py
```

7月版：

```sh
python3 scripts/build_listing_eyecatch.py \
  --individual-dir output/releases/japanese-summer-flowers/2026-07/customer/individual \
  --output output/releases/japanese-summer-flowers/2026-07/marketing/japanese-summer-flowers-2026-07-eyecatch-1024.png \
  --title-bottom "SUMMER FLOWERS" \
  --subtitle "JULY STICKER COLLECTION" \
  --sticker-ids "34,32,1,2,3,4,6,9,13,15,22,29"
```

8月版：

```sh
python3 scripts/build_listing_eyecatch.py \
  --individual-dir output/releases/japanese-summer-events/2026-08/customer/individual \
  --output output/releases/japanese-summer-events/2026-08/marketing/japanese-summer-events-2026-08-eyecatch-1024.png \
  --title-bottom "SUMMER EVENTS" \
  --subtitle "AUGUST STICKER COLLECTION" \
  --sticker-ids "1,34,2,4,7,9,13,17,21,25,29,33"
```

CodexのバンドルPythonを使う場合は、`python3`をワークスペース依存環境の
Python実行ファイルへ置き換える。

## QA

- 1024 × 1024 pxである。
- 72 dpiメタデータが設定されている。
- PNGがRGBで、アルファチャンネルを持たない。
- ロゴと英字に誤字、欠け、変形がない。
- シールがタイトル、ロゴ、共通マークへ重ならない。
- 選んだシールに欠け、異物、透かし、マゼンタ残りがない。
- 3つの共通マークが同じ順序・表記・配色で表示される。
- `marketing/`にあり、`customer/`へ混入していない。

確認例：

```sh
sips -g pixelWidth -g pixelHeight -g dpiWidth -g dpiHeight -g hasAlpha \
  output/releases/<theme>/<year-month>/marketing/<theme>-<year-month>-eyecatch-1024.png
```
