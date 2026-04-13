# Zenn Article Generator v3.0 — AutoAgent方式

AIエージェント12体でZennのトレンド入りレベルの技術記事を自動生成するシステム。
orchestrator.pyがMetaChainとして全エージェントを自動呼び出し・自動判断・自律ループする。

## 使い方

```bash
# 全自動実行（1コマンドで完走）
python orchestrator.py run --source source-material/file1.md source-material/file2.md

# 状態確認
python orchestrator.py status
```

## フロー（全自動）

```
run コマンド
  → phase_init         : 成果物クリア、知識DB保持
  → phase_analyze_code : Code Analyzer（topic + 固定素材5つ）
  → phase_search_trends: Trend Searcher（5メディア検索）
  → phase_simulate     : Dev Simulator（3独立AIシミュレーション）
  → phase_review_materials: Material Review Loop（最大5回、停滞で打ち切り）
  → phase_article_loop : Article Loop（最大10回、2連続9.0以上で完了）
  → COMPLETE
```

## 停止条件

- 素材PDCA: 停滞(±0.5×3回) or 最大5回
- 記事PDCA: 2連続 ≥ 9.0/10 / 停滞(±0.5×3回) / 最大10回

## エージェント呼び出し

orchestrator.pyが `claude -p` でサブエージェントを実行する。
各エージェントは `.claude/agents/*.md` に定義されている。
人間の介入なしで全フェーズが完走する。
