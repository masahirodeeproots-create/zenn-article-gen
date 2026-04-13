#!/usr/bin/env python3
"""
Zenn Article Generator — Orchestrator v3.0 (AutoAgent方式)

MetaChainとして機能する:
  - エージェントを自動呼び出し（claude -p）
  - 結果を自動解析（スコア抽出、成果物確認）
  - 次ステップを自動判断して実行
  - 終了条件まで自律ループ

`python orchestrator.py run --source file1.md file2.md`
で Phase 0→完成まで全自動完走する。
"""

import json
import os
import random
import re
import shutil
import subprocess
import sys
from pathlib import Path

import knowledge_store

BASE_DIR = Path("/tmp/zenn-article-gen")
CONFIG_PATH = BASE_DIR / "config.json"
AGENTS_DIR = BASE_DIR / ".claude" / "agents"


# ============================================================
# Config I/O
# ============================================================

def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_config(config: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def log(msg: str):
    """進捗ログ（標準出力）"""
    print(f"[orchestrator] {msg}", flush=True)


# ============================================================
# Agent Execution — MetaChain の核心
# ============================================================

def call_agent(agent_name: str, prompt: str, model: str = "sonnet") -> str:
    """claude -p でサブエージェントを実行し、出力テキストを返す。

    Args:
        agent_name: ログ用のエージェント名
        prompt: エージェントに渡すプロンプト全文
        model: 使用モデル (sonnet / opus / haiku)
    Returns:
        エージェントの出力テキスト
    """
    log(f"CALL {agent_name} (model={model})")

    result = subprocess.run(
        [
            "claude", "-p", prompt,
            "--model", model,
            "--output-format", "text",
            "--permission-mode", "bypassPermissions",
            "--max-turns", "30",
            "--add-dir", str(BASE_DIR),
        ],
        capture_output=True,
        text=True,
        cwd=str(BASE_DIR),
        timeout=1800,  # 30分タイムアウト
    )

    if result.returncode != 0:
        log(f"ERROR: {agent_name} failed (rc={result.returncode})")
        log(f"stderr: {result.stderr[:500]}")
        raise RuntimeError(f"Agent {agent_name} failed")

    output = result.stdout
    log(f"DONE {agent_name} ({len(output)} chars)")
    return output


def extract_score(text: str) -> float | None:
    """エージェント出力から 'Overall: X/10' パターンでスコアを抽出"""
    # ファイルから読む場合も対応
    m = re.search(r"Overall:\s*([\d.]+)\s*/\s*10", text)
    if m:
        return float(m.group(1))
    return None


def read_agent_def(name: str) -> str:
    """エージェント定義ファイルを読む"""
    path = AGENTS_DIR / f"{name}.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


# ============================================================
# Utility
# ============================================================

def sample_benchmark_articles(config: dict) -> list[str]:
    benchmark_dir = BASE_DIR / config["benchmark_dir"]
    all_articles = sorted(benchmark_dir.glob("*.md"))
    n = config.get("benchmark_sample_size", 5)
    seed = random.randint(0, 2**32 - 1)
    config["benchmark_seed"] = seed
    rng = random.Random(seed)
    sampled = rng.sample(all_articles, min(n, len(all_articles)))
    return [str(p) for p in sampled]


def setup_iteration_dir(n: int) -> Path:
    iter_dir = BASE_DIR / "iterations" / str(n)
    iter_dir.mkdir(parents=True, exist_ok=True)
    sg = BASE_DIR / "style_guide.md"
    if sg.exists():
        shutil.copy(sg, iter_dir / "style_guide.md")
    return iter_dir


def check_stagnation(scores: list[dict], window: int, tolerance: float) -> bool:
    vals = [s["score"] for s in scores]
    if len(vals) < window:
        return False
    recent = vals[-window:]
    return max(recent) - min(recent) <= tolerance


def source_files_prompt(config: dict) -> str:
    """ソースファイル一覧をプロンプト用に整形"""
    files = config["simulator_source_files"]
    return "\n".join(f"- {BASE_DIR / f}" for f in files)


# ============================================================
# Phase Executors — 各フェーズを自動実行
# ============================================================

def phase_init(config: dict, source_files: list[str]):
    """init: 成果物クリア+知識DB保持"""
    log("=== PHASE: INIT ===")

    # ソースファイル存在確認
    for f in source_files:
        path = BASE_DIR / f if not Path(f).is_absolute() else Path(f)
        if not path.exists():
            log(f"ERROR: Source file not found: {f}")
            sys.exit(1)

    # materials/ を全削除して再作成
    materials_dir = BASE_DIR / "materials"
    if materials_dir.exists():
        shutil.rmtree(materials_dir)
    materials_dir.mkdir(parents=True)
    (materials_dir / "fixed").mkdir()

    # iterations/ を全削除
    iterations_dir = BASE_DIR / "iterations"
    if iterations_dir.exists():
        shutil.rmtree(iterations_dir)

    # material_reviews/ をクリア
    mr_dir = BASE_DIR / "material_reviews"
    if mr_dir.exists():
        shutil.rmtree(mr_dir)
    mr_dir.mkdir(parents=True, exist_ok=True)

    # anti_patterns.md をリセット
    (BASE_DIR / "anti_patterns.md").write_text(
        "# Anti-Patterns Log\n\n"
        "このファイルは反復ごとに蓄積されるアンチパターンの記録です。\n"
        "Writerは記事生成前にこのファイルを読み、過去に指摘された失敗パターンを意識的に避けてください。\n\n"
        "---\n\n"
        "（まだ記録なし — Iteration 1完了後から追記されます）\n"
    )

    knowledge_store.init_knowledge_dir()

    config["simulator_source_files"] = source_files
    config["topic"] = ""
    config["article_purpose"] = ""
    config["reader_takeaway"] = ""
    config["system_role"] = ""
    config["current_phase"] = "init"
    config["status"] = "running"
    config["current_iteration"] = 0
    config["scores"] = []
    config["last_score"] = None
    config["consecutive_above_threshold"] = 0
    config["material_scores"] = []
    config["material_current_iteration"] = 0
    config["current_benchmark_articles"] = []
    config["benchmark_seed"] = None
    save_config(config)

    # Style Guide Updater (init cleanup)
    sg = BASE_DIR / "style_guide.md"
    if sg.exists():
        log("Style Guide cleanup...")
        call_agent("style_guide_updater", f"""
あなたはStyle Guide Updater Agentです。

{read_agent_def("style_guide_updater")}

今回のタスク: init_cleanup
{BASE_DIR / "style_guide.md"} を読んで、前の記事固有のルールを削除してください。
共通ルール（カタログ構成はダメ、冒頭2段構成等）は残してください。
上書き保存してください。
""")

    log("INIT complete")


def phase_analyze_code(config: dict):
    """Phase 1: Code Analyzer — topic + 固定素材5つ生成"""
    log("=== PHASE 1: ANALYZE CODE ===")

    config["current_phase"] = "analyze-code"
    save_config(config)

    sources = source_files_prompt(config)
    call_agent("code_analyzer", f"""
あなたはCode Analyzer Agentです。

{read_agent_def("code_analyzer")}

## ソースファイル
{sources}

全ファイルを読んで以下を実行してください:

1. config.jsonのフィールド生成:
   {CONFIG_PATH} を読んで topic, article_purpose, reader_takeaway, system_role を生成し、
   config.jsonに書き込んでください（他のフィールドは変更しない）。

2. 固定素材5ファイルを {BASE_DIR / "materials" / "fixed"} に生成:
   - system_overview.md, metrics.md, architecture.md, code_examples.md, comparisons.md
""")

    # 検証
    config = load_config()  # Code Analyzerが更新したconfigを再読み込み
    fixed_dir = BASE_DIR / "materials" / "fixed"
    for fname in ["system_overview.md", "metrics.md", "architecture.md",
                  "code_examples.md", "comparisons.md"]:
        if not (fixed_dir / fname).exists():
            raise RuntimeError(f"Code Analyzer failed: {fname} not found")

    if not config.get("topic"):
        raise RuntimeError("Code Analyzer failed: topic is empty")

    config["current_phase"] = "code-analyzed"
    save_config(config)
    log(f"Phase 1 complete. topic={config['topic']}")


def phase_search_trends(config: dict):
    """Phase 0: Trend Searcher — トレンド・痛み検索"""
    log("=== PHASE 0: SEARCH TRENDS ===")

    config["current_phase"] = "search-trends"
    save_config(config)

    call_agent("trend_searcher", f"""
あなたはTrend Searcher Agentです。

{read_agent_def("trend_searcher")}

## topic
{config["topic"]}

## 出力先
- {BASE_DIR / "materials" / "trend_context.md"}（3-5個のトレンド）
- {BASE_DIR / "materials" / "reader_pain.md"}（3-5個の読者の痛み）

## knowledge DBへの蓄積
- {BASE_DIR / "knowledge" / "trends.md"} に追記
- {BASE_DIR / "knowledge" / "reader_pains.md"} に追記
""")

    # 検証
    for fname in ["materials/trend_context.md", "materials/reader_pain.md"]:
        if not (BASE_DIR / fname).exists():
            raise RuntimeError(f"Trend Searcher failed: {fname} not found")

    config["current_phase"] = "trends-ready"
    save_config(config)
    log("Phase 0 complete")


def phase_simulate(config: dict):
    """Phase 2a: Dev Simulator — 体験ストーリー生成"""
    log("=== PHASE 2a: SIMULATE ===")

    log_path = BASE_DIR / config["dev_simulation_log"]
    if log_path.exists():
        log_path.unlink()

    config["current_phase"] = "simulate"
    config["material_scores"] = []
    config["material_current_iteration"] = 0
    save_config(config)

    sources = source_files_prompt(config)
    call_agent("dev_simulator", f"""
あなたはDev Simulator（Round Controller）です。

{read_agent_def("dev_simulator")}

## 完成形のソースファイル（Director用）
{sources}

## 参照素材
- {BASE_DIR / "materials" / "fixed" / "system_overview.md"}（Human役用）
- {BASE_DIR / "materials" / "trend_context.md"}（Human役用）
- {BASE_DIR / "materials" / "reader_pain.md"}（Director役用）

## 出力先
{log_path}

## 重要
- 3エージェントの発言を生成してください（1つのAIが3つの視点で書いてOK。速度優先）
- 最大5ラウンド、Directorスコア≥95でSTOP
""")

    if not log_path.exists():
        raise RuntimeError("Dev Simulator failed: log not found")

    config["current_phase"] = "ready"
    save_config(config)
    log("Phase 2a complete")


def phase_review_materials(config: dict):
    """Phase 2b: 素材改善ループ"""
    log("=== PHASE 2b: MATERIAL REVIEW LOOP ===")

    material_max = config["material_max_iterations"]

    while config["material_current_iteration"] < material_max:
        n = config["material_current_iteration"] + 1
        config["material_current_iteration"] = n
        config["current_phase"] = "review-materials"
        save_config(config)

        # --- Material Reviewer ---
        log(f"Material Review round {n}/{material_max}")
        review_path = BASE_DIR / "material_reviews" / f"review_{n}.md"

        call_agent("material_reviewer", f"""
あなたはMaterial Reviewer Agentです。

{read_agent_def("material_reviewer")}

## 読むもの
1. {BASE_DIR / "materials" / "fixed" / "system_overview.md"}
2. {BASE_DIR / config["dev_simulation_log"]}
3. {BASE_DIR / "human-bench" / "articles"} 配下のペルソナ記事全部

## 出力先
{review_path}

必ず `Overall: X/10` の形式でスコアを含めてください。
""")

        # スコア抽出
        if not review_path.exists():
            raise RuntimeError(f"Material Reviewer failed: {review_path} not found")

        review_text = review_path.read_text(encoding="utf-8")
        score = extract_score(review_text)
        if score is None:
            log(f"WARNING: Could not extract score from review_{n}.md, defaulting to 5.0")
            score = 5.0

        config["material_scores"].append({"iteration": n, "score": score})
        save_config(config)
        log(f"Material score: {score}/10")

        # 停滞検出
        if check_stagnation(config["material_scores"],
                            config["material_stagnation_window"],
                            config["material_stagnation_tolerance"]):
            recent = [s["score"] for s in config["material_scores"][-config["material_stagnation_window"]:]]
            log(f"Material stagnation detected: {recent}")
            break

        if n >= material_max:
            log("Material max iterations reached")
            break

        # --- Material Updater ---
        log(f"Material Update round {n}")
        sources = source_files_prompt(config)

        call_agent("material_updater", f"""
あなたはMaterial Updater Agentです。

{read_agent_def("material_updater")}

## 読むもの
1. {BASE_DIR / config["dev_simulation_log"]}（改善対象）
2. {review_path}（Reviewerの指摘）
3. ソースファイル（事実確認用）:
{sources}

dev_simulation_log.md を改善して上書き保存してください。
""")

    log("Phase 2b complete")


def phase_article_loop(config: dict):
    """Phase 3: 記事生成+改善ループ"""
    log("=== PHASE 3: ARTICLE LOOP ===")

    while True:
        n = config["current_iteration"] + 1

        if n > config["max_iterations"]:
            log("Max iterations reached")
            config["status"] = "complete"
            save_config(config)
            break

        # --- ベンチマークサンプリング + ディレクトリ準備 ---
        sampled = sample_benchmark_articles(config)
        config["current_benchmark_articles"] = sampled
        setup_iteration_dir(n)
        config["current_iteration"] = n
        config["current_phase"] = "write"
        save_config(config)

        log(f"--- Iteration {n} (seed={config['benchmark_seed']}) ---")

        # --- Writer ---
        article_path = f"iterations/{n}/article.md"
        benchmark_list = "\n".join(f"- {p}" for p in sampled)
        fixed_list = "\n".join(
            f"- {BASE_DIR / 'materials' / 'fixed' / f}"
            for f in ["system_overview.md", "metrics.md", "architecture.md",
                      "code_examples.md", "comparisons.md"]
        )

        call_agent("writer", f"""
あなたはWriter Agentです。

{read_agent_def("writer")}

## 記事の目的
- article_purpose: {config.get("article_purpose", "")}
- reader_takeaway: {config.get("reader_takeaway", "")}
- system_role: {config.get("system_role", "")}

## 読むもの
- 固定素材:
{fixed_list}
- 体験ストーリー: {BASE_DIR / config["dev_simulation_log"]}
- スタイルガイド: {BASE_DIR / "style_guide.md"}
- アンチパターン: {BASE_DIR / "anti_patterns.md"}

## 出力先
{BASE_DIR / article_path}

human-bench/articles/ は絶対に読まないでください。
""")

        if not (BASE_DIR / article_path).exists():
            raise RuntimeError(f"Writer failed: {article_path} not found")

        config["current_phase"] = "review"
        save_config(config)

        # --- Reviewer ---
        review_path = f"iterations/{n}/review.md"

        call_agent("reviewer", f"""
あなたはReviewer Agentです。

{read_agent_def("reviewer")}

## 読むもの
1. {BASE_DIR / article_path}（評価対象）
2. ベンチマーク記事:
{benchmark_list}

## 出力先
{BASE_DIR / review_path}

必ず `Overall: X/10` の形式でスコアを含めてください。
""")

        if not (BASE_DIR / review_path).exists():
            raise RuntimeError(f"Reviewer failed: {review_path} not found")

        review_text = (BASE_DIR / review_path).read_text(encoding="utf-8")
        score = extract_score(review_text)
        if score is None:
            log(f"WARNING: Could not extract score, defaulting to 5.0")
            score = 5.0

        # --- スコア記録+停止判定 ---
        config["last_score"] = score
        config["scores"].append({"iteration": n, "score": score})

        threshold = config.get("score_threshold", 9.0)
        if score >= threshold:
            config["consecutive_above_threshold"] = config.get("consecutive_above_threshold", 0) + 1
        else:
            config["consecutive_above_threshold"] = 0
        save_config(config)

        log(f"Score: {score}/10 (consecutive≥{threshold}: {config['consecutive_above_threshold']})")

        # 2連続 ≥ 9.0
        if config["consecutive_above_threshold"] >= 2:
            log("SUCCESS: 2 consecutive scores >= 9.0!")
            config["status"] = "complete"
            save_config(config)
            break

        # 停滞検出
        if check_stagnation(config["scores"],
                            config["stagnation_window"],
                            config["stagnation_tolerance"]):
            recent = [s["score"] for s in config["scores"][-config["stagnation_window"]:]]
            log(f"Stagnation detected: {recent}")
            config["status"] = "complete"
            save_config(config)
            break

        # --- Consolidation (iter 5) ---
        if n == config.get("consolidation_at_iteration"):
            log("Running Consolidator...")
            call_agent("consolidator", f"""
あなたはConsolidator Agentです。

{read_agent_def("consolidator")}

{BASE_DIR / "style_guide.md"} を読んで、内容を維持したまま文字数を圧縮してください。
目標: 200行以内。上書き保存してください。
圧縮レポートを {BASE_DIR / f"iterations/{n}/consolidation_report.md"} に出力してください。
""")

        # --- Style Guide Updater ---
        log("Updating style guide...")
        call_agent("style_guide_updater", f"""
あなたはStyle Guide Updater Agentです。

{read_agent_def("style_guide_updater")}

## 読むもの
1. {BASE_DIR / f"iterations/{n}/review.md"}
2. {BASE_DIR / f"iterations/{n}/article.md"}
3. {BASE_DIR / "style_guide.md"}
4. {BASE_DIR / "anti_patterns.md"}

レビューで指摘された問題を書き方ルールとしてstyle_guide.mdに追加してください。
繰り返される失敗をanti_patterns.mdに追記してください。
change logを {BASE_DIR / f"iterations/{n}/changelog.md"} に出力してください。
""")

        config["current_phase"] = "next"
        save_config(config)
        log(f"Iteration {n} complete. Moving to next.")


# ============================================================
# Main Commands
# ============================================================

def cmd_run(source_files: list[str]):
    """全自動実行: init → Phase 1 → Phase 0 → Phase 2 → Phase 3 → 完成"""
    config = load_config()

    # init
    phase_init(config, source_files)

    # Phase 1: Code Analyzer (topicが必要なのでPhase 0より先)
    config = load_config()
    phase_analyze_code(config)

    # Phase 0: Trend Searcher
    config = load_config()
    phase_search_trends(config)

    # Phase 2a: Dev Simulator
    config = load_config()
    phase_simulate(config)

    # Phase 2b: Material Review Loop
    config = load_config()
    phase_review_materials(config)

    # Phase 3: Article Loop
    config = load_config()
    phase_article_loop(config)

    # 完了
    config = load_config()
    log("=" * 60)
    log(f"COMPLETE! Final article: iterations/{config['current_iteration']}/article.md")
    log(f"Scores: {[s['score'] for s in config['scores']]}")
    log(f"Material scores: {[s['score'] for s in config['material_scores']]}")
    log("=" * 60)


def cmd_status():
    config = load_config()
    print(json.dumps(config, indent=2, ensure_ascii=False))


def main():
    if len(sys.argv) < 2:
        cmd_status()
        return

    cmd = sys.argv[1]

    if cmd == "run":
        files = [a for a in sys.argv[2:] if a != "--source"]
        if not files:
            print("Usage: python orchestrator.py run --source <file1> <file2> ...")
            sys.exit(1)
        cmd_run(files)

    elif cmd == "status":
        cmd_status()

    else:
        print(f"Unknown command: {cmd}")
        print("Available: run, status")
        sys.exit(1)


if __name__ == "__main__":
    main()
