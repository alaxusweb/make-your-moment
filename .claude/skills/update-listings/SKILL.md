---
name: update-listings
description: Rewrite Etsy product copy (title, description, tags in English and Japanese) for sticker releases based on the market research document, then push it through the Etsy API. Use when the user asks to update listings, refresh product info, apply new market data, or register a new release on Etsy.
---

# 商品情報の更新

`output/releases/<theme>/<year-month>/manifest.json` を巡回し、市況データに基づいて
Etsy の商品情報（タイトル・説明・タグ／英日）を書き換える。

## 役割分担

コピーを書くのは **あなた（Claude）** の仕事。Python ツールは AI を呼ばない。
機械的な処理（列挙・検証・API 送信・整合性ガード）だけをツールに任せる。

```
listings/tools/listing.py plan        # 何をすべきかの一覧（JSON）
listings/tools/listing.py init-draft  # 原稿の雛形（ハッシュ入り）
listings/tools/listing.py validate    # Etsy 制約の検証
listings/tools/listing.py push        # 既定 dry-run、--apply で送信
listings/tools/listing.py link        # リリースと listing_id の紐付け
```

すべて `python3` で動く（PIL や reportlab は不要）。

## 手順

### 1. 市況データを確認する

`docs/compass_artifact.md` が市況データ。ユーザーが「市況を最新に」と言った場合、
または最終更新から時間が経っている場合は、WebSearch で Etsy の
日本テーマ・デジタルステッカー市場を再調査し、このファイルを**上書き**する。
上書きすると全 draft が `rewrite_draft_market_changed` になる（意図した挙動）。

### 2. plan を読む

```sh
python3 listings/tools/listing.py plan
```

`releases[].action` が次にやることを示す。

| action | 対応 |
|---|---|
| `link_required` | 未紐付け。`shop-listings` で既存商品を列挙し、対応を確認して `link`。Etsy 側に該当商品がなければ新規出品なので、原稿を書いてから `create` |
| `write_draft` | 原稿がない。新規執筆 |
| `rewrite_draft_manifest_changed` | 素材が変わった。原稿を書き直す |
| `rewrite_draft_market_changed` | 市況が変わった。キーワードを見直す |
| `fix_draft` | 原稿が壊れている |
| `push` | 原稿は最新。Etsy へ送る |
| `up_to_date` | 何もしない |

`plan` の出力には各リリースの全シール名（和名・ローマ字）とおまけ内容が入っている。
manifest.json を個別に読み直す必要はない。

### 3. 原稿を書く

```sh
python3 listings/tools/listing.py init-draft --release <theme>/<year-month>
```

`listings/drafts/<theme>/<year-month>.json` が生成される。ハッシュは埋まっているので
**`source` ブロックは触らない**。`focus_keyword` と `listings.en` / `listings.ja` を埋める。

市況データ由来の執筆ルール:

- タイトルは前方 40 文字に主要キーワードを置く（`focus_keyword` に同じ語を入れる）
- タイトル 140 文字以内、`%` `:` `&` `+` は各 1 回まで
- タグは 13 個ちょうど、各 20 文字以内、重複禁止、タイトルの語をそのまま繰り返さない
- **主言語は日本語で固定**（Etsy のデフォルト言語は変更できない）。`ja` ブロックが
  `updateListing` で主言語スロットへ、`en` ブロックが翻訳スロットへ入る。
  英語コピーを `ja` ブロックに入れない
- 米国 Etsy 向けの SEO キーワードは `en` ブロックに置く（`focus_language` は `en`）
- 日本語タグは日本語の検索語で組み直す（英語の直訳にしない）
- 季節キーワードはピークの 6〜8 週間前に出す

**事実と異なる記述をしない**（Etsy の商品説明は表示義務がある）:

- GoodNotes 専用ファイルは同梱していない。「GoodNotes で使える透過 PNG」は真だが
  「GoodNotes ファイル同梱」は虚偽
- PDF は全面ベクターではない。編集可能なのは日付ラベルのテキストだけ
- 枚数・寸法・dpi は manifest の値をそのまま使う（`plan` に入っている）

**AI 開示は必須**。`compliance.ai_disclosure` は true のまま、説明文にも開示文を入れる。
Etsy は 2026-01-14 から生成 AI 開示を強制執行している。外すと出品削除リスク。

ただし **Etsy が実際に見るのは Shop Manager の「制作方法 > whatContent:ai_gen」
チェックボックス**であり、これは API に存在しないためツールからは設定できない。
`validate` が通っても規約を満たしたことにはならない。公開前に必ずユーザーへ
手動チェックを依頼すること。

### 4. 検証する

```sh
python3 listings/tools/listing.py validate --all
```

ERROR が 1 件でもあれば push は拒否される。WARN は判断材料。

### 5. 送信する

```sh
python3 listings/tools/listing.py push --release <key>            # dry run
python3 listings/tools/listing.py push --release <key> --apply    # 実送信
```

**必ず dry-run の内容をユーザーに見せて確認を取ってから `--apply` する。**
本番の販売ページを書き換える操作なので、承認なしに実行しない。

`--apply` は PATCH → 翻訳 PUT → GET 読み戻し照合まで行う。読み戻しが一致しない場合は
「pushed」として記録せずに終了するので、その場合は Etsy 側を目視確認する。

## 認証

`listings/config/etsy.json`（gitignore 済み）に認証情報。未設定なら次を案内する。

```sh
cp listings/config/etsy.example.json listings/config/etsy.json
# keystring と shared_secret をデベロッパーダッシュボードから転記
python3 listings/tools/listing.py resolve-shop --shop-name <shop> --write
python3 listings/tools/listing.py authorize
```

必要スコープは `listings_r listings_w shops_r`。アクセストークンは自動更新され書き戻される。
`authorize` はブラウザ操作を伴うので、**ユーザー自身に実行してもらう**（`!` プレフィックスで
このセッションから実行できる）。

## やらないこと

- `output/` 配下を書き換えない。画像生成パイプラインの領域で、このスキルは読むだけ
- 未紐付けのリリースを勝手に紐付けない。listing_id は必ずユーザーに確認する
- registry の `--force` を自分の判断で使わない
