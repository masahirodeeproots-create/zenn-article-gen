# Zenn Article Generator - Orchestrator Guide

AIエージェントシステムについてのZenn記事を反復的に生成・改善するワークフロー。

## アーキテクチャ

### Phase 0: 準備
1. `python orchestrator.py init <source_files>` — Config自動生成
2. `python orchestrator.py simulate` — Dev Simulation（3独立AI）

### Phase 1〜: 記事生成ループ
1. **Writer Agent** — dev_simulation_log.md + style_guide.md + anti_patterns.md を参照
2. **Reviewer Agent** — 読者体験型評価。ベンチマーク記事と比較
3. **Style Guide Updater** — ベンチマーク差分を具体例でガイドに追加

### 停止条件
- 2連続 ≥ 9.0/10
- 最大10イテレーション
- スコアジャンプ制限: +1.0/iter

## コマンド一覧
```
python orchestrator.py init <file1> <file2>   # Config自動生成
python orchestrator.py simulate               # Dev Simulation
python orchestrator.py after-simulate          # Simulation完了後
python orchestrator.py start-iteration         # 記事生成ループ開始
python orchestrator.py after-write             # Writer完了後
python orchestrator.py after-review <score>    # Reviewer完了後
python orchestrator.py after-update            # Updater完了後
python orchestrator.py after-consolidate       # Consolidation完了後
python orchestrator.py status                  # 状態確認
```
