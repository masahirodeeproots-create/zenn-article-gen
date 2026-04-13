# Reader Pains

## [2026-04-13] artifact-traceability (global)

- 出典: DEV Community, HN governance layer記事
- 概要: 複数エージェントのartifactがどのrun/フェーズ由来か追跡できず、デバッグ・再現が困難。run_idがないとパイプライン全体再実行になる。

## [2026-04-13] phase-gate-design-uncertainty (jp/global)

- 出典: cloud-ace.jp; Anthropic「Building Effective Agents」
- 概要: どのフェーズにゲートを置くか、自動検証か人間チェックかの判断基準が不明。実践知が公開情報として少ない。

## [2026-04-13] context-propagation-degradation (zenn/HN)

- 出典: Zenn「Claude Codeのマルチセッション管理にジョブキューの概念を取り入れる」(10 likes); HN governance layer記事
- 概要: 10体規模になるとフェーズ間のcontext伝達で前提情報が欠落し、後続エージェントの出力が的外れになる（伝言ゲーム劣化）。contextウィンドウ溢れも問題。

## [2026-04-13] loop-termination-criteria (global)

- 出典: machinelearningmastery.com; Anthropic「Building Effective Agents」
- 概要: 品質が上がらないのに回し続けてコスト浪費 vs 早く止めすぎて低品質のまま完了、という両方の失敗が起きる。停滞検知・スコア閾値・最大イテレーション数の組み合わせ方の知見が少ない。

## [2026-04-13] zenn-ai-posting-compliance (zenn)

- 出典: Zenn「AIによるコンテンツ執筆に関するZennの方針（2026-03-10）」
- 概要: AIエージェントが書いた記事をZennに投稿して規約違反にならないか不安。「AIが下書き＋人間が検証・加筆」ならOKという解釈が広まりつつあるが確信が持てない開発者が多い。

## [2026-04-13] kol-personalization-gap (global)

- 出典: trysight.ai; noimosai.com; aidma-hd.jp
- 概要: マルチエージェントで「汎用コンテンツ」は生成できても「そのKOLらしい」投稿指示書が作れない。KOL固有のトーン・語彙・価値観・SNSスタイルを反映した個別化が最難関。ブランドガイドラインと個人スタイルのバランス調整をどのエージェントが担うか不明確。

## [2026-04-13] creative-quality-evaluation-subjectivity (global)

- 出典: noimosai.com; mirra.my; Anthropic multi-agent research
- 概要: コーディングタスクと違い、コンテンツの「良し悪し」はテストで自動検証できない。LLMに「10点満点で採点」させても実際のエンゲージメントと乖離することが多く、何を品質ゲートにするか判断できない開発者が多い。

## [2026-04-13] harness-cost-complexity (global)

- 出典: anthropic.com/engineering/harness-design-long-running-apps; HN実装記事
- 概要: フルハーネス実装は単一エージェントの20倍コスト（$9→$200）。「ちゃんとしたマルチエージェントを作るにはどれだけのコストがかかるか見えない」という不安が多い。費用対効果の判断基準がなく、どの程度の規模から本格ハーネスを使うべきかの実践知が不足。

## [2026-04-13] subagent-context-exhaustion (jp)

- 出典: zenn.dev/tacoms「Claude CodeのSub agentsでコンテキスト枯渇問題をサクッと解決できた」; code.claude.com/docs/ja/sub-agents
- 概要: 長いタスクでエージェントのコンテキストウィンドウが溢れて処理が途中で止まる問題。サブエージェントに委譲することで独立コンテキストウィンドウを確保できるが、「どのタイミングでサブエージェントに切り出すか」の設計判断が難しい。

## [2026-04-13] agent-role-granularity-decision (global/jp)

- 出典: anthropic.com/engineering/multi-agent-research-system; cloud-ace.jp
- 概要: 10体のエージェントをどこで切るか（何を1エージェントの責務にするか）の粒度判断が難しい。細かすぎるとcontext受け渡しコストが増大、粗すぎると並列化の恩恵がない。「1エージェント1成果物ファイル」という設計原則が実践的に機能するが、知られていない。

