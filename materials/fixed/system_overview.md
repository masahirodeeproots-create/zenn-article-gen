# System Overview

## このシステムは何か

SNSインフルエンサー（KOL）向けの投稿指示書スライドデッキ（PPTX）を、受注書・KOLリスト・商品情報を入力として受け取り、10体のClaudeエージェントが連携して全自動生成するワークフロー自動化システム。オーケストレーターがリードとして各エージェントを逐次スポーンし、フェーズごとに成果物の存在を確認してから次フェーズへ進む「成果物ゲート駆動」設計を採用している。

## 誰のためのシステムか

インフルエンサーマーケティングを実施する広告代理店・ブランドのマーケティング担当者。

## 何を入力して何を出力するか

受注書・KOLリスト・商品情報（inputs/）を入力とし、KOL別クリエイティブ指示スライドデッキ（`{project}.pptx`）を出力する。

## なぜ作ったのか

KOL指示書の作成は、KOLのトンマナ調査・クリエイティブ方向設計・キャプション作成・スライド組版・AI画像生成・レビューという多段階の手作業であり、KOL1名あたりに相当の時間を要していた。各フェーズに専門エージェントを割り当てることで、人手介入なしに1回のコマンド実行で完走できる仕組みを目指して開発された。

## 専門用語の説明

| 用語 | 説明 |
|------|------|
| KOL (Key Opinion Leader) | SNSインフルエンサーの呼称 |
| 投稿指示書 | SNS投稿のクリエイティブ方針・キャプション・シーン構成をまとめたスライドデッキ |
| classic_small / thin_large | KOL数3名以下 vs 4名以上による実行モード分類 |
| data_binding.json | スライドテンプレートへのテキスト・画像マッピング定義ファイル |
| run_id | 同一実行サイクルの成果物を識別するプロヴェナンスID |
| scene_count | KOL1名あたりに生成するシーン画像数（通常4枚、YouTubeLongのみ6枚） |
| render_medium | KOL画像の描画スタイル（hand_drawn_info / semi_real_anime / commercial_anime） |
| per_kol_packages.json | Plannerが出力するKOL別クリエイティブ方針パッケージ |
| assets_resolved.json | 全アセットの最終統合マニフェスト（Visualizer/Builderが参照） |

## 読者が知るべき前提

- Claude Codeのサブエージェント機能（`claude -p` によるエージェント呼び出し）の基本概念
- python-pptxによるPowerPointのプログラム操作（テキスト書き込み・画像挿入・Shape操作）
- SNSインフルエンサーマーケティングのキャンペーン構造（KOL・プラットフォーム・クリエイティブ素材の概念）
- AIによる画像生成ツール（banana4claude / nanobanana-wrapper）をエージェントが呼び出せる環境
- PPTX内のShape名・Z-order・endParaRPrなどpython-pptx固有の概念
