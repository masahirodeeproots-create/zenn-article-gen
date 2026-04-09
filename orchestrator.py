#!/usr/bin/env python3
"""
Zenn Article Generator — Orchestrator Script (v2 — uhyo方式)

コードが担う責務:
- イテレーション番号の管理
- ディレクトリ作成・ファイルコピー
- ベンチマーク記事のランダムサンプリング
- 次アクションの判定（続行/停止/Consolidation）
- 連続スコア達成の追跡

LLMが担う責務（このスクリプトはやらない）:
- 記事生成 (Writer) ← style_guide + anti_patterns_log を読む
- 記事評価 (Reviewer) ← サンプリングされたベンチマーク記事を読む
- スタイルガイド更新 + アンチパターン追記 (Style Guide Updater)
- スタイルガイド圧縮 (Consolidation)

使い方:
  python orchestrator.py simulate              # Phase 0: 開発シミュレーションログを生成
  python orchestrator.py after-simulate        # Simulator完了後に実行
  python orchestrator.py start-iteration       # 新しい反復を開始（ベンチマークサンプリング含む）
  python orchestrator.py after-write           # Writer完了後に実行
  python orchestrator.py after-review <score>  # Reviewer完了後に実行 (例: after-review 8.5)
  python orchestrator.py after-update          # Style Guide Updater完了後に実行
  python orchestrator.py after-consolidate     # Consolidation完了後に実行
  python orchestrator.py status                # 現在の状態を表示
"""

import json
import random
import shutil
import sys
from pathlib import Path

BASE_DIR = Path("/tmp/zenn-article-gen")
CONFIG_PATH = BASE_DIR / "config.json"


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return json.load(f)


def save_config(config: dict):
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def sample_benchmark_articles(config: dict) -> list[str]:
    """benchmark_dir からランダムに N 本サンプリングする"""
    benchmark_dir = BASE_DIR / config["benchmark_dir"]
    all_articles = sorted(benchmark_dir.glob("*.md"))
    n = config.get("benchmark_sample_size", 5)
    sampled = random.sample(all_articles, min(n, len(all_articles)))
    return [str(p) for p in sampled]


def setup_iteration_dir(n: int) -> Path:
    """イテレーションディレクトリを作成し、現在のスタイルガイドをアーカイブする"""
    iter_dir = BASE_DIR / "iterations" / str(n)
    iter_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(BASE_DIR / "style_guide.md", iter_dir / "style_guide.md")
    return iter_dir


def print_agent_context(config: dict, extra: dict = None):
    """エージェントに渡すべき情報を構造化して出力する"""
    ctx = {
        "iteration": config["current_iteration"],
        "phase": config["current_phase"],
        "topic": config["topic"],
    }
    if extra:
        ctx.update(extra)
    print(json.dumps(ctx, indent=2, ensure_ascii=False))


def cmd_simulate(config: dict):
    """Phase 0: 開発シミュレーションログの生成を開始"""
    # フルリセット
    config["current_phase"] = "simulate"
    config["current_iteration"] = 0
    config["consecutive_above_threshold"] = 0
    config["scores"] = []
    config["last_score"] = None
    config["status"] = "running"
    save_config(config)

    print("ACTION: CALL_DEV_SIMULATOR")
    print_agent_context(config, {
        "simulator_source_files": config["simulator_source_files"],
        "dev_simulation_log_path": config["dev_simulation_log"],
        "simulator_score_threshold": config.get("simulator_score_threshold", 95),
    })


def cmd_after_simulate(config: dict):
    """Simulator完了後"""
    log_path = BASE_DIR / config["dev_simulation_log"]
    if not log_path.exists():
        print("ERROR: dev_simulation_log.md not found. Simulator may have failed.")
        sys.exit(1)

    config["current_phase"] = "ready"
    config["current_iteration"] = 0
    config["consecutive_above_threshold"] = 0
    config["scores"] = []
    config["last_score"] = None
    save_config(config)
    print("STATUS: SIMULATION_COMPLETE")
    print(f"LOG: {config['dev_simulation_log']}")
    print("ACTION: Run 'python orchestrator.py start-iteration' to begin article generation")


def cmd_status(config: dict):
    print("=== Orchestrator Status ===")
    print(json.dumps(config, indent=2, ensure_ascii=False))


def cmd_start_iteration(config: dict):
    if config.get("status") == "complete":
        print("STATUS: ALREADY_COMPLETE")
        return

    n = config["current_iteration"] + 1
    if n > config["max_iterations"]:
        print("STATUS: MAX_ITERATIONS_REACHED")
        config["status"] = "complete"
        save_config(config)
        return

    # ベンチマーク記事をランダムサンプリング（毎回異なる組み合わせ）
    sampled = sample_benchmark_articles(config)
    config["current_benchmark_articles"] = sampled

    setup_iteration_dir(n)
    config["current_iteration"] = n
    config["current_phase"] = "write"
    save_config(config)

    print(f"ACTION: CALL_WRITER")
    print(f"BENCHMARK_SAMPLE: {len(sampled)} articles sampled from {config['benchmark_dir']}")
    print_agent_context(config, {
        "article_output_path": f"iterations/{n}/article.md",
        "style_guide_path": "style_guide.md",
        "anti_patterns_log_path": config["anti_patterns_log"],
        "dev_simulation_log_path": config["dev_simulation_log"],
        "article_purpose": config.get("article_purpose", ""),
        "reader_takeaway": config.get("reader_takeaway", ""),
        "system_role": config.get("system_role", ""),
    })


def cmd_after_write(config: dict):
    n = config["current_iteration"]
    article_path = BASE_DIR / "iterations" / str(n) / "article.md"

    if not article_path.exists():
        print("ERROR: article.md not found. Writer may have failed.")
        sys.exit(1)

    config["current_phase"] = "review"
    save_config(config)

    print(f"ACTION: CALL_REVIEWER")
    print_agent_context(config, {
        "article_path": f"iterations/{n}/article.md",
        "review_output_path": f"iterations/{n}/review.md",
        "benchmark_articles": config["current_benchmark_articles"],
    })


def cmd_after_review(config: dict, score: float):
    n = config["current_iteration"]

    # スコアジャンプ制限: 前回スコアから max_score_jump 以上の上昇を制限
    max_jump = config.get("max_score_jump_per_iteration", 1.0)
    prev_score = config.get("last_score")
    if prev_score is not None and score > prev_score + max_jump:
        capped = prev_score + max_jump
        print(f"SCORE_CAPPED: {score} → {capped} (max jump {max_jump} from {prev_score})")
        score = capped

    config["last_score"] = score
    config.setdefault("scores", []).append({"iteration": n, "score": score})

    # 連続達成カウンターを更新
    consecutive_required = config.get("consecutive_required", 2)
    if score >= config["stop_score"]:
        config["consecutive_above_threshold"] = config.get("consecutive_above_threshold", 0) + 1
    else:
        config["consecutive_above_threshold"] = 0

    save_config(config)

    print(f"SCORE: {score}/10")
    print(f"THRESHOLD: {config['stop_score']}/10")
    print(f"CONSECUTIVE: {config['consecutive_above_threshold']}/{consecutive_required}")

    if config["consecutive_above_threshold"] >= consecutive_required:
        print(f"ACTION: STOP  # {consecutive_required} consecutive scores >= {config['stop_score']}")
        config["status"] = "complete"
        save_config(config)
        return

    if n >= config["max_iterations"]:
        print(f"ACTION: STOP  # max iterations ({config['max_iterations']}) reached")
        config["status"] = "complete"
        save_config(config)
        return

    # Consolidationの判定
    if n == config.get("consolidation_at_iteration"):
        config["current_phase"] = "consolidate"
        save_config(config)
        print(f"ACTION: CALL_CONSOLIDATION  # iteration {n} is consolidation point")
        print_agent_context(config, {
            "style_guide_path": "style_guide.md",
            "consolidation_output_path": f"iterations/{n}/consolidation_report.md",
            "target_lines": 200,
            "instruction": "内容を失わずに文字数を圧縮する。ANTIパターン表は10行以内に削減。重複ルールを統合。",
        })
    else:
        config["current_phase"] = "update"
        save_config(config)
        print(f"ACTION: CALL_STYLE_GUIDE_UPDATER")
        print_agent_context(config, {
            "review_path": f"iterations/{n}/review.md",
            "article_path": f"iterations/{n}/article.md",
            "changelog_output_path": f"iterations/{n}/changelog.md",
            "anti_patterns_log_path": config["anti_patterns_log"],
        })


def cmd_after_update(config: dict):
    config["current_phase"] = "next"
    save_config(config)
    next_n = config["current_iteration"] + 1
    print(f"ACTION: NEXT_ITERATION  # run: python orchestrator.py start-iteration")
    print(f"NEXT_ITERATION: {next_n}")


def cmd_after_consolidate(config: dict):
    n = config["current_iteration"]
    config["current_phase"] = "update"
    save_config(config)
    print(f"ACTION: CALL_STYLE_GUIDE_UPDATER  # after consolidation")
    print_agent_context(config, {
        "review_path": f"iterations/{n}/review.md",
        "article_path": f"iterations/{n}/article.md",
        "changelog_output_path": f"iterations/{n}/changelog.md",
        "anti_patterns_log_path": config["anti_patterns_log"],
        "note": "consolidationの後なので、新規ルール追加より既存ルールの精緻化を優先する",
    })


COMMANDS = {
    "status": cmd_status,
    "simulate": cmd_simulate,
    "after-simulate": cmd_after_simulate,
    "start-iteration": cmd_start_iteration,
    "after-write": cmd_after_write,
    # after-review は score 引数が必要なため main() で直接処理
    "after-update": cmd_after_update,
    "after-consolidate": cmd_after_consolidate,
}

ALL_COMMANDS = list(COMMANDS.keys()) + ["after-review"]


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd not in ALL_COMMANDS:
        print(f"Unknown command: {cmd}")
        print(f"Available: {', '.join(ALL_COMMANDS)}")
        sys.exit(1)

    config = load_config()

    if cmd == "after-review":
        if len(sys.argv) < 3:
            print("ERROR: after-review requires a score argument")
            print("  Usage: python orchestrator.py after-review <score>")
            print("  Example: python orchestrator.py after-review 8.5")
            sys.exit(1)
        try:
            score = float(sys.argv[2])
        except ValueError:
            print(f"ERROR: Invalid score '{sys.argv[2]}' — must be a number (e.g. 8.5)")
            sys.exit(1)
        cmd_after_review(config, score)
    else:
        COMMANDS[cmd](config)


if __name__ == "__main__":
    main()
