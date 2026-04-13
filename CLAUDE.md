# Zenn Article Generator v2.0 — Orchestrator Guide

AIエージェント12体でZennのトレンド入りレベルの技術記事を自動生成するシステム。

## アーキテクチャ

2つのPDCAサイクルで構成:
- **素材PDCA**: 何を書くか（Phase 0-2）
- **記事PDCA**: どう書くか（Phase 3）

### Phase 1: 固定素材の生成（Code Analyzer）
ソースコードから事実ベースの素材5つを一括生成。config.jsonのtopicも生成。

### Phase 0: 知識の準備（Trend Searcher）
topicからトレンド・読者の痛みを検索。knowledge/に蓄積。

### Phase 2: 体験ストーリー（Dev Simulator + Material PDCA）
3独立AI（Human/Claude/Director）でシミュレーション → 素材改善ループ。

### Phase 3: 記事生成（Writer + 記事PDCA）
全素材から記事生成 → レビュー → スタイルガイド更新ループ。

## コマンド一覧

```
python orchestrator.py init --source <file1> <file2>  # 初期化+Code Analyzer
python orchestrator.py analyze-code                    # Phase 1（単体実行用）
python orchestrator.py after-analyze-code
python orchestrator.py search-trends                   # Phase 0
python orchestrator.py after-search-trends
python orchestrator.py simulate                        # Phase 2
python orchestrator.py after-simulate
python orchestrator.py review-materials                # 素材改善ループ
python orchestrator.py after-material-review <score>
python orchestrator.py after-material-update
python orchestrator.py start-iteration                 # Phase 3
python orchestrator.py after-write
python orchestrator.py after-review <score>
python orchestrator.py after-update
python orchestrator.py after-consolidate
python orchestrator.py status
```

## フロー

```
init → analyze-code → search-trends → simulate →
review-materials (loop) → start-iteration (loop) → 完成
```

## 停止条件

- 素材PDCA: 停滞(±0.5×3回) or 最大5回
- 記事PDCA: 2連続 ≥ 9.0/10 / 停滞(±0.5×3回) / 最大10回

## コードの責務 vs エージェントの責務

| コード | エージェント |
|--------|------------|
| イテレーション番号管理 | トレンド・痛みの検索と整理 |
| ファイルのコピー・クリア | ソースコードの分析・素材生成 |
| スコアの記録・停滞検出 | 体験ストーリーの生成 |
| ベンチマークのランダムサンプリング | 素材・記事の評価・改善 |
| 検索キャッシュの重複チェック | スコアの読み取り |
