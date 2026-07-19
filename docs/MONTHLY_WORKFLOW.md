# 月次制作手順

## 1. テーマと月を作る

7月例のテーマディレクトリを複製する。

```text
output/releases/<theme-slug>/<YYYY-MM>/
```

`manifest.json`で次を確定する。

- テーマ和名・英名・slug
- 年月と月表示
- 28-31の日数
- 日数分の和名・ローマ字
- ランダムおまけと35番のコンセプト
- 個別PNGファイル名
- PNG、PDF、QA PDFの出力名

## 2. 個別素材を準備する

原則として1生成につき1シールとする。複数生成を使う場合は、隣画像との接触、
上下左右の欠け、白枠の接続を暗背景で確認し、分離できないものだけ単品再生成する。

校了した35枚だけを`customer/individual/`へ置く。クロマ原稿、グループ画像、
抽出候補、旧稿、透明化テストは移さない。

## 3. ビルドする

```sh
scripts/build.sh --manifest output/releases/<theme>/<year-month>/manifest.json
```

ビルドは同じmanifestから次を生成する。

1. ラスターデザイン層
2. 花名編集用PDF
3. PDF由来の透過PNG
4. QA用alignment PDF

一時ラスターデザイン層は保存しない。

別フォントを使う場合：

```sh
scripts/build.sh \
  --manifest output/releases/<theme>/<year-month>/manifest.json \
  --editable-font /path/to/japanese-font.ttf
```

## 4. 自動検査する

```sh
scripts/verify.sh --manifest output/releases/<theme>/<year-month>/manifest.json
```

35枚、PNG、PDFページ寸法、透過、300dpi、花名抽出、埋め込みフォント、
PDF/PNG一致を検査する。

## 5. 目視検査する

- customer PNGを暗背景と白背景で原寸確認
- alignment PDFで7本の中心線と全ラベル中央を確認
- 全個別PNGの上下左右、白枠、異物、マゼンタを確認
- PDF編集ソフトで花名を1件変更し、保存・再表示できることを手動確認

## 6. 販売データを取り出す

購入者向けは`customer/`のみ。`qa/`、manifest、生成スクリプトは販売ZIPへ入れない。
個別35枚を商品に含めるかは商品仕様で決める。7月例では分割データとして含めている。

## 7. 販売用アイキャッチを作る

`scripts/build_listing_eyecatch.py`で`marketing/`へ1024×1024px・72dpi・
アルファなしPNGを生成する。ロゴ、テーマ英名、月名、代表シール、共通の
`EASY DOWNLOAD`、`PRINTABLE PNG`、`EDITABLE PDF`マークを含める。

アイキャッチは販売ページ用であり、購入者向け`customer/`へ入れない。
共通アセット、実行例、QA条件は`docs/LISTING_EYECATCH_SPEC.md`を参照する。
