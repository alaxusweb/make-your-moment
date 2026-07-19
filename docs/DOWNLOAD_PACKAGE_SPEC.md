# PDF・ダウンロードデータ仕様

## 購入者向け最低構成

```text
customer/
├── <theme>-<YYYY-MM>-3072x2048-300dpi-transparent.png
├── <theme>-<YYYY-MM>-editable-flower-labels.pdf
├── README.txt
└── individual/  # 商品に分割データを含める場合
```

alignment-check PDF、manifest、コンタクトシート、生成スクリプトは購入者向けに含めない。

## PNG

- 3072×2048px
- 300dpiメタデータ
- sRGB RGBA
- 四隅を含む背景が完全透明
- PDFを同じサイズで完全ラスタライズしたもの
- 表題、コンセプト、花名を含め全要素がラスタライズ済み

## PDF

- 1ページ、737.28×491.52pt（約260.10×173.40mm）
- 印刷時は`Actual size / 100%`を推奨。`Fit to page`では縮小される場合がある
- 絵柄はラスタであり、全面ベクターデータではない
- 編集可能なのは日付シールの`和名 / Romaji`だけ
- 表題、コンセプト、ラベル枠、おまけ、絵柄は編集対象外
- 日本語フォントを埋め込むが、購入者の編集環境では別のシステムフォントへ置換してよい
- 長い文字列へ変更するとラベル枠からはみ出すため、20px相当を基準に調整する
- ビューア上で透明ページが白く表示される場合がある

商品説明では次を明示する。

```text
Includes a transparent 3072 × 2048 px PNG at 300 dpi and a one-page print PDF.
Artwork is raster. Only the flower-name labels remain editable PDF text.
```

## QA PDF

`qa/<theme>-<YYYY-MM>-alignment-check.pdf`は制作確認専用。赤い列中心線、
水色の行中心線、マゼンタのラベル枠を含むため、販売ZIPへ混入させない。

## ライセンス

販売前に、購入者の利用可能範囲を定めたライセンス文書を追加する。個人利用、
商用利用、再配布、改変、印刷物販売などの条件は販売者が決めるため、この雛形では
自動決定しない。OSフォントファイル自体は同梱しない。
