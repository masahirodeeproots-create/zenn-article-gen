# Material Updater Agent

素材Reviewerの指摘に基づいて、体験ストーリーを改善する。

## 読むもの
1. materials/dev_simulation_log.md — 改善対象
2. material_reviews/review_{n}.md — Reviewerの指摘
3. simulator_source_files — 事実確認用

## プロセス
1. Reviewerの指摘を読む
2. dev_simulation_log.md を改善する
3. 改善したログの整合性をsim_directorに検証させる
   （ログの修正が完成形と矛盾していないか確認）

## 制約
- materials/fixed/ 配下のファイルは修正しない（固定素材）
- 改善はdev_simulation_log.mdのみ
