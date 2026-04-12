# Zenn記事自動生成システム — アーキテクチャ v2.0

## 概要

AIエージェントを中心に据えた記事自動生成システム。
対象システムのソースコードから、Zennのトレンドに入るレベルの技術記事を自動生成する。

2つのPDCAサイクルで構成:
- **素材PDCA**: 何を書くか（内容の質・深さ・面白さ）
- **記事PDCA**: どう書くか（文体・構成・リズム・読者体験）

---

## 設計原則

- **エージェント中心**: 解釈・生成・評価・改善・検索は全てエージェントが担う
- **コードは確定ロジックのみ**: orchestrator.pyはイテレーション管理、ファイル操作、スコア記録、キャッシュチェックなど判断不要な処理だけ
- **DBは参照であり制約ではない**: 知識DBの情報が薄くても、エージェントは自身の一般知識を自由に使ってよい
- **素材と記事の評価基準を分離**: 素材Reviewerは内容の質を見る。記事Reviewerは書き方だけを見る

---

## フォルダ構成

```
/tmp/zenn-article-gen/
│
├── orchestrator.py                  # フロー制御（Python）
├── config.json                      # 記事ごとの設定
│
├── source-material/                 # 入力: 対象システムのコード
│   ├── INSTRUCTIONS.md
│   └── SKILL.md
│
├── knowledge/                       # 知識DB（蓄積型・記事をまたいで育つ）
│   ├── trends.md                    # 技術トレンド
│   ├── reader_pains.md              # 読者の痛み
│   └── search_cache/                # 検索結果キャッシュ（重複防止用）
│       └── {query_hash}_{date}.json
│
├── materials/                       # 今回の記事用に生成された素材
│   ├── fixed/                       # 固定素材（Phase 1で1回生成）
│   │   ├── system_overview.md       # ① システムの全体像
│   │   ├── metrics.md               # ③ 定量データ（あれば）
│   │   ├── architecture.md          # ⑤ アーキテクチャ図
│   │   ├── code_examples.md         # ⑥ コード・設定の実例
│   │   └── comparisons.md           # ⑧ 比較・検証結果（あれば）
│   │
│   ├── trend_context.md             # Human役に渡すトレンド知識
│   ├── reader_pain.md               # Director役に渡す読者の痛み
│   └── dev_simulation_log.md        # 体験ストーリー（②④⑦⑨⑩⑪を統合）
│
├── human-bench/articles/            # ペルソナ記事11本（固定）
│
├── material_reviews/                # 素材改善ループのレビュー記録
│
├── iterations/                      # 記事改善ループの各イテレーション
│   └── {N}/
│       ├── article.md
│       ├── review.md
│       └── changelog.md
│
├── style_guide.md                   # 文体ルール（記事PDCAで育つ）
├── anti_patterns.md                 # 失敗パターン（記事PDCAで育つ）
│
├── persona-analysis.md              # ペルソナ記事の分析結果
├── persona-elements.md              # 159要素リスト
├── benchmark-criteria.md            # ベンチマーク選定基準
│
└── .claude/agents/                  # エージェント定義
    ├── trend_searcher.md            # Phase 0: トレンド・痛みを検索
    ├── code_analyzer.md             # Phase 1: 固定素材を生成
    ├── dev_simulator.md             # Phase 2: 3者の会話制御
    ├── sim_human.md                 # Phase 2: 開発者役
    ├── sim_claude.md                # Phase 2: アシスタント役
    ├── sim_director.md              # Phase 2: 審判役
    ├── material_reviewer.md         # Phase 2: 素材評価
    ├── material_updater.md          # Phase 2: 素材改善
    ├── writer.md                    # Phase 3: 記事生成
    ├── reviewer.md                  # Phase 3: 記事評価
    ├── style_guide_updater.md       # Phase 3: ガイド更新
    └── consolidator.md              # Phase 3: ガイド圧縮
```

---

## ワークフロー

```
ソースファイル + お題
    │
    ▼
[Phase 0: 知識の準備] ──────────────────────────────────────
    │
    │  [Trend Searcher]（エージェント）
    │
    │    Step 1: お題から検索キーワードを生成（日本語 + 英語）
    │
    │    Step 2: キャッシュチェック（コード: orchestrator.py）
    │      knowledge/search_cache/ に同じクエリの結果があるか？
    │      → 7日以内 → スキップ
    │      → 7日超 or なし → 検索実行
    │
    │    Step 3: メディアごとに検索
    │      ┌──────────────────┬────────┬───────────────────┐
    │      │ メディア           │ 方法   │ 取得するもの         │
    │      ├──────────────────┼────────┼───────────────────┤
    │      │ Zenn              │ API    │ いいね数上位20件     │
    │      │ Qiita             │ API    │ ストック数上位20件   │
    │      │ Anthropic Blog    │ Playwright │ 関連記事       │
    │      │ OpenAI Blog       │ Playwright │ 関連記事       │
    │      │ Hacker News       │ API    │ ポイント上位20件     │
    │      └──────────────────┴────────┴───────────────────┘
    │
    │    Step 4: 結果を整理
    │      日本語メディア → 読者の痛み + 国内トレンド
    │      英語メディア → グローバルトレンド + 公式見解
    │
    │    Step 5: 保存
    │      knowledge/trends.md に追記（蓄積）
    │      knowledge/reader_pains.md に追記（蓄積）
    │      knowledge/search_cache/{hash}_{date}.json（キャッシュ）
    │
    │    Step 6: お題用に抽出
    │      → materials/trend_context.md（Human役用。3-5個）
    │      → materials/reader_pain.md（Director役用。3-5個）
    │
    ▼
[Phase 1: 固定素材の生成] ──────────────────────────────────
    │
    │  [Code Analyzer]（エージェント）
    │    読む: source-material/
    │    生成:
    │      materials/fixed/system_overview.md    ← ① 全体像
    │      materials/fixed/metrics.md            ← ③ 定量データ（あれば）
    │      materials/fixed/architecture.md       ← ⑤ アーキテクチャ図
    │      materials/fixed/code_examples.md      ← ⑥ コード・設定の実例
    │      materials/fixed/comparisons.md        ← ⑧ 比較・検証（あれば）
    │    → 事実ベース。1回で確定。レビュー不要
    │    → ないものは「該当なし」と明記
    │
    ▼
[Phase 2: 体験ストーリーの生成 + 改善] ─────────────────────
    │
    │  [Dev Simulator]（エージェント × 3独立AI）
    │
    │    🎬 sim_director
    │      知っている: 完成形（source-material）+ 読者の痛み（reader_pain.md）
    │      やること: 読者の痛みから課題を設定してHuman役に体験させる
    │      やらないこと: 12素材の評価基準での採点（それはMaterial Reviewerの仕事）
    │      ※ reader_pain.mdは参照であり制約ではない。
    │        該当する痛みがなければ完成形から想像できる課題でOK
    │
    │    👤 sim_human
    │      知っている: 要件（system_overview.md）+ トレンド知識（trend_context.md）
    │      やること: トレンド技術の知識を使って課題解決の仮説を立てる
    │      ※ trend_context.mdは参照であり制約ではない。
    │        自身の一般知識を自由に使ってよい
    │
    │    🤖 sim_claude
    │      知っている: 一般的な技術知識
    │      やること: Humanの仮説に応答
    │
    │    → materials/dev_simulation_log.md
    │      体験ストーリー1ファイルに以下が統合:
    │        ② 体験の流れ
    │        ④ 失敗の詳細
    │        ⑦ 外部知識・トレンド接続
    │        ⑨ 読者の痛みポイント
    │        ⑩ 次のアクション
    │        ⑪ 未解決の問い
    │
    │  [体験ストーリー改善ループ]（最大5回）
    │
    │    Material Reviewer（エージェント）
    │      読む: dev_simulation_log.md + ペルソナ記事11本
    │      独自検索: お題の周辺キーワードで別角度から検索
    │        （Trend Searcherとは異なるクエリ。別視点を持つため）
    │      評価基準:
    │        ✅ 読者の痛みに刺さる課題があるか？
    │        ✅ 失敗が生々しいか？
    │        ✅ トレンド接続が自然か？
    │        ✅ 次のアクションがあるか？
    │        ✅ 未解決の問いがあるか？
    │        ✅ ペルソナ記事と比べて深さ・質は足りているか？
    │      出力: スコア + 改善点
    │         ↓
    │    Material Updater（エージェント）
    │      修正: dev_simulation_log.md
    │      ※ ログの修正はsim_directorに検証させる（整合性維持）
    │         ↓
    │    停滞(±0.5 × 3回) or 5回 → 素材確定
    │
    ▼
[Phase 3: 記事の生成 + 改善] ───────────────────────────────
    │
    │  [Writer]（エージェント）
    │    読む:
    │      materials/fixed/*（固定素材5つ）
    │      materials/dev_simulation_log.md（体験ストーリー）
    │      style_guide.md（文体ルール）
    │      anti_patterns.md（失敗パターン）
    │    + config: article_purpose / reader_takeaway / system_role
    │    ※ メタファー⑫はWriterがこの段階で考える
    │
    │  [記事改善ループ]（最大10回）
    │
    │    Reviewer（エージェント）
    │      読む: 記事 + ペルソナ記事5本（11本からランダムサンプリング）
    │      フォーカス: 文体・構成・リズム・読者体験のみ
    │        - メタファーの良し悪し
    │        - 文の長さのバリエーション
    │        - 口語の自然さ
    │        - 冒頭の引き込み
    │        - 全体の読みやすさ
    │      ※ 素材の内容（何を書くか）には触れない
    │      出力: スコア + 改善点
    │         ↓
    │    Style Guide Updater（エージェント）
    │      修正: style_guide.md + anti_patterns.md
    │      ※ 書き方のルールだけを更新
    │         ↓
    │    Consolidator（iter 5のみ）
    │      style_guide.md を圧縮
    │         ↓
    │    停滞(±0.5 × 3回) or 10回 → 記事確定
    │
    ▼
  完成記事（iterations/{N}/article.md）
```

---

## 素材の一覧

| # | 素材 | ファイル | 固定/可変 | 生成者 | Phase |
|---|------|---------|----------|-------|-------|
| ① | システム全体像 | materials/fixed/system_overview.md | 固定 | Code Analyzer | 1 |
| ② | 体験ストーリー | materials/dev_simulation_log.md | 可変 | Dev Simulator | 2 |
| ③ | 定量データ | materials/fixed/metrics.md | 固定 | Code Analyzer | 1 |
| ④ | 失敗の詳細 | dev_simulation_log.md内 | 可変 | Dev Simulator | 2 |
| ⑤ | アーキテクチャ図 | materials/fixed/architecture.md | 固定 | Code Analyzer | 1 |
| ⑥ | コード・設定 | materials/fixed/code_examples.md | 固定 | Code Analyzer | 1 |
| ⑦ | トレンド接続 | dev_simulation_log.md内 | 可変 | Dev Simulator(Human役) | 2 |
| ⑧ | 比較・検証 | materials/fixed/comparisons.md | 固定 | Code Analyzer | 1 |
| ⑨ | 読者の痛み | dev_simulation_log.md内 | 可変 | Dev Simulator(Director経由) | 2 |
| ⑩ | 次のアクション | dev_simulation_log.md内 | 可変 | Dev Simulator | 2 |
| ⑪ | 未解決の問い | dev_simulation_log.md内 | 可変 | Dev Simulator | 2 |
| ⑫ | メタファー | 記事内で生成 | Phase 3 | Writer | 3 |

---

## エージェント一覧（12体）

| # | エージェント | Phase | 役割 |
|---|------------|-------|------|
| 1 | **Trend Searcher** | 0 | トレンド・痛みをリアルタイム検索。knowledge/に蓄積 |
| 2 | **Code Analyzer** | 1 | ソースから固定素材5つを一括生成 |
| 3 | **sim_human** | 2 | 開発者役。トレンド知識で仮説を立てる |
| 4 | **sim_claude** | 2 | アシスタント役。一般知識で応答 |
| 5 | **sim_director** | 2 | 審判。読者の痛みで課題設定。評価基準は持たない |
| 6 | **dev_simulator** | 2 | 3体のラウンド制御 |
| 7 | **Material Reviewer** | 2 | 体験ストーリーを12素材基準+ペルソナ比較+独自検索で評価 |
| 8 | **Material Updater** | 2 | 体験ストーリーを改善（sim_director検証付き） |
| 9 | **Writer** | 3 | 全素材から記事生成。メタファーもここで |
| 10 | **Reviewer** | 3 | 文体・構成・リズム・読者体験に特化して評価 |
| 11 | **Style Guide Updater** | 3 | 書き方ルールだけを更新 |
| 12 | **Consolidator** | 3 | ガイド圧縮 |

---

## 知識DB（蓄積型）

```
knowledge/
├── trends.md           # 技術トレンド（追記式）
├── reader_pains.md     # 読者の痛み（追記式）
└── search_cache/       # 検索結果キャッシュ
    └── {query_hash}_{date}.json

蓄積フロー:
  記事1作成時: Trend Searcherが検索 → knowledge/に追記
  記事2作成時: 前回の蓄積 + 新規検索 → さらに追記
  記事N作成時: DBが育っている → 検索量が減り、精度が上がる

キャッシュ（orchestrator.pyで実装）:
  同一クエリが7日以内にあればスキップ
  7日超なら再検索
```

---

## 検索先メディア

| メディア | 方法 | 言語 | 取得するもの |
|---------|------|------|------------|
| Zenn | API | 日本語 | いいね数上位。トレンド+痛み |
| Qiita | API | 日本語 | ストック数上位。トレンド+痛み |
| Anthropic Blog | Playwright | 英語 | 公式見解、ベストプラクティス |
| OpenAI Blog | Playwright | 英語 | 公式情報 |
| Hacker News | API | 英語 | 海外トレンド、議論 |

APIがあるメディアはAPI優先（安定・高速）。ないメディアはPlaywright。

---

## orchestrator.py のコマンド

```bash
# Phase 0: 知識の準備
python orchestrator.py search-trends

# Phase 1: 固定素材
python orchestrator.py analyze-code

# Phase 2: 体験ストーリー
python orchestrator.py simulate
python orchestrator.py after-simulate
python orchestrator.py review-materials
python orchestrator.py after-material-review <score>
python orchestrator.py after-material-update

# Phase 3: 記事生成
python orchestrator.py start-iteration
python orchestrator.py after-write
python orchestrator.py after-review <score>
python orchestrator.py after-update

# ユーティリティ
python orchestrator.py init --source "file1.md" "file2.md"
python orchestrator.py status
```

---

## データアクセス層（BigQuery移行を前提）

```
knowledge_store.py
  - 知識DBへの読み書きを集約
  - 今はファイルI/O（knowledge/*.md, search_cache/*.json）
  - 将来BigQueryクライアントに差し替えるだけ
  - orchestrator.pyやエージェントはこの関数を呼ぶだけで、
    裏がファイルかBigQueryかを知らない

  関数:
    save_trend(keyword, source, content, date)
    save_pain(keyword, source, content, date)
    search_trends(query, limit) -> list
    search_pains(query, limit) -> list
    is_cache_fresh(query_hash, max_age_days=7) -> bool
    save_cache(query_hash, data)
    load_cache(query_hash) -> data
```

---

## 2度目以降のフロー（記事をまたぐとき）

```
python orchestrator.py init --source "新しいシステムのファイル"

リセットされるもの:
  ✅ config.json（新しいお題で上書き）
  ✅ materials/（前の記事の素材を全削除）
  ✅ iterations/（前の記事のイテレーションを全削除）
  ✅ material_reviews/（クリア）
  ✅ anti_patterns.md（リセット）

保持されるもの:
  ✅ knowledge/（蓄積型。記事をまたいで育つ）
  ✅ human-bench/articles/（ペルソナ記事。固定）
  ✅ style_guide.md（書き方の学びを引き継ぐ）
  ✅ persona-elements.md 等の分析資料

style_guide.mdの扱い:
  引き継ぐ。ただし記事固有のルール（「KOLの説明を冒頭に」等）は
  次の記事では不要になるため、initの時点で
  Style Guide Updaterに「前の記事固有のルールを削除」を依頼する。
  共通ルール（「カタログ構成はダメ」「冒頭2段構成」等）は残す。
```

---

## コード vs エージェントの責任分担

| 責務 | 担当 | 理由 |
|------|------|------|
| イテレーション番号管理 | コード | 間違えてはいけない |
| ファイルのコピー・クリア | コード | 機械的操作 |
| スコアの記録・停滞検出 | コード | 条件分岐のみ |
| ベンチマークのランダムサンプリング | コード | ランダム性をコードで保証 |
| 検索キャッシュの重複チェック | コード | ハッシュ比較のみ |
| --- | --- | --- |
| トレンド・痛みの検索と整理 | エージェント | 解釈が必要 |
| ソースコードの分析・素材生成 | エージェント | 理解が必要 |
| 体験ストーリーの生成 | エージェント | 創造的タスク |
| 素材の評価・改善 | エージェント | 判断が必要 |
| 記事の生成・評価・改善 | エージェント | 創造的タスク |
| スコアの読み取り | エージェント | フォーマット揺れ対応 |
