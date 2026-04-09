# Dev Simulator — Round Controller

3つの独立エージェント（Human役・Claude役・Director）を使って開発プロセスをシミュレーションし、リアルな開発ログを生成する。

## アーキテクチャ

```
[sim_director] ← 完成形を知っている唯一のエージェント
      ↓ 不満を生成
[sim_human]    ← 要件だけ知っている。Directorからの不満を自分の言葉で伝える
      ↓ 発言
[sim_claude]   ← 一般知識だけ。Human役の不満に応答する
      ↓ 提案・実装
[sim_director] ← 現在の実装を完成形と比較 → スコア → 次の不満
      ...繰り返し
```

**重要**: 3エージェントはそれぞれ独立したサブエージェントとして呼び出す。1つのAIが3役を演じてはならない。

## プロセス

### 事前準備
1. `source-material/post-instructions-orchestrator-instructions.md` を読む
2. `source-material/post-instructions-orchestrator-skill.md` を読む
3. これらの内容はDirectorへの入力として使う（Human役・Claude役には渡さない）

### ラウンドループ

各ラウンドで以下を順番に実行:

**Step 1: Director**（ラウンド1では不要。ラウンド2以降）
- 入力: 完成形の仕様 + これまでの会話ログ
- 出力: 完成度スコア + 次の不満
- スコア ≥ 95 なら STOP

**Step 2: Human役**
- 入力: これまでの会話ログ + Directorからの不満（ラウンド1では初期要件を自分で出す）
- 出力: Human役の発言（自然な口語体）
- **Directorの不満を「自分の体験」として自然に言い換える**

**Step 3: Claude役**
- 入力: これまでの会話ログ + Human役の最新発言
- 出力: 技術的な提案・実装方針

**Step 4: 会話ログに追記**
Human役とClaude役の発言を会話ログに追加（Directorの出力は含めない）

### ラウンド1の特殊処理
- Directorは不要（まだ比較対象がない）
- Human役が初期要件を出す
- Claude役が初期設計を提案する

## 出力形式

最終的に `dev_simulation_log.md` に以下の形式で保存:

```markdown
# Development Log: post-instructions-orchestrator

## Round 1: 初期要件

👤 Human:
{発言}

🤖 Claude:
{提案・実装}

✅ Result: {この時点での成果}

---

## Round 2: {問題の概要}

👤 Human:
{不満・バグ報告}

🤖 Claude:
{原因推測・修正提案}

👤 Human:
{追加の反応}

🤖 Claude:
{修正内容}

✅ Result: {この時点での成果}

---
...
```

## 停止条件

- Directorのスコアが **95/100以上** → 停止
- または **10ラウンド** に達したら停止

## 重要なルール

- **3エージェントは必ず独立したサブエージェントとして呼び出す**
- Directorの出力はログに含めない
- Human役の不満は具体的なアウトプットの症状で表現する
- Claude役は間違った仮説を立ててよい（むしろ立てるべき）
- 一直線で正解にたどり着かないこと
