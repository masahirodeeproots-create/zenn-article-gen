# Dev Simulator — Round Controller

3つの独立エージェント（sim_human / sim_claude / sim_director）を使って
開発プロセスをシミュレーションし、体験ストーリーを生成する。

## 重要
3エージェントはそれぞれ独立したサブエージェントとして呼び出す。
1つのAIが3役を演じてはならない。

## 事前準備
1. simulator_source_files を読む（Directorへの入力）
2. materials/fixed/system_overview.md を読む（Human役の初期要件理解）
3. materials/trend_context.md を読む（Human役に渡す）
4. materials/reader_pain.md を読む（Director役に渡す）

## ラウンドループ

### ラウンド1（特殊）
- Human役が初期要件を出す（system_overview.md参考）
- Claude役が初期設計を提案する
- Directorは不要

### ラウンド2以降
Step 1: Director → 完成形+ログ比較 → スコア+次の設計の問い（≥95でSTOP）
Step 2: Human → ログ+Directorの問い → 設計仮説（トレンド知識を活用）
Step 3: Claude → ログ+Human発言 → 設計パターン提案
Step 4: 会話ログに追記

## 出力
materials/dev_simulation_log.md に保存。

```markdown
# Development Log

## Round 1: 初期の設計仮説

👤 Human:
{設計仮説・要件}

🤖 Claude:
{設計パターンの提案}

✅ Design Insight: {このラウンドで得られた設計原則}

---
```

以下が統合される: ②体験 / ④失敗 / ⑦トレンド接続 / ⑨痛み / ⑩次のアクション / ⑪未解決の問い

## ログの抽象度
✅ 設計原則、発見プロセス、他ドメインとの類推、簡易ASCII図、迷い、素朴な疑問
❌ ファイル名、Phase番号、コードスニペット、JSON構造、エラーメッセージ

## Directorの出力はログに含めない

## 停止条件
- Directorスコア ≥ 95/100 → 停止
- または 10ラウンド → 停止

## 重要なルール
- 3エージェントは必ず独立したサブエージェントとして呼び出す
- 会話は設計原則レベルで行う。実装詳細には踏み込まない
- 一直線で正解にたどり着かないこと
