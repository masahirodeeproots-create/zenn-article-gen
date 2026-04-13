# 要件定義書 — Zenn記事自動生成システム v2.0

> 正仕様: ARCHITECTURE.md
> 本文書はARCHITECTURE.mdの設計を実装するための要件を定義する。
> 全コード・全エージェント定義を新規作成する前提。

---

## 1. システム概要

対象システムのソースコードから、Zennのトレンドに入るレベルの技術記事を自動生成する。

2つのPDCAサイクルで構成:
- **素材PDCA**: 何を書くか（内容の質・深さ・面白さ）
- **記事PDCA**: どう書くか（文体・構成・リズム・読者体験）

### 1.1 成功基準
- Reviewerスコア 9.0/10 以上を2連続で達成
- 1記事あたり、手動介入なしでPhase 0→3が完走できる

---

## 2. 機能要件

### FR-01: Phase 0 — 知識の準備（Trend Searcher）

お題に関連するトレンド・読者の痛みをリアルタイム検索し、知識DBに蓄積する。

| ID | 要件 |
|----|------|
| FR-01-1 | お題から日本語・英語の検索キーワードを自動生成する |
| FR-01-2 | orchestrator.pyがキャッシュをチェックし、同一クエリが7日以内ならスキップする |
| FR-01-3 | 5メディアを検索する。API組（Qiita公式API / HN公式API / Zenn非公式JSON）はWebFetchでAPIを叩き人気順で取得。Blog組（OpenAI / Anthropic）はWebFetchでRSS/sitemap→本文取得し、エージェントが関連度で判定。WebSearchはフォールバック |
| FR-01-4 | 日本語メディア→読者の痛み+国内トレンド、英語メディア→グローバルトレンド+公式見解に整理する |
| FR-01-5 | knowledge/trends.md, knowledge/reader_pains.mdに追記保存する（蓄積型） |
| FR-01-6 | knowledge/search_cache/{hash}_{date}.jsonにキャッシュを保存する |
| FR-01-7 | お題用に抽出してmaterials/trend_context.md（3-5個）、materials/reader_pain.md（3-5個）を生成する |

**入力**: config.jsonのtopic + source-material/
**出力**: knowledge/への蓄積 + materials/trend_context.md + materials/reader_pain.md

---

### FR-02: Phase 1 — 固定素材の生成（Code Analyzer）

ソースコードを分析し、事実ベースの固定素材5つを一括生成する。

| ID | 要件 |
|----|------|
| FR-02-1 | source-material/からシステム全体像を抽出→materials/fixed/system_overview.md |
| FR-02-2 | 定量データがあれば抽出→materials/fixed/metrics.md（なければ「該当なし」と明記） |
| FR-02-3 | アーキテクチャを図解→materials/fixed/architecture.md |
| FR-02-4 | 特徴的なコード・設定を抽出→materials/fixed/code_examples.md |
| FR-02-5 | 比較データがあれば抽出→materials/fixed/comparisons.md（なければ「該当なし」と明記） |

**入力**: source-material/
**出力**: materials/fixed/ 配下の5ファイル
**制約**: 1回で確定。レビューループなし。ないものは無理に埋めない。

---

### FR-03: Phase 2 — 体験ストーリーの生成 + 改善

3独立AIによる開発シミュレーションで体験ストーリーを生成し、素材改善ループで品質を上げる。

#### FR-03a: シミュレーション

| ID | 要件 |
|----|------|
| FR-03a-1 | sim_director / sim_human / sim_claude の3体を独立サブエージェントとして呼び出す（1つのAIが3役を演じてはならない） |
| FR-03a-2 | sim_directorは完成形（simulator_source_files）+ 読者の痛み（reader_pain.md）を知っている。読者の痛みから課題を設定してHuman役に体験させる。**評価基準は持たない**（それはMaterial Reviewerの仕事） |
| FR-03a-3 | sim_humanは要件（system_overview.md）+ トレンド知識（trend_context.md）を知っている。トレンド技術の知識を使って課題解決の仮説を立てる。trend_context.mdは参照であり制約ではない |
| FR-03a-4 | sim_claudeは一般的な技術知識のみ。Humanの仮説に応答する |
| FR-03a-5 | 出力はmaterials/dev_simulation_log.mdに統合: ②体験の流れ / ④失敗の詳細 / ⑦トレンド接続 / ⑨読者の痛みポイント / ⑩次のアクション / ⑪未解決の問い |

#### FR-03b: 素材改善ループ（最大5回）

| ID | 要件 |
|----|------|
| FR-03b-1 | Material Reviewerがdev_simulation_log.md + ペルソナ記事**11本全部**を読んで評価する |
| FR-03b-2 | Material Reviewerはお題の周辺キーワードで**独自検索**する（Trend Searcherとは異なるクエリ）。検索結果はknowledge/に**保存しない** |
| FR-03b-3 | 評価基準6項目: (1)読者の痛みに刺さる課題があるか (2)失敗が生々しいか (3)トレンド接続が自然か (4)次のアクションがあるか (5)未解決の問いがあるか (6)ペルソナ記事と比べて深さ・質は足りているか |
| FR-03b-4 | Material Updaterが改善する。ログの修正はsim_directorに検証させる（整合性維持） |
| FR-03b-5 | 停止条件: 直近3回のスコアが±0.5以内（停滞） or 最大5回 |

---

### FR-04: Phase 3 — 記事の生成 + 改善

全素材から記事を生成し、文体・構成・読者体験に特化した改善ループを回す。

| ID | 要件 |
|----|------|
| FR-04-1 | Writerは固定素材5つ + 体験ストーリー + style_guide.md + anti_patterns.md + config（article_purpose / reader_takeaway / system_role）を読んで記事を生成する |
| FR-04-2 | ⑫メタファーはWriterがこの段階で考案する |
| FR-04-3 | Reviewerは記事 + ペルソナ記事**5本**（11本からランダムサンプリング）を読んで評価する。文体・構成・リズム・読者体験**のみ**（素材の内容には触れない） |
| FR-04-4 | Style Guide Updaterが書き方ルールだけを更新する |
| FR-04-5 | iter 5でConsolidatorがstyle_guide.mdを圧縮する（iter 5に到達した場合のみ） |
| FR-04-6 | 停止条件: 2連続 ≥ 9.0/10 での早期終了 / 直近3回のスコアが±0.5以内（停滞） / 最大10回 |

---

### FR-05: オーケストレーション（orchestrator.py）

コードが担う責務は**判断不要な処理だけ**。

| ID | 要件 |
|----|------|
| FR-05-1 | `init --source "file1.md" "file2.md"` — ソースファイル指定。materials/, iterations/, material_reviews/を全削除。anti_patterns.mdをリセット。knowledge/, style_guide.md, human-bench/, persona分析資料は保持。Style Guide Updaterに記事固有ルールの削除を依頼する |
| FR-05-2 | `search-trends` — Phase 0起動。Trend Searcher呼び出し |
| FR-05-3 | `after-search-trends` — materials/trend_context.md, reader_pain.mdの存在確認。次アクション出力 |
| FR-05-4 | `analyze-code` — Phase 1起動。Code Analyzer呼び出し |
| FR-05-5 | `after-analyze-code` — materials/fixed/の5ファイル存在確認。次アクション出力 |
| FR-05-6 | `simulate` — Phase 2シミュレーション起動。Dev Simulator呼び出し |
| FR-05-7 | `after-simulate` — dev_simulation_log.md存在確認。次アクション出力 |
| FR-05-8 | `review-materials` — 素材レビューループ制御。Material Reviewer呼び出し |
| FR-05-9 | `after-material-review <score>` — スコア記録、停滞検出、次アクション判定 |
| FR-05-10 | `after-material-update` — 次の素材レビューへ誘導 |
| FR-05-11 | `start-iteration` — 記事ループ起動。ベンチマーク記事をランダムサンプリング。Writer呼び出し |
| FR-05-12 | `after-write` — article.md存在確認。Reviewer呼び出し |
| FR-05-13 | `after-review <score>` — スコア記録、停滞検出、2連続9.0以上検出、Consolidation判定、次アクション判定 |
| FR-05-14 | `after-update` — 次イテレーションへ誘導 |
| FR-05-15 | `after-consolidate` — Consolidation完了後、Style Guide Updater呼び出しへ誘導 |
| FR-05-16 | `status` — 全フェーズの進捗をJSON出力 |

**コードの責務**: イテレーション番号管理 / ファイルのコピー・クリア / スコアの記録・停滞検出 / ベンチマークのランダムサンプリング / 検索キャッシュの重複チェック
**エージェントの責務**: 検索・分析・生成・評価・改善（判断が必要な全て）

---

### FR-06: 知識DB・データアクセス層（knowledge_store.py）

| ID | 要件 |
|----|------|
| FR-06-1 | save_trend(keyword, source, content, date) — トレンド追記保存 |
| FR-06-2 | save_pain(keyword, source, content, date) — 読者の痛み追記保存 |
| FR-06-3 | search_trends(query, limit) -> list — キーワード検索 |
| FR-06-4 | search_pains(query, limit) -> list — キーワード検索 |
| FR-06-5 | is_cache_fresh(query_hash, max_age_days=7) -> bool — キャッシュ有効期限判定 |
| FR-06-6 | save_cache(query_hash, data) — キャッシュ保存 |
| FR-06-7 | load_cache(query_hash) -> data — キャッシュ読み込み |
| FR-06-8 | init_knowledge_dir() — ディレクトリ初期化（冪等） |
| FR-06-9 | 今はファイルI/O。将来BigQueryクライアントに差し替えるだけで動く設計 |

※ is_cache_fresh / save_cache / load_cache は ARCHITECTURE.md に従い引数を `query_hash`（ハッシュ済み文字列）とする。ハッシュ化は呼び出し元の責務。

---

### FR-07: 記事間の引き継ぎ（initでのリセット制御）

| リセットするもの | 保持するもの |
|-----------------|-------------|
| config.json（新しいお題で上書き） | knowledge/（蓄積型。記事をまたいで育つ） |
| materials/（全削除） | human-bench/articles/（ペルソナ記事11本。固定） |
| iterations/（全削除） | style_guide.md（共通ルールを引き継ぐ） |
| material_reviews/（クリア） | persona-analysis.md, persona-elements.md 等の分析資料 |
| anti_patterns.md（リセット） | benchmark-criteria.md |

style_guide.mdの扱い:
- 共通ルール（「カタログ構成はダメ」「冒頭2段構成」等）は残す
- 記事固有ルール（「KOLの説明を冒頭に」等）はinit時にStyle Guide Updaterが削除する

---

## 3. 非機能要件

| ID | カテゴリ | 要件 |
|----|---------|------|
| NFR-01 | コスト | 各Phase・各エージェント呼び出しのトークン消費をログに出力する |
| NFR-02 | 冪等性 | 各コマンドは途中で失敗しても再実行で復旧可能とする |
| NFR-03 | 可観測性 | `status`コマンドで全フェーズの入出力ファイル・スコア・Phase状態を一覧表示する |
| NFR-04 | 拡張性 | knowledge_store.pyの関数シグネチャを変えずにBigQuery移行可能とする |
| NFR-05 | 再現性 | ベンチマークサンプリングのseedをconfig.jsonに記録する |

---

## 4. エージェント一覧（12体）

ARCHITECTURE.md準拠。全て新規作成。

| # | エージェント | ファイル | Phase | 役割 |
|---|------------|---------|-------|------|
| 1 | Trend Searcher | trend_searcher.md | 0 | トレンド・痛みをリアルタイム検索。knowledge/に蓄積 |
| 2 | Code Analyzer | code_analyzer.md | 1 | ソースから固定素材5つを一括生成 |
| 3 | sim_human | sim_human.md | 2 | 開発者役。トレンド知識で仮説を立てる |
| 4 | sim_claude | sim_claude.md | 2 | アシスタント役。一般知識で応答 |
| 5 | sim_director | sim_director.md | 2 | 審判。読者の痛みで課題設定。**評価基準は持たない** |
| 6 | Dev Simulator | dev_simulator.md | 2 | 3体のラウンド制御 |
| 7 | Material Reviewer | material_reviewer.md | 2 | 体験ストーリーを6基準+ペルソナ比較+独自検索で評価 |
| 8 | Material Updater | material_updater.md | 2 | 体験ストーリーを改善（sim_director検証付き） |
| 9 | Writer | writer.md | 3 | 全素材から記事生成。メタファーもここで |
| 10 | Reviewer | reviewer.md | 3 | 文体・構成・リズム・読者体験に特化して評価 |
| 11 | Style Guide Updater | style_guide_updater.md | 3 | 書き方ルールだけを更新 |
| 12 | Consolidator | consolidator.md | 3 | ガイド圧縮 |

---

## 5. 素材一覧（12種）

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

## 6. フォルダ構成

ARCHITECTURE.md準拠。

```
/tmp/zenn-article-gen/
│
├── orchestrator.py
├── knowledge_store.py
├── config.json
│
├── source-material/
│   └── (対象システムのファイル)
│
├── knowledge/
│   ├── trends.md
│   ├── reader_pains.md
│   └── search_cache/
│       └── {query_hash}_{date}.json
│
├── materials/
│   ├── fixed/
│   │   ├── system_overview.md
│   │   ├── metrics.md
│   │   ├── architecture.md
│   │   ├── code_examples.md
│   │   └── comparisons.md
│   ├── trend_context.md
│   ├── reader_pain.md
│   └── dev_simulation_log.md
│
├── human-bench/articles/          # ペルソナ記事11本（固定）
│
├── material_reviews/
│
├── iterations/
│   └── {N}/
│       ├── article.md
│       ├── review.md
│       └── changelog.md
│
├── style_guide.md
├── anti_patterns.md
│
├── persona-analysis.md
├── persona-elements.md
├── benchmark-criteria.md
│
└── .claude/agents/                # エージェント定義12体
    ├── trend_searcher.md
    ├── code_analyzer.md
    ├── dev_simulator.md
    ├── sim_human.md
    ├── sim_claude.md
    ├── sim_director.md
    ├── material_reviewer.md
    ├── material_updater.md
    ├── writer.md
    ├── reviewer.md
    ├── style_guide_updater.md
    └── consolidator.md
```

---

## 7. コマンドフロー

```
python orchestrator.py init --source "file1.md" "file2.md"
  ↓ (initがCode Analyzerを呼び出し → topic + 固定素材5つ生成)
python orchestrator.py analyze-code           # Phase 1（topicが先に必要）
python orchestrator.py after-analyze-code
  ↓
python orchestrator.py search-trends          # Phase 0（topicを使って検索）
python orchestrator.py after-search-trends
  ↓
python orchestrator.py simulate               # Phase 2
python orchestrator.py after-simulate
  ↓
python orchestrator.py review-materials       # Phase 2 素材改善ループ
python orchestrator.py after-material-review <score>
python orchestrator.py after-material-update
  ↓ (停滞 or 5回で終了)
python orchestrator.py start-iteration        # Phase 3 記事改善ループ
python orchestrator.py after-write
python orchestrator.py after-review <score>
python orchestrator.py after-update
  ↓ (2連続9.0以上 or 停滞 or 10回で終了)
完成: iterations/{N}/article.md
```
