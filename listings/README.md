# 商品情報管理（Etsy）

`output/` の画像生成パイプラインとは独立した、販売面の管理領域。
`output/` 配下は**読むだけ**で、書き換えない。

## 構成

```text
listings/
├── config/
│   ├── etsy.example.json     # 認証情報の雛形
│   └── etsy.json             # 実体（gitignore）
├── drafts/
│   └── <theme>/<year-month>.json   # 商品原稿（英日）
├── registry/
│   ├── registry.sqlite3      # リリース ↔ Etsy listing の紐付け（正）
│   └── registry.json         # 同内容の書き出し（git レビュー用）
└── tools/
    ├── listing.py            # CLI
    ├── release.py            # manifest 読み取り
    ├── draft.py              # 原稿スキーマ・Etsy 制約検証
    ├── registry.py           # 紐付け管理
    └── etsy_api.py           # Etsy Open API v3 クライアント
```

## 設計方針

**コピーは Claude が書き、ツールは書かない。** 文面生成を Python に持たせると AI API が
必要になりコストが発生する。ツールは列挙・検証・送信・整合性ガードだけを担当し、
市況の読解とコピー執筆は Claude Code のセッション（サブスクリプション）で行う。

手順は `.claude/skills/update-listings/SKILL.md` にスキル化してある。
「商品情報を更新して」と指示すれば同じ流れが再現される。

## コマンド

```sh
python3 listings/tools/listing.py plan       # 全リリースの状態を JSON で出力
python3 listings/tools/listing.py status     # 同じ内容を人間向けに
python3 listings/tools/listing.py init-draft --release <theme>/<year-month>
python3 listings/tools/listing.py validate --all
python3 listings/tools/listing.py push --release <key>           # dry run
python3 listings/tools/listing.py push --release <key> --apply   # 実送信
python3 listings/tools/listing.py push --release <key> --language ja --apply  # 部分反映
python3 listings/tools/listing.py shop-listings                  # 既存商品の一覧と紐付け状態
python3 listings/tools/listing.py create --release <key>          # 新規出品 dry run
python3 listings/tools/listing.py create --release <key> --apply  # draft 作成 + 自動 link
python3 listings/tools/listing.py link --release <key> --listing-id <id>
python3 listings/tools/listing.py resolve-shop --shop-name <name> --write  # shop_id 取得
```

`resolve-shop` は API キーのみで動く（OAuth 前に実行できる）。shop_id は Shop Manager の
画面に表示されないため、この方法で引く。

依存は標準ライブラリのみ。`build.sh` と違い bundled Python は不要。

## 誤更新を防ぐ仕組み

手動登録した商品との対応が失われている状態から始めるため、紐付けと鮮度を
ストレージ層と検証層の両方で守る。

| 事象 | 挙動 |
|---|---|
| 1 リリースに 2 つの listing_id | `link` が拒否（PRIMARY KEY） |
| 1 listing_id を 2 リリースへ | `link` が拒否（UNIQUE 制約） |
| 原稿執筆後に manifest が変わった | `validate` / `push` が ERROR で停止 |
| 原稿執筆後に市況が変わった | WARN 表示（`plan` は再執筆を指示） |
| Etsy 制約違反（文字数・タグ数・禁止文字） | `push` が ERROR で停止 |
| AI 開示なし | `push` が ERROR で停止 |
| 送信したが Etsy 側に反映されていない | 読み戻し照合で検出、pushed として記録しない |

`push` は既定で dry-run。`--apply` を付けたときだけ送信する。

## 言語の割り当て（重要）

このショップの**主言語は日本語で固定**されている。Etsy のデフォルト言語変更は
サポート経由でしか行えず、変更できない前提で運用する。したがって各 draft は:

```json
"primary_language": "ja",   // updateListing (PATCH) で送られる = 日本語コピー
"focus_language": "en"      // 英語 SEO キーワードの検証対象
```

- `ja` ブロック → `updateListing` で主言語スロットへ。日本語圏の表示と、
  en 以外のロケールからのフォールバック表示に使われる
- `en` ブロック → `updateListingTranslation` で英語スロットへ。市況レポートが
  狙う米国 Etsy の検索面はここ

**英語コピーを主言語スロットに入れてはいけない**（過去にその状態になっており、
英語スロットが空のまま放置されていた）。`focus_keyword` の前方40文字チェックは
`focus_language` に対して行われるので、主言語が ja でも英語 SEO は検証される。

部分反映が必要なときは `--language` で言語を絞れる。部分 push は registry に
「完了」として記録されないため、残作業が隠れない。

## Etsy API

- `PATCH /v3/application/shops/{shop_id}/listings/{listing_id}` — 主言語（英語）
- `PUT  .../listings/{listing_id}/translations/ja` — 日本語翻訳
- `POST https://api.etsy.com/v3/public/oauth/token` — `grant_type=refresh_token`

必要スコープは `listings_r listings_w shops_r`。refresh token は使用のたびに更新されるため、
`etsy.json` に自動で書き戻す（このファイルを失うと OAuth をやり直しになる）。

### 初期設定

```sh
cp listings/config/etsy.example.json listings/config/etsy.json
# keystring と shared_secret を Etsy デベロッパーダッシュボードから転記

python3 listings/tools/listing.py resolve-shop --shop-name <shop> --write  # shop_id
python3 listings/tools/listing.py authorize                                # refresh_token
```

`authorize` は PKCE 認可フローを実行し、localhost で待ち受けてコードを受け取る。
Etsy が localhost の redirect_uri を拒否する場合は `--paste` を付け、ブラウザの
アドレスバーの URL を貼り付ける（ページが開けなくてもコードは URL に載っている）。
redirect_uri はアプリ登録時の値と**完全一致**していなければならない。

### x-api-key の形式

認証なしの呼び出し（`findShops` など）は `keystring:shared_secret` を要求する。
OAuth 付きの呼び出しは keystring 単体で通るが、Etsy が shared secret を要求した場合は
自動で結合形式に切り替えて再試行する。

書き込みボディの形式は Etsy の公式資料内でも記述が揺れているため、`body_encoding` で
`form`（既定・配列はカンマ結合）と `json` を切り替えられる。どちらでも送信後に GET で
読み戻して照合するので、形式ミスは silent failure にならない。

## 新規出品

`create` は `createDraftListing` を呼び、**必ず draft 状態**で作る。価格・デジタル
ファイル・商品写真は Shop Manager で人が確認する前提なので、API 経由で販売開始
できないようにしてある。作成後は自動で registry へ link し、`en` 翻訳も送る。

新規出品の形は `etsy.json` の `listing_defaults` に置く。既存商品から採取した値で、
Etsy 側でポリシーが変わったらここを直す。雛形は `etsy.example.json` にもある。

| キー | 値 | 意味 |
|---|---|---|
| `taxonomy_id` | 6844 | Etsy のカテゴリ ID |
| `type` | download | ダウンロード商品 |
| `quantity` | 100 | 在庫数 |
| `who_made` / `when_made` | i_did / 2020_2026 | 出品者情報 |
| `return_policy_id` | 1 | 返品ポリシー |
| `price` / `currency` | 5.0 / USD | `create --price` で上書き可 |

不足があれば `create` が実行前に拒否する（`listing_defaults in etsy.json is
missing [...]`）ので、欠けたまま出品されることはない。

作成後に手作業で残るもの:

- デジタルファイルのアップロード（PNGシート・PDF・個別PNG）
- 商品写真（`marketing/` のアイキャッチ）
- 価格の確認と公開

## 将来やること

デジタルファイルと商品画像のアップロード（`uploadListingFile` / `uploadListingImage`）は
未実装。現状は Shop Manager で手動。
