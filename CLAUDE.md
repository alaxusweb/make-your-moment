# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## このリポジトリの性質

アプリではなく、**印刷用月次ステッカーシートのダウンロード販売データを決定論的に生成する Python パイプライン**。
1テーマ×1ヶ月が1リリース単位で、すべての作業は `output/releases/<theme>/<year-month>/` に閉じる。

`AGENTS.md` にこのプロジェクトの制作契約（non-negotiable rules と完了ゲート）が書かれている。
テーマや月を変更する作業の前に必ず読むこと。仕様の詳細は `docs/` に分割されている。

## コマンド

作業単位は常に「1つの manifest」。`--manifest` を省略すると 7月版がデフォルトになるため、必ず明示する。

```sh
# ビルド（ラスター層 → PDF → PNG → QA用alignment PDF）
~/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  scripts/build.py --manifest output/releases/<theme>/<year-month>/manifest.json

# 検査（＝このリポジトリのテストスイート）
scripts/verify.sh --manifest output/releases/<theme>/<year-month>/manifest.json

# 販売ページ用アイキャッチ（customer/ ではなく marketing/ へ出力）
python3 scripts/build_listing_eyecatch.py \
  --individual-dir output/releases/<theme>/<year-month>/customer/individual \
  --output output/releases/<theme>/<year-month>/marketing/<theme>-<year-month>-eyecatch-1024.png \
  --title-bottom "SUMMER EVENTS" --subtitle "AUGUST STICKER COLLECTION" \
  --sticker-ids "1,34,2,4,7,9,13,17,21,25,29,33"
```

### 実行環境の落とし穴

- **`scripts/build.sh` はこのチェックアウト位置では動かない。** ラッパーは
  `user_root="${project_root%%/.codex/*}"` でプロジェクトが `.codex/` 配下にある前提で
  bundled Python を探すため、Dropbox 直下では存在しないパスを見て「Pillowと
  ReportLabを利用できるPythonが見つかりません」で終了する。上記のとおり
  `scripts/build.py` を bundled Python で直接呼ぶ。
- system `python3` には **reportlab が入っていない**（PIL と pypdf はある）。
  そのため `verify.sh` は system python3 で通るが、build 側は bundled Python が必要。
- `pdftocairo`（poppler）が build と verify の両方で必須。`/opt/homebrew/bin/pdftocairo` に存在。
- `build_listing_eyecatch.py` には実行権限がないので `python3` 経由で呼ぶ。

### 再ビルド時の注意

出力が内容的に同一でも PDF はタイムスタンプでバイト差分が出る。検証目的で
ビルドしただけなら `git checkout -- output/releases/<theme>/<year-month>/` で戻すこと。
PNG は決定論的なので差分が出ない。

## アーキテクチャ

### manifest.json が単一の真実

`output/releases/<theme>/<year-month>/manifest.json` にテーマ文言、キャンバス、
グリッド座標、タイポグラフィ、枚数、入出力ファイル名、35枠すべての素材割り当てが入る。
build も verify も**この1ファイルだけ**から動く。座標や文言をスクリプト側にハードコードしない。
新規月は `templates/monthly-manifest.json` か既存月の複製から作る。

### PDF → PNG の一方向生成（最重要）

`scripts/build.py` の生成順は固定：

1. `compose_raster_design()` — 個別PNG・表題・白紙ラベル枠・おまけ・コンセプト文字を
   1枚の RGBA ラスター層に合成（この中間ファイルは保存しない）
2. `build_pdf()` — そのラスター層を全面に敷き、**日付シールの `和名 / Romaji` だけ**を
   PDF実テキストで重ねる
3. `rasterize_pdf()` — `pdftocairo -transp` で同じ PDF を 3072×2048px へ完全ラスタライズし納品PNGにする

PNG と PDF を別々に組版してはいけない。`verify.py` の `compare_pdf_render_to_png()` が
1ピクセルの差も許さず突き合わせるため、この経路を崩すと必ず落ちる。

### slot 番号 = グリッド位置

slot 1..35 が 7×5 グリッドへ `row=(slot-1)//7`, `column=(slot-1)%7` で機械的に対応する。
manifest の `column_centers_px` / `row_centers_px` が中心座標。ラベルは
`row_centers_px[row] + label_offset_y_px` に置かれ、PDFテキストとラスター枠が同じ式を共有する。

### 不変条件の強制箇所

- `build.py: validate_manifest()` — 3072×2048/300dpi、7×5、slot 1..35 の連番、
  日数と `day_stickers` の一致、コンセプトシール1枚かつ slot 35 を検査。破ると即例外。
- `verify.py` — 35枚のRGBA・四隅透明、PNG寸法/dpi/透過、PDFの1ページ・ページ寸法、
  日付ラベルだけがテキスト抽出可能（表題とコンセプトが抽出されたら失敗）、
  Unicodeフォント埋め込み、ラスター層の alpha soft mask、PDF/PNG完全一致。

`verify.sh` が通ることが完了条件。ただし自動検査は目視検査の代わりにならない
（`docs/QA_CHECKLIST.md` の項目を原寸で確認する）。

### フォント解決

manifest の `design_font_path` / `editable_font_path` が null のときは
`system_font_candidates()` が OS のフォントを順に試す（デザイン層は Hiragino Sans GB 優先、
編集可能テキストは YuGothR 優先）。build の標準出力に実際に採用されたフォントが出るので、
出力の見た目が変わったときはまずそこを見る。**OSフォント本体を販売物へ同梱しない。**

## ディレクトリの役割分離

| ディレクトリ | 用途 | 販売ZIPに含める |
|---|---|---|
| `customer/` | 納品PNG・編集可能PDF・README・`individual/` 35枚 | 含める |
| `qa/` | alignment-check PDF（赤/水色/マゼンタのガイド線入り） | **絶対に含めない** |
| `marketing/` | 販売ページ用 1024×1024 アイキャッチ | 含めない |

manifest、スクリプト、中間生成物も販売ZIPに入れない。

## 素材の扱い

`customer/individual/sticker-01.png` 〜 `sticker-35.png` は校了済みの独立透過PNGのみを置く。
クロマ原稿、グループ生成画像、抽出候補、旧稿、透明化テストを混ぜない。
1536×1024px の単純2倍化は不可（`docs/DECISIONS_AND_FAILURE_MODES.md` に失敗パターンの一覧がある）。
文字は画像生成モデルに描かせず、必ず manifest から決定論的に組版する。

## 商品情報管理（`listings/`）

`output/` が画像生成、`listings/` が販売面。後者は前者を**読むだけ**で書き換えない。

Etsy の商品コピー（タイトル・説明・タグ／英日）は **Claude が書き、Python は書かない**。
文面生成をツールに持たせると AI API 課金が発生するため、ツールは列挙・検証・API 送信・
整合性ガードのみを担当する。手順は `.claude/skills/update-listings/SKILL.md` にスキル化済み。

```sh
python3 listings/tools/listing.py plan     # 全リリースの状態と次の action を JSON 出力
python3 listings/tools/listing.py push --release <key>          # dry run
python3 listings/tools/listing.py push --release <key> --apply  # 実送信
```

標準ライブラリのみで動くため bundled Python は不要。`push` は既定 dry-run で、
manifest 変更・Etsy 制約違反・AI 開示なしのいずれかがあれば ERROR で停止する。
詳細は `listings/README.md`。

## 既存リリース

- `japanese-summer-flowers/2026-07` — 花テーマ、日付ラベルは花名
- `japanese-summer-events/2026-08` — イベントテーマ。PDF名が
  `editable-event-labels.pdf` でテーマごとに変わる（`artifacts` で指定）
