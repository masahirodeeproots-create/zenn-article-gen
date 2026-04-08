# Zenn Article Generator - Orchestrator Guide

OshigotoAIシステムについてのZenn記事を反復的に生成・改善するワークフロー。

## アーキテクチャ

### Sub-Agents
1. **Writer Agent** (`.claude/agents/writer.md`): 記事生成。style_guide.md + source-material/ のみ参照
2. **Reviewer Agent** (`.claude/agents/reviewer.md`): 記事レビュー。human-bench/articles/ と比較
3. **Style Guide Updater** (`.claude/agents/style_guide_updater.md`): スタイルガイド改善

### 情報フロー
```
source-material/ → Writer → article.md
                      ↑
style_guide.md ←── Style Guide Updater ←── Reviewer ←── human-bench/articles/
```

## ワークフロー

1. トピック決定
2. `iterations/{N}/` 作成、style_guide.md をコピー
3. Writer Agent 実行 → `iterations/{N}/article.md`
4. Reviewer Agent 実行 → `iterations/{N}/review.md`
5. Style Guide Updater 実行 → style_guide.md 更新 + `iterations/{N}/changelog.md`
6. スコア確認 → 8.5以上なら完了、未満なら次のiterationへ

## 記事トピック

「Claude Codeで103個のSkillを持つAIエージェント基盤を作った話 — LLM as a Workflowという設計思想」
