# Codex 月次ステッカー制作テンプレート

このディレクトリだけで、月次ステッカーの個別素材管理、7×5組版、花名編集用PDF、
透過PNG、alignment-check PDFの生成と検査を行えます。

ショップロゴ：

- 横長版：`branding/makeyourmomentjp-logo-primary.png`
- Web正方形版（1024×1024px・72dpi・透明PNG）：`branding/makeyourmomentjp-logo-square-1024.png`

## 最短の使い方

1. `output/releases/japanese-summer-flowers/2026-07/`を新しいテーマ・月名で複製する。
2. `manifest.json`のテーマ、月、日数、花名、ファイル名を変更する。
3. `customer/individual/`を、校了済みの独立透過PNG 35枚へ置き換える。
4. 次を実行する。

```sh
scripts/build.sh --manifest output/releases/<theme>/<year-month>/manifest.json
scripts/verify.sh --manifest output/releases/<theme>/<year-month>/manifest.json
```

5. `customer/`のPNG・PDFと、`qa/`のalignment PDFを原寸確認する。
6. 販売ページ用に`marketing/`へ1024px正方形のアイキャッチ画像を生成する。

## 7月版の完成例

```text
output/releases/japanese-summer-flowers/2026-07/
├── manifest.json
├── customer/
│   ├── japanese-summer-flowers-2026-07-3072x2048-300dpi-transparent.png
│   ├── japanese-summer-flowers-2026-07-editable-flower-labels.pdf
│   ├── README.txt
│   └── individual/
│       └── sticker-01.png ... sticker-35.png
└── qa/
    ├── japanese-summer-flowers-2026-07-alignment-check.pdf
    └── contact-sheet-31-clean.png
```

`customer/`が購入者向け、`qa/`が制作確認専用です。販売時は`qa/`を含めません。

## 生成順

1. 個別PNGから絵柄、白紙ラベル枠、表題、コンセプトをラスターレイヤーへ組版
2. 日数分の`和名 / Romaji`だけを編集可能PDFテキストとして配置
3. PDFを出力
4. 同じPDFを3072×2048px・300dpi・透過RGBAへ完全ラスタライズしてPNG出力

PDFとPNGで座標や文字列を別管理しないため、位置ずれを防げます。

詳細は[制作仕様](docs/PRODUCTION_SPEC.md)、[月次手順](docs/MONTHLY_WORKFLOW.md)、
[PDFダウンロード仕様](docs/DOWNLOAD_PACKAGE_SPEC.md)、[QA](docs/QA_CHECKLIST.md)、
[販売用アイキャッチ仕様](docs/LISTING_EYECATCH_SPEC.md)を参照してください。
