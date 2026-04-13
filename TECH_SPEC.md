# 技術仕様書 — Zenn記事自動生成システム v2.0

> 正仕様: ARCHITECTURE.md
> 全コード・全エージェント定義を新規作成する前提。

---

## 1. 成果物一覧

| ファイル | 種別 | 説明 |
|---------|------|------|
| orchestrator.py | Python | フロー制御。判断不要な処理のみ |
| knowledge_store.py | Python | 知識DBへの読み書き。ファイルI/O実装 |
| config.json | JSON | 記事ごとの設定・状態管理 |
| .claude/agents/*.md | Markdown × 12 | エージェント定義 |
| CLAUDE.md | Markdown | Claude Code向けガイド |

---

## 2. knowledge_store.py

### 2.1 設計方針
- 知識DBへの全操作をこのモジュールに集約
- 今はファイルI/O。関数シグネチャはBigQuery移行を見据える
- orchestrator.pyやエージェントはこの関数を呼ぶだけで、裏がファイルかBigQueryかを知らない

### 2.2 関数仕様

```python
"""knowledge_store.py — 知識DBデータアクセス層"""

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path("/tmp/zenn-article-gen")
KNOWLEDGE_DIR = BASE_DIR / "knowledge"
CACHE_DIR = KNOWLEDGE_DIR / "search_cache"


def init_knowledge_dir():
    """知識DBディレクトリを初期化（冪等）"""
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    for fname in ["trends.md", "reader_pains.md"]:
        path = KNOWLEDGE_DIR / fname
        if not path.exists():
            path.write_text(f"# {fname.replace('.md','').replace('_',' ').title()}\n\n")


def save_trend(keyword: str, source: str, content: str, date: str):
    """トレンド情報を追記保存

    Args:
        keyword: 検索キーワード
        source: 情報源（"zenn" / "qiita" / "hn" / "anthropic_blog" / "openai_blog"）
        content: トレンド内容
        date: 取得日（ISO 8601: "2026-04-13"）
    """
    path = KNOWLEDGE_DIR / "trends.md"
    entry = f"\n## [{date}] {keyword} ({source})\n\n{content}\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(entry)


def save_pain(keyword: str, source: str, content: str, date: str):
    """読者の痛み情報を追記保存。シグネチャはsave_trendと同一。"""
    path = KNOWLEDGE_DIR / "reader_pains.md"
    entry = f"\n## [{date}] {keyword} ({source})\n\n{content}\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(entry)


def search_trends(query: str, limit: int = 10) -> list:
    """トレンドをキーワード検索。セクション単位でマッチ。"""
    return _search_file("trends.md", query, limit)


def search_pains(query: str, limit: int = 10) -> list:
    """読者の痛みをキーワード検索。"""
    return _search_file("reader_pains.md", query, limit)


def _search_file(filename: str, query: str, limit: int) -> list:
    """知識ファイルをセクション単位で検索（内部関数）"""
    path = KNOWLEDGE_DIR / filename
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    sections = text.split("\n## ")
    results = []
    q = query.lower()
    for section in sections[1:]:
        if q in section.lower():
            header = section.split("\n")[0]
            body = "\n".join(section.split("\n")[1:]).strip()
            results.append({"header": header, "content": body})
            if len(results) >= limit:
                break
    return results


def query_hash(query: str) -> str:
    """クエリからハッシュを生成。呼び出し元がこれを使ってからcache関数に渡す。"""
    return hashlib.md5(query.encode()).hexdigest()[:12]


def is_cache_fresh(qhash: str, max_age_days: int = 7) -> bool:
    """キャッシュが有効期限内か判定。

    ファイル名: {query_hash}_{YYYY-MM-DD}.json
    """
    cutoff = datetime.now() - timedelta(days=max_age_days)
    for f in CACHE_DIR.glob(f"{qhash}_*.json"):
        # ハッシュは英数字12文字でアンダースコアを含まないため split("_",1) で安全に分離
        date_str = f.stem.split("_", 1)[1]
        try:
            if datetime.strptime(date_str, "%Y-%m-%d") >= cutoff:
                return True
        except ValueError:
            continue
    return False


def save_cache(qhash: str, data: dict):
    """検索結果をキャッシュに保存。"""
    date_str = datetime.now().strftime("%Y-%m-%d")
    path = CACHE_DIR / f"{qhash}_{date_str}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_cache(qhash: str) -> dict | None:
    """最新のキャッシュを読み込み。なければNone。"""
    files = sorted(CACHE_DIR.glob(f"{qhash}_*.json"), reverse=True)
    if not files:
        return None
    with open(files[0], encoding="utf-8") as f:
        return json.load(f)
```

**ARCHITECTURE.mdとの対応**:
- `query_hash()` をpublic関数として公開。呼び出し元がハッシュ化してから `is_cache_fresh(qhash)`, `save_cache(qhash, data)`, `load_cache(qhash)` に渡す
- これはARCHITECTURE.md「`is_cache_fresh(query_hash, max_age_days=7)`」の設計に準拠

---

## 3. config.json

### 3.1 全フィールド定義

```json
{
  // --- 記事設定（initで生成） ---
  "topic": "",
  "article_purpose": "",
  "reader_takeaway": "",
  "system_role": "",
  "simulator_source_files": [],

  // --- Phase状態 ---
  "current_phase": "init",
  "status": "running",

  // --- ベンチマーク ---
  "benchmark_dir": "human-bench/articles",
  "benchmark_sample_size": 5,
  "benchmark_seed": null,
  "current_benchmark_articles": [],

  // --- 素材改善ループ ---
  "material_max_iterations": 5,
  "material_stagnation_window": 3,
  "material_stagnation_tolerance": 0.5,
  "material_current_iteration": 0,
  "material_scores": [],

  // --- 記事改善ループ ---
  "max_iterations": 10,
  "consolidation_at_iteration": 5,
  "stagnation_window": 3,
  "stagnation_tolerance": 0.5,
  "current_iteration": 0,
  "scores": [],
  "last_score": null,
  "consecutive_above_threshold": 0,
  "score_threshold": 9.0,

  // --- ファイルパス ---
  "dev_simulation_log": "materials/dev_simulation_log.md",
  "anti_patterns_log": "anti_patterns.md",

  // --- シミュレーション ---
  "simulator_score_threshold": 95
}
```

### 3.2 current_phaseの状態遷移

```
init
  → search-trends → trends-ready
  → analyze-code → code-analyzed
  → simulate → ready
  → review-materials → (ループ)
  → write → review → update → next → write ...
  → consolidate → update → next
  → complete
```

---

## 4. orchestrator.py

### 4.1 設計方針
- 全コマンドは `ACTION: CALL_XXX` または `ACTION: Run 'python orchestrator.py xxx'` を出力する
- エージェントに渡す情報は `print_agent_context()` でJSON出力する
- コードが判断するのは: イテレーション番号 / ファイル存在確認 / スコア記録・停滞検出 / サンプリング / キャッシュチェック

### 4.2 コマンド仕様

#### `init --source <files...>`

```python
def cmd_init(config, source_files):
    # 1. ソースファイル存在確認
    # 2. materials/ を全削除して再作成（fixed/ 含む）
    # 3. iterations/ を全削除
    # 4. material_reviews/ をクリア
    # 5. anti_patterns.md をリセット
    # 6. knowledge_store.init_knowledge_dir()（保持。なければ作成）
    # 7. config をリセット（topic等は空。後でCode Analyzerが生成）
    # 8. ACTION: CALL_STYLE_GUIDE_UPDATER（記事固有ルール削除）
    # 9. ACTION: CALL_CODE_ANALYZER（config.jsonフィールド + 固定素材5つ生成）
```

**注意**: Code AnalyzerがPhase 1でconfig.jsonのtopic / article_purpose / reader_takeaway / system_roleも生成する。initコマンド自体はフィールドを空にするだけ。

#### `search-trends`

```python
def cmd_search_trends(config):
    # 1. config.topic が空でないことを確認
    # 2. current_phase = "search-trends"
    # 3. ACTION: CALL_TREND_SEARCHER
    # 出力コンテキスト:
    #   topic, knowledge_dir, trend_output, pain_output
```

#### `after-search-trends`

```python
def cmd_after_search_trends(config):
    # 1. materials/trend_context.md, materials/reader_pain.md 存在確認
    # 2. current_phase = "trends-ready"
    # 3. ACTION: Run 'python orchestrator.py simulate'
```

※ analyze-code → search-trends → simulate の順で進む。fixed素材もtrend/painも揃った状態でシミュレーションに入る。

#### `analyze-code`

```python
def cmd_analyze_code(config):
    # 1. current_phase = "analyze-code"
    # 2. ACTION: CALL_CODE_ANALYZER
    # 出力コンテキスト:
    #   source_files, output_dir("materials/fixed/"),
    #   outputs(5ファイル名)
```

#### `after-analyze-code`

```python
def cmd_after_analyze_code(config):
    # 1. materials/fixed/ の5ファイル存在確認
    # 2. config.jsonのtopic等が生成されていることを確認
    # 3. current_phase = "code-analyzed"
    # 4. ACTION: Run 'python orchestrator.py search-trends'
```

**フロー順序**: ARCHITECTURE.mdに従いPhase 1(analyze-code) → Phase 0(search-trends)の順で実行する。理由: Code Analyzerがtopicをconfigにセットしないと、Trend Searcherが検索キーワードを生成できないため。initではCode Analyzerを呼び出してtopic + 固定素材を生成し、その後search-trendsに進む。

```
init → (CALL_CODE_ANALYZER) → analyze-code完了 → search-trends → after-search-trends → simulate → ...
```

#### `simulate`

```python
def cmd_simulate(config):
    # 1. 前回成果物クリア（iterations/, material_reviews/, dev_simulation_log）
    # 2. ループカウンタリセット
    # 3. current_phase = "simulate"
    # 4. ACTION: CALL_DEV_SIMULATOR
    # 出力コンテキスト:
    #   simulator_source_files, dev_simulation_log_path,
    #   simulator_score_threshold,
    #   system_overview_path("materials/fixed/system_overview.md"),
    #   trend_context_path("materials/trend_context.md"),
    #   reader_pain_path("materials/reader_pain.md")
```

#### `after-simulate`

```python
def cmd_after_simulate(config):
    # 1. dev_simulation_log.md 存在確認
    # 2. ループカウンタリセット
    # 3. current_phase = "ready"
    # 4. ACTION: Run 'python orchestrator.py review-materials'
```

#### `review-materials`

```python
def cmd_review_materials(config):
    # 1. material_current_iteration += 1
    # 2. 最大回数チェック → 超えたらstart-iterationへ誘導
    # 3. current_phase = "review-materials"
    # 4. ACTION: CALL_MATERIAL_REVIEWER
    # 出力コンテキスト:
    #   dev_simulation_log_path,
    #   material_review_output_path("material_reviews/review_{n}.md"),
    #   system_overview_path
```

#### `after-material-review <score>`

```python
def cmd_after_material_review(config, score):
    # 1. スコアをmaterial_scoresに追記
    # 2. 停滞検出: 直近3回が±0.5以内 → start-iterationへ誘導
    # 3. それ以外 → ACTION: CALL_MATERIAL_UPDATER
    # 出力コンテキスト:
    #   dev_simulation_log_path,
    #   material_review_path("material_reviews/review_{n}.md"),
    #   simulator_source_files
```

#### `after-material-update`

```python
def cmd_after_material_update(config):
    # ACTION: Run 'python orchestrator.py review-materials'
```

#### `start-iteration`

```python
def cmd_start_iteration(config):
    # 1. complete済みなら終了
    # 2. max_iterations超えたら終了
    # 3. ベンチマークサンプリング（seed記録）
    # 4. イテレーションディレクトリ作成 + style_guide.mdアーカイブ
    # 5. current_iteration += 1
    # 6. current_phase = "write"
    # 7. ACTION: CALL_WRITER
    # 出力コンテキスト:
    #   article_output_path, style_guide_path, anti_patterns_log_path,
    #   dev_simulation_log_path, article_purpose, reader_takeaway, system_role,
    #   fixed_materials(5ファイルのパスリスト)
```

#### `after-write`

```python
def cmd_after_write(config):
    # 1. article.md 存在確認
    # 2. current_phase = "review"
    # 3. ACTION: CALL_REVIEWER
    # 出力コンテキスト:
    #   article_path, review_output_path, benchmark_articles
```

#### `after-review <score>`

```python
def cmd_after_review(config, score):
    # 1. スコア記録
    # 2. 2連続 ≥ 9.0 チェック → complete
    # 3. 停滞検出: 直近3回が±0.5以内 → complete
    # 4. max_iterations到達 → complete
    # 5. iter == consolidation_at_iteration → CALL_CONSOLIDATION
    # 6. それ以外 → CALL_STYLE_GUIDE_UPDATER
```

#### `after-update`

```python
def cmd_after_update(config):
    # current_phase = "next"
    # ACTION: Run 'python orchestrator.py start-iteration'
```

#### `after-consolidate`

```python
def cmd_after_consolidate(config):
    # current_phase = "update"
    # ACTION: CALL_STYLE_GUIDE_UPDATER（consolidation後なので既存ルールの精緻化優先）
```

#### `status`

```python
def cmd_status(config):
    # config.json全体をJSON出力
```

---

## 5. エージェント定義（12体）

全て `.claude/agents/` 配下に新規作成。

### 5.1 trend_searcher.md

```markdown
# Trend Searcher Agent

お題に関連するトレンド・読者の痛みをリアルタイム検索し、知識DBに蓄積する。

## 入力
- config.jsonの `topic`
- knowledge/ の既存蓄積（重複防止のため参照）

## プロセス

### Step 1: キーワード生成
topicから検索キーワードを生成。
- 日本語: 3-5個（具体的な技術名 + ユースケース）
- 英語: 3-5個

### Step 2: メディアごとに検索（WebFetchで実行）

### API組（人気順で直接取得可能）
| メディア | 収集方法 | WebFetchのURL例 | 人気指標 |
|---------|---------|----------------|---------|
| Qiita | 公式API v2 | `https://qiita.com/api/v2/items?query={keyword}&sort=stock&per_page=20` | likes/stocks |
| HN | 公式API | `https://hn.algolia.com/api/v1/search?query={keyword}&tags=story&hitsPerPage=20` | score |
| Zenn | 非公式JSON | `https://zenn.dev/api/articles?q={keyword}&order=liked_count` | liked/bookmarks |

### Blog組（人気指標なし。関連度でエージェントが判定）
| メディア | 収集手順 | 備考 |
|---------|---------|------|
| OpenAI | WebFetchでRSS/sitemap取得→記事URL抽出→WebFetchで本文取得 | 人気度は自前判定 |
| Anthropic | WebFetchでsitemap取得→記事URL抽出→WebFetchで本文取得 | 人気度は自前判定 |

### フォールバック
上記で取得できなかった場合のみWebSearchを使用。

### Step 3: 整理
- 日本語メディア → 読者の痛み + 国内トレンド
- 英語メディア → グローバルトレンド + 公式見解

### Step 4: 保存
- knowledge/trends.md に追記
- knowledge/reader_pains.md に追記
- knowledge/search_cache/ にキャッシュ

### Step 5: お題用に抽出
- materials/trend_context.md（最も関連性の高い3-5個）
- materials/reader_pain.md（最も切実な3-5個）

## 出力フォーマット

### materials/trend_context.md
# Trend Context — {topic}
## 1. {トレンド名}
- 出典: {source}
- 概要: {1-2文}
- 記事との接続: {なぜこのトレンドがこの記事に関係するか}

### materials/reader_pain.md
# Reader Pain Points — {topic}
## 1. {痛みの名前}
- 出典: {source}
- 詳細: {どういう場面で何に困っているか}
- 記事での活用: {この痛みに対してこの記事がどう応えられるか}

## 制約
- APIレート制限時は取得できた分だけで進める（Qiita: 認証なし60req/h）
- Blog組のsitemap/RSS取得に失敗した場合はWebSearchにフォールバック
- WebSearchでも取れなければそのメディアはスキップ
- knowledge/に同じ情報がある場合は重複追記しない
```

---

### 5.2 code_analyzer.md

```markdown
# Code Analyzer Agent

ソースコードを分析し、事実ベースの固定素材5つを一括生成する。
加えて、config.jsonの記事関連フィールドを生成する。

## 入力
- source-material/ 配下の全ファイル

## 責務1: config.jsonフィールド生成

以下の4フィールドを生成してconfig.jsonに書き込む:
- topic: 記事タイトル（読者が開きたくなるもの）
- article_purpose: 試行錯誤を通じて読者が学べること
- reader_takeaway: 読者が持ち帰れる具体的な学び
- system_role: このシステムの記事内での立ち位置

## 責務2: 固定素材5ファイル生成

### ① materials/fixed/system_overview.md
# System Overview
## このシステムは何か
[1段落。技術者でない人にも伝わるレベル]
## 誰のためのシステムか
[1文]
## 何を入力して何を出力するか
[入力→出力を1文]
## なぜ作ったのか
[1段落。手作業の何が辛かったか]
## 専門用語の説明
[このシステム固有の用語]
## 読者が知るべき前提
[箇条書き3-5個]

### ③ materials/fixed/metrics.md
定量データ（処理時間・精度・コスト等）。
なければ「## 該当なし」+ 理由1文。

### ⑤ materials/fixed/architecture.md
ASCII図 + コンポーネント説明 + データフロー。

### ⑥ materials/fixed/code_examples.md
特徴的なコード・設定のスニペット。ソースから直接引用。

### ⑧ materials/fixed/comparisons.md
比較データ（代替手段との違い等）。
なければ「## 該当なし」+ 理由1文。

## 制約
- 事実ベースのみ。推測・解釈を加えない
- 1回で確定。レビューループなし
- ないものは「該当なし」（無理に埋めない）
- コードスニペットはソースから直接引用（改変しない）
```

---

### 5.3 dev_simulator.md

```markdown
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
以下が統合される: ②体験 / ④失敗 / ⑦トレンド接続 / ⑨痛み / ⑩次のアクション / ⑪未解決の問い

## ログの抽象度
✅ 設計原則、発見プロセス、他ドメインとの類推、簡易ASCII図、迷い、素朴な疑問
❌ ファイル名、Phase番号、コードスニペット、JSON構造、エラーメッセージ

## Directorの出力はログに含めない

## 停止条件
- Directorスコア ≥ 95/100 → 停止
- または 10ラウンド → 停止
```

---

### 5.4 sim_human.md

```markdown
# Simulation Human Agent

開発シミュレーションにおける「人間（設計者）」役。

## あなたは誰か
AIエージェントを使ったシステムを初めて本格的に作るエンジニア。読者と同じ目線。

## 知っていること
- 作りたいシステムの要件（materials/fixed/system_overview.md から理解）
- 技術トレンドの知識（materials/trend_context.md から理解）
  ※ trend_context.mdは参照であり制約ではない。自身の一般知識を自由に使ってよい
- ソフトウェア開発の一般知識
- 前のラウンドまでの会話内容
- Directorから渡された「設計の問い」

## 知らないこと（絶対に使わない）
- 完成形の設計（source-materialの具体的な設計判断）
- ファイル名やJSONスキーマ

## 振る舞い
- 設計原則を考えながら話す（実装詳細ではなく「なぜ」を問う）
- Directorの問いを「自分で思いついた疑問」として自然に出す
- 他ドメインとの類推（「組織論と同じだ」「APIの契約と似てる」）
- 素朴な疑問（「なんでそんなに分ける必要あるの？」）
- 迷いを素直に出す（「正直どっちがいいかわからない」）
- 苛立ちや驚き（「え、そんなことで壊れるの？」）
- トレンド知識を使って仮説を立てる（「最近のAgent frameworkだと〜」）
  ※ 無理にねじ込まない。自然に出るときだけ

## 会話の抽象度
✅ 設計原則、他ドメインとの類推、簡易ASCII図
❌ ファイル名、Phase番号、コードスニペット、JSON構造

## 出力
1〜5文の自然な口語体。設計原則や仮説を含む。
```

---

### 5.5 sim_claude.md

```markdown
# Simulation Claude Agent

開発シミュレーションにおける「Claude（設計アシスタント）」役。

## あなたは誰か
一般的な技術知識を持つAIアシスタント。対象システムの完成形は知らない。

## 知っていること
- 一般的な技術知識（マイクロサービス、API設計、デザインパターン等）
- 前のラウンドまでの会話内容
- Human役の最新発言

## 知らないこと
- 完成形の設計
- 具体的な実装詳細

## 振る舞い
- Human役の仮説に応答する
- 設計パターンを原則レベルで提案する
- 長所と短所を公平に説明する
- 一般的なベストプラクティスや類似事例を紹介する

## 会話の抽象度
✅ 設計原則、パターン名、他ドメインとの類推
❌ ファイル名、Phase番号、コードスニペット、JSON構造

## 出力
1〜5文。設計パターンの提案（原則レベル）。
```

---

### 5.6 sim_director.md

```markdown
# Simulation Director Agent

開発シミュレーションの裏方。完成形の設計思想を知っている唯一のエージェント。

## 役割
Human役とClaude役が到達した設計思想を完成形と比較し、次にHuman役が考えるべき「設計の問い」を生成する。
読者の痛みから課題を設定してHuman役に体験させる。
**ただし12素材の評価基準での採点はしない（それはMaterial Reviewerの仕事）。**

## 知っていること
- 完成形の設計思想（simulator_source_files を読んで理解）
- 読者の痛みポイント（materials/reader_pain.md から理解）
  ※ reader_pain.mdは参照であり制約ではない。該当する痛みがなければ完成形から想像できる課題でOK
- 前ラウンドまでの会話ログ

## プロセス
1. 完成形の設計思想を理解する（初回のみ）
2. 会話ログを読む
3. Human+Claudeが到達した現在の設計原則を把握する
4. 完成形と比較して完成度スコア（0〜100）をつける
5. 設計原則として最も欠けている部分を特定する
6. それを「設計の問い」として出力する

## 「設計の問い」のルール
❌ 現象・バグとして伝えてはいけない
❌ 実装詳細を含めてはいけない
✅ 設計原則レベルの問い

例:
- 「エージェントが増えたとき、誰が何を知るべきかの境界をどう設計する？」
- 「前段の品質が後段の前提になるとき、どこでゲートを置く？」

## 出力フォーマット
[Director Internal — ログには含めない]
完成度: XX/100
現在の設計原則: [要約]
完成形との最大差分: [欠けている原則]
次の設計の問い: [原則レベルの問い]

## 停止条件
完成度 ≥ 95/100 → STOP

## 重要
- Directorの出力はdev_simulation_log.mdに含めない
- ファイル名、Phase番号、コード、JSONは一切使わない
```

---

### 5.7 material_reviewer.md

```markdown
# Material Reviewer Agent

体験ストーリーの品質を評価するエージェント。

## 読むもの
1. materials/fixed/system_overview.md — システムの全体像
2. materials/dev_simulation_log.md — 体験ストーリー
3. human-bench/articles/ — ペルソナ記事**11本全部**

## 独自検索
お題の周辺キーワードで別角度から検索する。
Trend Searcherとは異なるクエリを使い、別視点を持つため。
**検索結果はknowledge/に保存しない。**

## 評価基準（6項目）
1. ✅ 読者の痛みに刺さる課題があるか？
2. ✅ 失敗が生々しいか？
3. ✅ トレンド接続が自然か？
4. ✅ 次のアクションがあるか？
5. ✅ 未解決の問いがあるか？
6. ✅ ペルソナ記事と比べて深さ・質は足りているか？

## 出力フォーマット
# Material Review

## 率直な感想
[素材を読んだ第一印象]

## ペルソナ記事との比較
[11本と比べてどこが負けているか、具体的に]

## 改善点
[1-3個。具体的に何をどう変えるべきか]

## Material Score
- Overall: X/10

**重要**: `Overall: X/10` の形式を必ず守ること。
```

---

### 5.8 material_updater.md

```markdown
# Material Updater Agent

素材Reviewerの指摘に基づいて、体験ストーリーを改善する。

## 読むもの
1. materials/dev_simulation_log.md — 改善対象
2. material_reviews/review_{n}.md — Reviewerの指摘
3. simulator_source_files — 事実確認用

## プロセス
1. Reviewerの指摘を読む
2. dev_simulation_log.md を改善する
3. 改善したログの整合性をsim_directorに検証させる
   （ログの修正が完成形と矛盾していないか確認）

## 制約
- materials/fixed/ 配下のファイルは修正しない（固定素材）
- 改善はdev_simulation_log.mdのみ
```

---

### 5.9 writer.md

```markdown
# Writer Agent

全素材から日本語の技術記事を生成する。人間が書いたものと区別できないレベルを目指す。

## 記事の目的（最重要）
オーケストレーターから渡される以下の3つで方向性を決める:
- article_purpose: この記事が語るべき主題
- reader_takeaway: 読者が持ち帰れるもの
- system_role: このシステムの記事内での立ち位置

**記事の主役はシステムの説明ではなく、article_purposeに書かれた主題。**

## インプット
1. 記事の目的: article_purpose, reader_takeaway, system_role
2. 固定素材:
   - materials/fixed/system_overview.md（読者への前提説明）
   - materials/fixed/metrics.md（定量データ）
   - materials/fixed/architecture.md（構成図）
   - materials/fixed/code_examples.md（コード実例）
   - materials/fixed/comparisons.md（比較結果）
3. 体験ストーリー: materials/dev_simulation_log.md
4. スタイルガイド: style_guide.md
5. アンチパターンログ: anti_patterns.md

## プロセス
1. article_purpose, reader_takeaway, system_roleを確認
2. system_overview.mdを読み、冒頭で読者に前提を説明する情報を把握
3. style_guide.mdを熟読
4. anti_patterns.mdを読み、過去の失敗パターンを意識的に避ける
5. dev_simulation_log.mdを読み、体験を把握
6. ⑫メタファーを考案する
7. reader_takeawayを達成する構成を考える（ログの順番に従わなくてよい）
8. 記事を生成する
9. 指定パスに保存する

## 絶対ルール
### やること
- 冒頭で「何のシステムの話か」を伝える（system_overview.md使用）
- article_purposeを主軸にする
- 開発ログの体験を著者自身の体験として一人称で書く
- スタイルガイド遵守
- アンチパターン回避

### やらないこと
- human-bench/articles/ は絶対に読まない（Reviewer専用）
```

---

### 5.10 reviewer.md

```markdown
# Reviewer Agent

あなたはZennのヘビーユーザー。技術記事を毎日読んでいる。

## 役割
記事を読み、ペルソナ記事（ランダムサンプリングされた5本）と比較して
文体・構成・リズム・読者体験のみを評価する。

## フォーカス
- メタファーの良し悪し
- 文の長さのバリエーション
- 口語の自然さ
- 冒頭の引き込み
- 全体の読みやすさ

## やらないこと
素材の内容（何を書くか）には触れない。書き方だけを見る。

## 読むもの
1. iterations/{N}/article.md — 評価対象
2. オーケストレーターから渡されたベンチマーク記事5本

## 出力フォーマット
# Review — Iteration {N}

## 率直な感想
[記事を読んだ第一印象]

## ベンチマーク比較
[5本と比べてどこが負けているか、具体的に]

## 改善点
[1-3個。文体・構成の具体的な改善提案]

## Score
- Overall: X/10

**重要**: `Overall: X/10` の形式を必ず守ること。
```

---

### 5.11 style_guide_updater.md

```markdown
# Style Guide Updater Agent

レビューフィードバックに基づいてスタイルガイドとアンチパターンログを更新する。

## 読むもの
1. iterations/{N}/review.md — Reviewerのフィードバック
2. iterations/{N}/article.md — 該当記事
3. style_guide.md — 現在のガイド
4. anti_patterns.md — 現在のアンチパターン

## やること
- レビューで指摘された問題を**書き方ルール**としてstyle_guide.mdに追加
- 繰り返される失敗をanti_patterns.mdに追記
- 既存ルールと重複するものは統合

## やらないこと
- 素材の内容に関するルールは追加しない（書き方のみ）

## init時の特別タスク
initコマンドで呼ばれた場合、前の記事固有のルールを削除する。
- 削除対象: 特定のシステム名・用語に言及するルール
- 保持対象: 汎用的な文体ルール（「カタログ構成はダメ」「冒頭2段構成」等）

## 出力
- style_guide.md を上書き保存
- anti_patterns.md に追記
- iterations/{N}/changelog.md にchange log出力
```

---

### 5.12 consolidator.md

```markdown
# Consolidator Agent

style_guide.mdを内容は維持したまま文字数を圧縮する。
iter 5で1回だけ実行される。

## 読むもの
- style_guide.md

## やること
- 重複ルールを統合
- 冗長な説明を簡潔にする
- ANTIパターン表は10行以内に削減
- 目標: 200行以内

## やらないこと
- ルールの意味を変えない
- 重要なルールを削除しない

## 出力
- style_guide.md を上書き保存
- iterations/{N}/consolidation_report.md に圧縮レポート
```

---

## 6. 外部メディア取得仕様

全てエージェントがWebFetchで実行する。Playwrightは使わない。

### 6.1 Qiita（公式API v2）
```
GET https://qiita.com/api/v2/items?query={keyword}&sort=stock&per_page=20
Response: [{ title, url, likes_count, stocks_count, comments_count, body }]
認証: 不要（60リクエスト/時間）
人気指標: likes / comments / stocks でソート可能
```

### 6.2 Hacker News（Algolia API）
```
GET https://hn.algolia.com/api/v1/search?query={keyword}&tags=story&hitsPerPage=20
Response: { hits: [{ title, url, points, num_comments }] }
認証: 不要
人気指標: score（points）/ descendants（コメント数）
```

### 6.3 Zenn（非公式JSON）
```
GET https://zenn.dev/api/articles?q={keyword}&order=liked_count
Response: { articles: [{ title, path, liked_count, comments_count, bookmarked_count }] }
認証: 不要
人気指標: liked / comments / bookmarks
※ 非公式APIのため構造が変わる可能性あり。エラー時はWebSearchにフォールバック
```

### 6.4 OpenAI Blog（RSS → sitemap）
```
手順:
1. WebFetch でRSSフィード or sitemap を取得
2. 記事URLリストを抽出
3. キーワードに関連しそうなURLをエージェントが選定
4. WebFetch で記事本文を取得
5. エージェントがお題との関連度で判定（人気指標なし）

フォールバック: RSS/sitemapが取れなければ WebSearch "{keyword} site:openai.com/blog"
```

### 6.5 Anthropic Blog（sitemap → 記事ページ）
```
手順:
1. WebFetch で sitemap を取得
2. 記事URLリストを抽出
3. キーワードに関連しそうなURLをエージェントが選定
4. WebFetch で記事本文を取得
5. エージェントがお題との関連度で判定（人気指標なし）

フォールバック: sitemapが取れなければ WebSearch "{keyword} site:anthropic.com/research"
```

---

## 7. CLAUDE.md（新規作成）

```markdown
# Zenn Article Generator — Orchestrator Guide

AIエージェント12体でZennのトレンド入りレベルの技術記事を自動生成するシステム。

## アーキテクチャ

### Phase 0: 知識の準備（Trend Searcher）
### Phase 1: 固定素材の生成（Code Analyzer）
### Phase 2: 体験ストーリーの生成 + 改善（Dev Simulator + Material PDCA）
### Phase 3: 記事の生成 + 改善（Writer + 記事PDCA）

## コマンド一覧
python orchestrator.py init --source <file1> <file2>
python orchestrator.py analyze-code
python orchestrator.py after-analyze-code
python orchestrator.py search-trends
python orchestrator.py after-search-trends
python orchestrator.py simulate
python orchestrator.py after-simulate
python orchestrator.py review-materials
python orchestrator.py after-material-review <score>
python orchestrator.py after-material-update
python orchestrator.py start-iteration
python orchestrator.py after-write
python orchestrator.py after-review <score>
python orchestrator.py after-update
python orchestrator.py after-consolidate
python orchestrator.py status

## 停止条件
- 記事PDCA: 2連続 ≥ 9.0/10 / 停滞(±0.5×3回) / 最大10回
- 素材PDCA: 停滞(±0.5×3回) / 最大5回
```

---

## 8. 実装順序

```
Step 1: knowledge_store.py
  依存: なし

Step 2: config.json スキーマ定義
  依存: なし（Step 1と並行可）

Step 3: orchestrator.py（全コマンド）
  依存: Step 1, 2

Step 4: エージェント定義12体
  依存: Step 3（コマンドとファイルパスが確定していること）
  ※ 12体は互いに独立なので並行作成可

Step 5: CLAUDE.md
  依存: Step 3, 4

Step 6: E2Eテスト
  依存: Step 1-5 全て
```

---

## 9. テスト計画

### 9.1 ユニットテスト（knowledge_store.py）

| テスト | 検証内容 |
|--------|---------|
| save_trend() | 追記保存。既存内容を壊さないこと |
| search_trends() | キーワードマッチ。limitの動作 |
| init_knowledge_dir() | 冪等性（2回呼んでも壊れない） |
| is_cache_fresh() | 7日以内→True、8日→False |
| query_hash() | 同じ入力で同じハッシュ。英数字12文字 |

### 9.2 ユニットテスト（orchestrator.py）

| テスト | 検証内容 |
|--------|---------|
| init | materials/削除、knowledge/保持、anti_patterns.mdリセット |
| after-review | 2連続9.0以上→complete |
| after-review | 停滞検出（±0.5×3回）→complete |
| after-review | max_iterations→complete |
| after-review | iter 5→consolidation |
| after-material-review | 停滞検出→start-iterationへ誘導 |
| start-iteration | ベンチマークサンプリング。seed記録 |

### 9.3 E2Eテスト

```
1. init → config.json生成確認
2. analyze-code → materials/fixed/ 5ファイル生成確認
3. search-trends → knowledge/蓄積 + materials/trend_context.md, reader_pain.md確認
4. simulate → materials/dev_simulation_log.md生成確認
5. review-materials → スコア出力確認
6. start-iteration → iterations/1/article.md生成確認
7. after-review → スコア記録・停滞検出確認
```

### 9.4 回帰テスト（2記事目init）

```
1. 1記事目完了後にinit実行
2. ✅ materials/ が全削除されていること
3. ✅ knowledge/ が保持されていること
4. ✅ style_guide.md の共通ルールが保持されていること
5. ✅ style_guide.md の記事固有ルールが削除されていること
6. ✅ anti_patterns.md がリセットされていること
7. ✅ benchmark-criteria.md が保持されていること
```
