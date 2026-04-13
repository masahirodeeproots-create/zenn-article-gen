# Trends


## [2026-04-13] multi-agent (zenn)

マルチエージェント協調の記事が増加

## [2026-04-13] verifiable-execution (global)

- 出典: DEV Community, HN governance layer記事
- 概要: 2026年の最重要マルチエージェント設計として「エージェントが何をしたか証明できること（Verifiable Execution）」が台頭。run_id/provenanceトラッキング・決定論的品質ゲートが実践パターンとして定着。

## [2026-04-13] anthropic-managed-agents (anthropic.com)

- 出典: anthropic.com/engineering/managed-agents
- 概要: brain/hands/session分離アーキテクチャ。ステートレスharnessでtime-to-first-token p50 60%改善。分離によりセキュリティ（credentialをサンドボックス外に保持）と差し替え可能性を両立。

## [2026-04-13] deterministic-quality-gate (HN)

- 出典: HN「I built a governance layer for multi-agent AI coding」
- 概要: LLMによる品質判断ではなく事前登録ルールベースの決定論的チェックが信頼性を高める。受領レジャー（append-only log）とコンテキストローテーション、独立サブエージェント方式が6ヶ月の実践から導出された知見。

## [2026-04-13] zenn-ai-policy (zenn)

- 出典: info.zenn.dev/2026-03-10-ai-contents-guideline; info.zenn.dev/2026-04-08-new-recent-articles
- 概要: ZennはAI自動生成の大量投稿を規約禁止。「著者主体（検証・洞察・経験が込められた記事）」を優遇する新アルゴリズムを2026-04-08に導入。

## [2026-04-13] multi-agent-phase-adoption (jp)

- 出典: cloud-ace.jp, ecosire.com, machinelearningmastery.com
- 概要: 2026年は単体エージェント→マルチエージェント移行の加速期。計画・実行・監視の役割分担でエラー率60%削減・速度40%改善が報告。フェーズ3（10-18ヶ月）でマルチエージェントワークフロー構築開始が標準的ロードマップ。

## [2026-04-13] multi-agent-parallel-research-90pct-gain (anthropic)

- 出典: anthropic.com/engineering/multi-agent-research-system
- 概要: Opus4（リード）＋Sonnet4（サブ）の並列マルチエージェント構成がシングルエージェントOpus4を90.2%上回る性能を達成。並列ツール呼び出しで複雑クエリの調査時間最大90%短縮。token使用量の増加が性能向上の80%を説明。詳細なタスク記述（出力フォーマット・ツール指示・境界定義）が重複防止のカギ。

## [2026-04-13] content-brief-one-to-eight-assets (global)

- 出典: trysight.ai/blog/multi-agent-ai-content-generation; fast.io/resources/ai-agent-social-media-automation; noimosai.com
- 概要: 2026年のコンテンツ自動化トレンド：1ブリーフから8チャネル別アセット（LinkedIn/Twitter/Instagram/TikTok等）を1時間以内に生成。従来は3人×3-5日の作業。エージェントワークフロー採用スタートアップでマーケティングオーバーヘッド80%削減・コンテンツ生産10倍を報告。Research→Strategy→Content→Reviewの役割分業が定番構成。

## [2026-04-13] visual-canvas-multi-agent-deliverable (HN)

- 出典: HN「Launch HN: Spine Swarm」(score:109)
- 概要: 複数エージェントがビジュアルキャンバス上で協調し、ピッチデッキ・競合分析・財務モデルなど複合成果物を生成。線形チャットではなく監査可能なワークフロー構造を維持。エージェントが異なるcanvasブロックを並列操作する設計。

## [2026-04-13] generator-evaluator-separation (anthropic)

- 出典: anthropic.com/engineering/harness-design-long-running-apps (2026-03-24)
- 概要: プランナー→ジェネレータ→エバリュエータの3層分離が長時間実行エージェントの標準ハーネス設計として確立。ファイルベース通信で各エージェント間の状態引き継ぎ。スプリント前に品質基準を「契約」として明示することで自己評価バイアスを防ぐ。単一エージェント（20分/$9）vs完全ハーネス（6時間/$200）で20倍のコスト差。

## [2026-04-13] context-engineering-jit (anthropic)

- 出典: anthropic.com/engineering/effective-context-engineering-for-ai-agents (2026-01-06)
- 概要: 「コンテキストエンジニアリング」という概念が体系化。LLMの注意予算に対し最小限の高信号トークンセットで結果最大化。プリロードでなくジャストインタイムのデータ取得、サブエージェント委譲でコンテキスト枯渇を防ぐ。モデル能力向上に伴い人間キュレーションを段階的に削減するアプローチ。

## [2026-04-13] agent-eval-three-layer (anthropic)

- 出典: anthropic.com/engineering/demystifying-evals-for-ai-agents (2026-03-18)
- 概要: エージェント評価の3層方式が整理された。コードベース評価（高速・客観）、モデルベース評価（柔軟・高コスト）、人間評価（高品質・低速）を組み合わせる。SWE-benchが1年で40%→80%超に向上。初期段階では20-50タスクからのスモールスタートを推奨。

## [2026-04-13] claude-code-subagent-feedback-loop (zenn/note)

- 出典: note.com/techocean_corp（Claude Code Subagentフィードバックループ記事）; zenn.dev/tacoms（コンテキスト枯渇問題解決）
- 概要: Claude CodeのSubagentをレビュワーとして運用することで抽象的フィードバックが可能に。サブエージェント分離でコンテキスト枯渇問題を解決するパターンが日本語コミュニティで普及中。記事生成・コード生成への応用事例が蓄積されている。

## [2026-04-13] harness-initializer-plus-checklist (anthropic)

- 出典: anthropic.com/engineering/effective-harnesses-for-long-running-agents
- 概要: 長時間実行エージェントのハーネス設計パターン：Initializer（基盤構築）とCodingフェーズを別プロンプトで分離。200以上のfeatureリストで早期完了宣言を防止。git history＋progress.txtによるコンテキスト再構築。「エージェントが完了を自己判断する」設計は失敗の温床。
