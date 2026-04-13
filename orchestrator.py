#!/usr/bin/env python3
"""
Zenn Article Generator — Orchestrator v2.0

コードが担う責務（判断不要な処理のみ）:
- イテレーション番号の管理
- ディレクトリ作成・ファイルコピー・クリア
- スコアの記録・停滞検出・2連続9.0以上検出
- ベンチマーク記事のランダムサンプリング（seed記録）
- 検索キャッシュの重複チェック

エージェントが担う責務（判断が必要な全て）:
- 検索・分析・生成・評価・改善

フロー:
  init → analyze-code → search-trends → simulate →
  review-materials(loop) → start-iteration(loop) → 完成
"""

import json
import random
import shutil
import sys
from pathlib import Path

import knowledge_store

BASE_DIR = Path("/tmp/zenn-article-gen")
CONFIG_PATH = BASE_DIR / "config.json"


# --- Config I/O ---

def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_config(config: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def print_agent_context(config: dict, extra: dict = None):
    """エージェントに渡す情報をJSON出力"""
    ctx = {
        "iteration": config.get("current_iteration", 0),
        "phase": config["current_phase"],
        "topic": config.get("topic", ""),
    }
    if extra:
        ctx.update(extra)
    print(json.dumps(ctx, indent=2, ensure_ascii=False))


# --- Utility ---

def sample_benchmark_articles(config: dict) -> list[str]:
    """benchmark_dirからランダムにN本サンプリング。seedを記録。"""
    benchmark_dir = BASE_DIR / config["benchmark_dir"]
    all_articles = sorted(benchmark_dir.glob("*.md"))
    n = config.get("benchmark_sample_size", 5)
    seed = random.randint(0, 2**32 - 1)
    config["benchmark_seed"] = seed
    rng = random.Random(seed)
    sampled = rng.sample(all_articles, min(n, len(all_articles)))
    return [str(p) for p in sampled]


def setup_iteration_dir(n: int) -> Path:
    """イテレーションディレクトリを作成し、style_guide.mdをアーカイブ"""
    iter_dir = BASE_DIR / "iterations" / str(n)
    iter_dir.mkdir(parents=True, exist_ok=True)
    sg = BASE_DIR / "style_guide.md"
    if sg.exists():
        shutil.copy(sg, iter_dir / "style_guide.md")
    return iter_dir


def check_stagnation(scores: list[dict], window: int, tolerance: float) -> bool:
    """直近window回のスコアが±tolerance以内なら停滞"""
    vals = [s["score"] for s in scores]
    if len(vals) < window:
        return False
    recent = vals[-window:]
    return max(recent) - min(recent) <= tolerance


# --- Commands ---

def cmd_init(config: dict, source_files: list[str]):
    """ソースファイル指定。成果物クリア+知識DB保持+Code Analyzer呼び出し"""
    # ソースファイル存在確認
    for f in source_files:
        path = BASE_DIR / f if not Path(f).is_absolute() else Path(f)
        if not path.exists():
            print(f"ERROR: Source file not found: {f}")
            sys.exit(1)

    # materials/ を全削除して再作成
    materials_dir = BASE_DIR / "materials"
    if materials_dir.exists():
        shutil.rmtree(materials_dir)
    materials_dir.mkdir(parents=True)
    (materials_dir / "fixed").mkdir()
    print("CLEANED: materials/ recreated")

    # iterations/ を全削除
    iterations_dir = BASE_DIR / "iterations"
    if iterations_dir.exists():
        shutil.rmtree(iterations_dir)
        print("CLEANED: iterations/ removed")

    # material_reviews/ をクリア
    mr_dir = BASE_DIR / "material_reviews"
    if mr_dir.exists():
        shutil.rmtree(mr_dir)
    mr_dir.mkdir(parents=True, exist_ok=True)
    print("CLEANED: material_reviews/ cleared")

    # anti_patterns.md をリセット
    anti_path = BASE_DIR / "anti_patterns.md"
    anti_path.write_text(
        "# Anti-Patterns Log\n\n"
        "このファイルは反復ごとに蓄積されるアンチパターンの記録です。\n"
        "Writerは記事生成前にこのファイルを読み、過去に指摘された失敗パターンを意識的に避けてください。\n\n"
        "---\n\n"
        "（まだ記録なし — Iteration 1完了後から追記されます）\n"
    )
    print("CLEANED: anti_patterns.md reset")

    # knowledge/ を保持（なければ作成）
    knowledge_store.init_knowledge_dir()
    print("KEPT: knowledge/ preserved")

    # config をリセット
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

    # Style Guide Updaterに記事固有ルール削除を依頼
    sg = BASE_DIR / "style_guide.md"
    if sg.exists():
        print("ACTION: CALL_STYLE_GUIDE_UPDATER")
        print_agent_context(config, {
            "style_guide_path": "style_guide.md",
            "task": "init_cleanup",
            "instruction": "前の記事固有のルールを削除する。共通ルール（カタログ構成はダメ、冒頭2段構成等）は残す。",
        })
        print("---")

    # Code Analyzerを呼び出し
    print("ACTION: CALL_CODE_ANALYZER")
    print_agent_context(config, {
        "source_files": source_files,
        "output_dir": "materials/fixed/",
        "outputs": [
            "system_overview.md",
            "metrics.md",
            "architecture.md",
            "code_examples.md",
            "comparisons.md",
        ],
        "config_fields_to_generate": ["topic", "article_purpose", "reader_takeaway", "system_role"],
        "instruction": "1) ソースファイルを読んでtopic, article_purpose, reader_takeaway, system_roleを生成しconfig.jsonに書き込む 2) 固定素材5つをmaterials/fixed/に生成する",
    })


def cmd_analyze_code(config: dict):
    """Phase 1: Code Analyzer呼び出し（initから分離実行する場合用）"""
    config["current_phase"] = "analyze-code"
    save_config(config)

    print("ACTION: CALL_CODE_ANALYZER")
    print_agent_context(config, {
        "source_files": config["simulator_source_files"],
        "output_dir": "materials/fixed/",
        "outputs": [
            "system_overview.md",
            "metrics.md",
            "architecture.md",
            "code_examples.md",
            "comparisons.md",
        ],
        "config_fields_to_generate": ["topic", "article_purpose", "reader_takeaway", "system_role"],
    })


def cmd_after_analyze_code(config: dict):
    """Code Analyzer完了後"""
    fixed_dir = BASE_DIR / "materials" / "fixed"
    required = ["system_overview.md", "metrics.md", "architecture.md",
                "code_examples.md", "comparisons.md"]
    for fname in required:
        if not (fixed_dir / fname).exists():
            print(f"ERROR: materials/fixed/{fname} not found. Code Analyzer may have failed.")
            sys.exit(1)

    if not config.get("topic"):
        print("ERROR: topic is empty. Code Analyzer did not generate config fields.")
        sys.exit(1)

    config["current_phase"] = "code-analyzed"
    save_config(config)

    print("STATUS: CODE_ANALYSIS_COMPLETE")
    print("ACTION: Run 'python orchestrator.py search-trends'")


def cmd_search_trends(config: dict):
    """Phase 0: Trend Searcher呼び出し"""
    if not config.get("topic"):
        print("ERROR: topic is empty. Run analyze-code first.")
        sys.exit(1)

    config["current_phase"] = "search-trends"
    save_config(config)

    print("ACTION: CALL_TREND_SEARCHER")
    print_agent_context(config, {
        "knowledge_dir": "knowledge/",
        "trend_output": "materials/trend_context.md",
        "pain_output": "materials/reader_pain.md",
    })


def cmd_after_search_trends(config: dict):
    """Trend Searcher完了後"""
    for fname in ["materials/trend_context.md", "materials/reader_pain.md"]:
        if not (BASE_DIR / fname).exists():
            print(f"ERROR: {fname} not found. Trend Searcher may have failed.")
            sys.exit(1)

    config["current_phase"] = "trends-ready"
    save_config(config)

    print("STATUS: TREND_SEARCH_COMPLETE")
    print("ACTION: Run 'python orchestrator.py simulate'")


def cmd_simulate(config: dict):
    """Phase 2: Dev Simulator呼び出し"""
    # dev_simulation_log をクリア
    log_path = BASE_DIR / config["dev_simulation_log"]
    if log_path.exists():
        log_path.unlink()
        print(f"CLEANED: {config['dev_simulation_log']} removed")

    config["current_phase"] = "simulate"
    config["material_scores"] = []
    config["material_current_iteration"] = 0
    save_config(config)

    print("ACTION: CALL_DEV_SIMULATOR")
    print_agent_context(config, {
        "simulator_source_files": config["simulator_source_files"],
        "dev_simulation_log_path": config["dev_simulation_log"],
        "simulator_score_threshold": config["simulator_score_threshold"],
        "system_overview_path": "materials/fixed/system_overview.md",
        "trend_context_path": "materials/trend_context.md",
        "reader_pain_path": "materials/reader_pain.md",
    })


def cmd_after_simulate(config: dict):
    """Simulator完了後"""
    log_path = BASE_DIR / config["dev_simulation_log"]
    if not log_path.exists():
        print("ERROR: dev_simulation_log.md not found. Simulator may have failed.")
        sys.exit(1)

    config["current_phase"] = "ready"
    save_config(config)

    print("STATUS: SIMULATION_COMPLETE")
    print("ACTION: Run 'python orchestrator.py review-materials'")


def cmd_review_materials(config: dict):
    """素材改善ループ: Material Reviewer呼び出し"""
    n = config["material_current_iteration"] + 1
    material_max = config["material_max_iterations"]

    if n > material_max:
        print("STATUS: MATERIAL_MAX_ITERATIONS_REACHED")
        print("ACTION: Run 'python orchestrator.py start-iteration'")
        return

    config["material_current_iteration"] = n
    config["current_phase"] = "review-materials"
    save_config(config)

    print(f"ACTION: CALL_MATERIAL_REVIEWER (round {n}/{material_max})")
    print_agent_context(config, {
        "dev_simulation_log_path": config["dev_simulation_log"],
        "system_overview_path": "materials/fixed/system_overview.md",
        "material_review_output_path": f"material_reviews/review_{n}.md",
    })


def cmd_after_material_review(config: dict, score: float):
    """素材レビュー完了後"""
    config["material_scores"].append({
        "iteration": config["material_current_iteration"],
        "score": score,
    })
    save_config(config)

    print(f"MATERIAL_SCORE: {score}/10")

    if check_stagnation(config["material_scores"],
                        config["material_stagnation_window"],
                        config["material_stagnation_tolerance"]):
        recent = [s["score"] for s in config["material_scores"][-config["material_stagnation_window"]:]]
        print(f"STATUS: MATERIAL_STAGNATION ({recent})")
        print("ACTION: Run 'python orchestrator.py start-iteration'")
        return

    print("ACTION: CALL_MATERIAL_UPDATER")
    print_agent_context(config, {
        "dev_simulation_log_path": config["dev_simulation_log"],
        "material_review_path": f"material_reviews/review_{config['material_current_iteration']}.md",
        "simulator_source_files": config["simulator_source_files"],
        "instruction": "素材Reviewerの指摘に基づいてdev_simulation_log.mdを改善。ログの修正はsim_directorに検証させること。",
    })


def cmd_after_material_update(config: dict):
    """素材更新完了後 → 次の素材レビューへ"""
    print("ACTION: Run 'python orchestrator.py review-materials'")


def cmd_start_iteration(config: dict):
    """Phase 3: 記事改善ループ開始。Writer呼び出し"""
    if config.get("status") == "complete":
        print("STATUS: ALREADY_COMPLETE")
        return

    n = config["current_iteration"] + 1
    if n > config["max_iterations"]:
        print("STATUS: MAX_ITERATIONS_REACHED")
        config["status"] = "complete"
        save_config(config)
        return

    sampled = sample_benchmark_articles(config)
    config["current_benchmark_articles"] = sampled

    setup_iteration_dir(n)
    config["current_iteration"] = n
    config["current_phase"] = "write"
    save_config(config)

    print("ACTION: CALL_WRITER")
    print(f"BENCHMARK_SAMPLE: {len(sampled)} articles (seed={config['benchmark_seed']})")
    print_agent_context(config, {
        "article_output_path": f"iterations/{n}/article.md",
        "style_guide_path": "style_guide.md",
        "anti_patterns_log_path": config["anti_patterns_log"],
        "dev_simulation_log_path": config["dev_simulation_log"],
        "article_purpose": config.get("article_purpose", ""),
        "reader_takeaway": config.get("reader_takeaway", ""),
        "system_role": config.get("system_role", ""),
        "fixed_materials": [
            "materials/fixed/system_overview.md",
            "materials/fixed/metrics.md",
            "materials/fixed/architecture.md",
            "materials/fixed/code_examples.md",
            "materials/fixed/comparisons.md",
        ],
    })


def cmd_after_write(config: dict):
    """Writer完了後 → Reviewer呼び出し"""
    n = config["current_iteration"]
    article_path = BASE_DIR / "iterations" / str(n) / "article.md"

    if not article_path.exists():
        print("ERROR: article.md not found. Writer may have failed.")
        sys.exit(1)

    config["current_phase"] = "review"
    save_config(config)

    print("ACTION: CALL_REVIEWER")
    print_agent_context(config, {
        "article_path": f"iterations/{n}/article.md",
        "review_output_path": f"iterations/{n}/review.md",
        "benchmark_articles": config["current_benchmark_articles"],
    })


def cmd_after_review(config: dict, score: float):
    """Reviewer完了後 → 停止判定 or 次のアクション"""
    n = config["current_iteration"]

    config["last_score"] = score
    config["scores"].append({"iteration": n, "score": score})

    # 2連続 ≥ 9.0 チェック
    threshold = config.get("score_threshold", 9.0)
    if score >= threshold:
        config["consecutive_above_threshold"] = config.get("consecutive_above_threshold", 0) + 1
    else:
        config["consecutive_above_threshold"] = 0

    save_config(config)
    print(f"SCORE: {score}/10 (consecutive_above_threshold: {config['consecutive_above_threshold']})")

    if config["consecutive_above_threshold"] >= 2:
        print("ACTION: STOP  # 2 consecutive scores >= 9.0")
        config["status"] = "complete"
        save_config(config)
        return

    # 停滞検出
    if check_stagnation(config["scores"],
                        config["stagnation_window"],
                        config["stagnation_tolerance"]):
        recent = [s["score"] for s in config["scores"][-config["stagnation_window"]:]]
        print(f"ACTION: STOP  # stagnation detected: {recent}")
        config["status"] = "complete"
        save_config(config)
        return

    if n >= config["max_iterations"]:
        print(f"ACTION: STOP  # max iterations ({config['max_iterations']}) reached")
        config["status"] = "complete"
        save_config(config)
        return

    # Consolidation判定
    if n == config.get("consolidation_at_iteration"):
        config["current_phase"] = "consolidate"
        save_config(config)
        print(f"ACTION: CALL_CONSOLIDATION  # iteration {n}")
        print_agent_context(config, {
            "style_guide_path": "style_guide.md",
            "consolidation_output_path": f"iterations/{n}/consolidation_report.md",
            "target_lines": 200,
            "instruction": "内容を失わずに文字数を圧縮する。ANTIパターン表は10行以内に削減。重複ルールを統合。",
        })
    else:
        config["current_phase"] = "update"
        save_config(config)
        print("ACTION: CALL_STYLE_GUIDE_UPDATER")
        print_agent_context(config, {
            "review_path": f"iterations/{n}/review.md",
            "article_path": f"iterations/{n}/article.md",
            "changelog_output_path": f"iterations/{n}/changelog.md",
            "anti_patterns_log_path": config["anti_patterns_log"],
            "style_guide_path": "style_guide.md",
        })


def cmd_after_update(config: dict):
    """Style Guide Updater完了後 → 次イテレーションへ"""
    config["current_phase"] = "next"
    save_config(config)
    next_n = config["current_iteration"] + 1
    print(f"ACTION: NEXT_ITERATION  # run: python orchestrator.py start-iteration")
    print(f"NEXT_ITERATION: {next_n}")


def cmd_after_consolidate(config: dict):
    """Consolidation完了後 → Style Guide Updater呼び出し"""
    n = config["current_iteration"]
    config["current_phase"] = "update"
    save_config(config)

    print("ACTION: CALL_STYLE_GUIDE_UPDATER  # after consolidation")
    print_agent_context(config, {
        "review_path": f"iterations/{n}/review.md",
        "article_path": f"iterations/{n}/article.md",
        "changelog_output_path": f"iterations/{n}/changelog.md",
        "anti_patterns_log_path": config["anti_patterns_log"],
        "style_guide_path": "style_guide.md",
        "note": "consolidation後なので、新規ルール追加より既存ルールの精緻化を優先する",
    })


def cmd_status(config: dict):
    """全フェーズの進捗を表示"""
    print("=== Orchestrator Status ===")
    print(json.dumps(config, indent=2, ensure_ascii=False))


# --- Command Router ---

COMMANDS = {
    "analyze-code": cmd_analyze_code,
    "after-analyze-code": cmd_after_analyze_code,
    "search-trends": cmd_search_trends,
    "after-search-trends": cmd_after_search_trends,
    "simulate": cmd_simulate,
    "after-simulate": cmd_after_simulate,
    "review-materials": cmd_review_materials,
    "after-material-update": cmd_after_material_update,
    "start-iteration": cmd_start_iteration,
    "after-write": cmd_after_write,
    "after-update": cmd_after_update,
    "after-consolidate": cmd_after_consolidate,
    "status": cmd_status,
}

SCORE_COMMANDS = {"after-review", "after-material-review"}
ALL_COMMANDS = set(COMMANDS.keys()) | SCORE_COMMANDS | {"init"}


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd not in ALL_COMMANDS:
        print(f"Unknown command: {cmd}")
        print(f"Available: {', '.join(sorted(ALL_COMMANDS))}")
        sys.exit(1)

    config = load_config()

    if cmd == "init":
        if len(sys.argv) < 3:
            print("ERROR: init requires source file paths")
            print("  Usage: python orchestrator.py init --source <file1> <file2> ...")
            sys.exit(1)
        files = [a for a in sys.argv[2:] if a != "--source"]
        cmd_init(config, files)

    elif cmd == "after-review":
        if len(sys.argv) < 3:
            print("ERROR: after-review requires a score argument")
            sys.exit(1)
        try:
            score = float(sys.argv[2])
        except ValueError:
            print(f"ERROR: Invalid score '{sys.argv[2]}' — must be a number")
            sys.exit(1)
        cmd_after_review(config, score)

    elif cmd == "after-material-review":
        if len(sys.argv) < 3:
            print("ERROR: after-material-review requires a score argument")
            sys.exit(1)
        try:
            score = float(sys.argv[2])
        except ValueError:
            print(f"ERROR: Invalid score '{sys.argv[2]}' — must be a number")
            sys.exit(1)
        cmd_after_material_review(config, score)

    else:
        COMMANDS[cmd](config)


if __name__ == "__main__":
    main()
