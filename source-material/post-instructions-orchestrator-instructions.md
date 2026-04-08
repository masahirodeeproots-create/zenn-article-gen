# PostInstructions Orchestrator

## Overview

受注済み案件向け PostInstructions mode の canonical orchestrator。
資料 intake から KOL research、creative planning、asset resolution、build/review/export までを
artifact-driven に進める。

この orchestrator は **legacy contract tree や別系統の mode 定義を source of truth にしない**。
Lead は `classic_small` / `thin_large` を判定し、phase gate と handoff を管理する。
Generic planning は `implementation-planning`、実行 state 管理は `plan-execution`
を使う。

## Target

`$ARGUMENTS` を project とし、出力先は:

```text
target: output/post-instructions/{project}/
legacy alias still present during migration: output/post_instructions/{project}/
```

## Execution Modes

- `classic_small`
  - KOL 数が 3 以下
  - Lead が intake / asset 周りの一部を直接処理してよい
- `thin_large`
  - KOL 数が 4 以上、または不明
  - Lead は summary / handoff / gate 判定中心

mode は `checkpoint/run_state.json` に保存する。

## Operating Rules

1. `interaction_policy=autonomous` の task はフェーズ間でユーザー確認を挟まない
2. `interaction_policy=approval_gated` の task は plan approval を 1 回だけ待つ
3. approval 後の execution 中は `interaction-policy.md` の Execution 禁止セクションを適用する
4. `replan_trigger` が発火しない限り execution を止めない
2. handoff は file artifact を正とする
3. Lead は長文本文より `*_phase_result.json` と summary を優先して読む
4. build 後は review / export まで止めない
5. classic_small でも artifact contract は thin_large と揃える

## Preflight

最低限確認する:
- `inputs/order_docs/` または `inputs/project_docs/` が存在する
- `inputs/kol_list.*` または equivalent target source がある
- template contract が参照可能

初期化 / 更新:
- `checkpoint/checkpoint.json`
- `checkpoint/run_state.json`
- `checkpoint/audit_log.yaml`
- `checkpoint/plans/{plan_id}.md`
- `checkpoint/plan_payload.yaml`
- request / session / approval / review state artifacts

初期化:
- request summary を確定する
- checkpoint / run_state / approval / review state の出力先を用意する
- `run_id` を生成する（`datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')` 形式）
- `checkpoint/run_state.json` に `run_id` フィールドを含める

### Generic Plan Initialization

Preflight と execution mode 判定後、`implementation-planning` を使って以下を生成する:

- `output/post-instructions/{project}/checkpoint/plans/postinst-{project}-main.md`
- `output/post-instructions/{project}/checkpoint/plan_payload.yaml`

推奨 payload:

```yaml
execution_mode: classic_small なら inline / thin_large なら subagent_per_task
doc_path: output/post-instructions/{project}/checkpoint/plans/postinst-{project}-main.md
target_units:
  - intake
  - product_research
  - kol_research
  - creative_plan
  - asset_resolution
  - build_visualize
  - review_export
non_goals:
  - unrelated design-system refactor
steps:
  - id: S1
    action: Initialize and intake project inputs
  - id: S2
    action: Run product research
  - id: S3
    action: Run KOL research
  - id: S4
    action: Produce creative planning artifacts
  - id: S5
    action: Resolve assets
  - id: S6
    action: Build and visualize the deck
  - id: S7
    action: Review, export, and close
```

適用:
- plan payload を execution state に反映する

`run_state.execution_mode` は `plan.execution_mode` と同じ意味で扱う。

`interaction_policy=approval_gated` の場合、Phase 3 完了時に:

plan state を `proposed` と `awaiting_plan_approval` に更新する

execution 開始後の control plane は `plan-execution` に従う。

## Phase Model

```text
Phase 0: Initialize
Phase 1: Intake
Phase 1.5: Product Research
Phase 2: KOL Research
Phase 3: Creative Planning
Phase 4: Asset Acquisition / Resolution
Phase 5: Build
Phase 6: Visualize
Phase 7: Review
Phase 8: Export
```

## Stage Dispatch Table

| Stage | Execution kind | Target | Required inputs | Required outputs | Gate |
|---|---|---|---|---|---|
| Phase 1: Intake | inline | See `reference/post-instructions-intake.md` | input docs + KOL list | intake artifacts and `planning/kol_targets.json` | intake packet ready |
| Phase 1.5: Product Research | inline | See `reference/post-instructions-product-research.md` | product targets + intake artifacts | product research summary + phase result | product fact supplementation ready |
| Phase 2: KOL Research | inline | See `reference/post-instructions-kol-research.md` | `planning/kol_targets.json` | KOL manifest + summary + phase result | KOL research bundle ready |
| Phase 3: Creative Planning | subagent | `planner`, spawn_packet: `agents/planner-post-instructions.md` | intake, product, and KOL research artifacts | `planning/per_kol_packages.json`, creative artifacts | creative plan ready |
| **Phase 4a: Asset Acquisition** | subagent | `designer`, spawn_packet: `agents/asset-acquisition.md` | `planning/input_digest.md`, `planning/per_kol_packages.json` | `planning/source_assets_manifest.json`, client logo, product ref | source assets manifest exists |
| **Phase 4b: Global Style Gen** | subagent | `designer`, spawn_packet: `agents/global-style-generator.md` | `planning/source_assets_manifest.json`, `planning/per_kol_packages.json` | `planning/global_assets_manifest.json`, campaign_cover.png, title_cover.png, product_main.png | **campaign_cover + title_cover + product_main が全て存在** |
| **Phase 4c: KOL Creative** | subagent **× KOL数** | `designer`, spawn_packet: `agents/kol-creative-worker.md` (KOL 1名ずつ spawn) | `planning/global_assets_manifest.json`, `planning/per_kol_packages.json`, KOL research | `planning/assets_plan_{slug}.json`, `cache/images/scenes/kol_scene*_{slug}.png` | per-KOL scene images exist |
| **Phase 4d: Asset Resolve** | subagent | `designer`, spawn_packet: `agents/asset-resolver.md` | source + global + per-KOL manifests | `planning/assets_resolved.json` (status=ready) | assets_resolved status=ready + campaign_cover exists |
| Phase 5: Build Prep | subagent | `builder`, spawn_packet: `agents/builder-post-instructions.md` | creative planning, templates, `planning/assets_resolved.json` | data_binding.json, build artifacts, PPTX skeleton | build artifacts ready |
| Phase 6: Visualize | subagent | `visualizer`, spawn_packet: `agents/visualizer-post-instructions.md` | skeleton PPTX, build artifacts, resolved assets | final PPTX with bindings applied | PPTX exists with bindings |
| Phase 7: Review | subagent | `reviewer`, spawn_packet: `agents/reviewer-post-instructions.md` | final PPTX, review criteria | review verdict | reviewer approves or escalates |
| Phase 8: Export | inline | See `reference/post-instructions-export.md` | final PPTX + approval/export-ready status | export checkpoint and delivery artifacts | export artifacts recorded |

## Phase Contracts

### Phase 1: Intake

必須成果物:
- `planning/intake_summary.md`
- `planning/intake_packet.json`
- `planning/kol_targets.json`
- `planning/intake_phase_result.json`

State updates:
- `touch-plan-step S1 -> in_progress / verified`
- `record-verification` for intake artifacts

### Phase 1.5: Product Research

必須成果物:
- `research/product_deep_research/summary.json`
- `research/product_deep_research/phase_result.json`

State updates:
- `touch-plan-step S2 -> in_progress / verified`
- `record-verification` for product research artifacts

### Phase 2: KOL Research

必須成果物:
- `research/kol_research_manifest.json`
- `planning/kol_research_summary.md`
- `research/kol_batch_phase_result.json`

State updates:
- `touch-plan-step S3 -> in_progress / verified`
- `record-verification` for KOL research artifacts

### Phase 2→3 Lead Readiness Check（MUST）

Phase 3 に進む前に Lead が以下を全件チェックする。**1 件でも欠落があれば Phase 3 に進まず、欠落 artifact の再取得を試みる。**

| チェック項目 | 確認方法 | 欠落時のアクション |
|------------|---------|----------------|
| `intake_packet.json` | `planning/intake_packet.json` の存在確認 | Phase 1 を再実行 |
| `kol_targets.json` | `planning/kol_targets.json` の存在確認 | Phase 1 を再実行 |
| Product Research | `research/product_deep_research/summary.json` の存在確認 | Phase 1.5 を再実行 |
| KOL Manifest | `research/kol_research_manifest.json` の存在確認 | Phase 2 を再実行 |
| KOL Research Summary | `planning/kol_research_summary.md` の存在確認 | Phase 2 を再実行 |
| 全 KOL 分 research | manifest 内の KOL 数と research ファイル数の一致 | 欠落 KOL の research を再実行 |

**全チェック PASS 後のみ** Phase 3 へ進む。

### Phase 3: Creative Planning

必須成果物:
- KOL 別 creative planning artifact
- `planning/phase3_handoff.json`

Board updates:
- `touch-plan-step S4 -> in_progress / verified`
- `record-review --stage spec` when planning artifacts are coherent
- `record-verification` for creative planning artifacts

Approval boundary:
- `interaction_policy=approval_gated` の場合、Phase 3 完了時に approval packet を生成し、承認後にのみ Phase 4 へ進む

### Phase 4: Asset Acquisition / Resolution

**Phase 4 は 4 回の独立した designer subagent spawn で構成される（1 回の spawn で全部やるのは禁止）:**

```
Step 4a: designer + agents/asset-acquisition.md
  → ロゴ・商品参照画像を取得
  → planning/source_assets_manifest.json を出力
  → Gate: source_assets_manifest.json exists AND contains current run_id

Step 4b: designer + agents/global-style-generator.md
  → campaign_cover (16:9) + title_cover (21:9) + product_main (9:16) を生成
  → planning/global_assets_manifest.json を出力
  → Gate: campaign_cover.png + title_cover.png + product_main.png が全て存在 AND global_assets_phase_result.json の run_id == current run_id

Step 4c: designer + agents/kol-creative-worker.md × KOL数
  → KOL 1名ずつ独立して spawn（並列可）
  → 各 KOL の scene 画像 4 枚 + KOL reference image を生成
  → Gate: 全 KOL の assets_plan_{slug}.json が存在 AND 各ファイルの run_id == current run_id
  → **4b の Gate をパスしていない場合は 4c を起動してはならない**

Step 4d: designer + agents/asset-resolver.md
  → source + global + per-KOL asset を統合
  → planning/assets_resolved.json (status=ready) を出力
  → Gate: assets_resolved status=ready + campaign_cover exists + run_id == current run_id
```

**禁止事項:**
- 4a-4d を 1 回の designer spawn でまとめて実行すること
- 4c を global_assets_manifest.json なしで起動すること
- Lead が assets_resolved.json を手書きすること（4d の designer が生成する）

必須成果物:
- `planning/source_assets_manifest.json`
- `planning/global_assets_manifest.json`
- `planning/assets_resolved.json`
- `planning/phase4_handoff.json`

State updates:
- `touch-plan-step S5 -> in_progress / verified`
- `record-verification` for asset resolution artifacts

**Phase 5-6 への遷移ゲート（必須確認）**:
`asset-resolver-post-instructions` 完了後、以下を確認してから Build に進む:
- `planning/assets_resolved.json` の `status` が `ready` であること
- `planning/assets_resolved.json` の `global_assets` に `campaign_cover` エントリが存在すること

上記を満たさない場合（`status: partial` / `campaign_cover` 欠落）は Build を開始せず:
1. `warnings` の内容を確認して欠落 asset の原因を特定する
2. `global-style-generator-post-instructions` を再実行する
3. `asset-resolver-post-instructions` を再実行してから Phase 5-6 に進む

### Run ID Contract

各 Phase 4 spawn packet の出力 `*_phase_result.json` に `run_id` フィールドを含める。
Gate 判定時は `checkpoint/run_state.json` の `run_id` と出力の `run_id` が一致することを確認する。
不一致の場合、stale artifact として無視し、該当 Phase を再実行する。

### Phase 5-6: Build / Visualize

必須成果物:
- `planning/build_spec.json`
- `planning/data_binding.json`
- `output/post-instructions/{project}/{project}.pptx`
- `planning/phase5_handoff.json`

State updates:
- `touch-plan-step S6 -> in_progress / verified`
- `record-review --stage quality` for build readiness
- `record-verification` for `build_spec.json`, `data_binding.json`, and PPTX

#### Caption スライド binding ルール

**builder spawn プロンプトパケットには `.claude/skills/post-instructions-orchestrator/knowledge/caption-binding-rules.md` の全内容を必ず含めること。Fix Loop で builder を再 spawn する場合も同様。**

詳細ルール・Shape マッピング・市場別 disclosure token は `knowledge/caption-binding-rules.md` を single source of truth とする。

### Phase 7: Review

必須成果物:
- `checkpoint/review_verdict.json`
- `review/rubric_results.json`
- `checkpoint/phase7_handoff.json`

### Reviewer Spawn Template

reviewer を spawn する際は必ず以下のプロンプトを使うこと:

```
Read .claude/skills/post-instructions-orchestrator/agents/reviewer-post-instructions.md for full review instructions.
Project: output/post-instructions/{project}
PPTX: output/post-instructions/{project}/{project}.pptx
Brief: planning/context_pack.json
This is review iteration #{reviewer_iterations + 1}.
```

State updates:
- `touch-plan-step S7 -> in_progress`
- `record-review --stage final`

### Phase 8: Export

必須成果物:
- export link or export artifact summary
- `checkpoint/export_result.json`

State updates:
- `touch-plan-step S7 -> verified`
- `record-verification` for export result
- close decision uses runtime review/verification state as the control-plane summary

### Phase 5-6-7: Build, Visualize & Review (AgentTeams)

**Phase 5-6-7 は AgentTeams で実行する。Builder → Visualizer → Reviewer を 1 チーム内で管理する。**

```
AgentTeams 構成:
  - builder (spawn_packet: agents/builder-post-instructions.md)
    → data_binding.json + PPTX skeleton を生成

  - visualizer (spawn_packet: agents/visualizer-post-instructions.md)
    → skeleton PPTX + data_binding.json + assets_resolved.json を入力
    → テキスト書き込み時に必ず明示的な黒色(030303)を設定
    → endParaRPr 順序修正を binding 最終ステップとして実行
    → binding 適用後に update_slide_numbers() を実行

  - reviewer (spawn_packet: agents/reviewer-post-instructions.md)
    → acceptance criteria + quality-gate に基づいて PPTX を評価
    → REJECT の場合: fix_targets に基づいて builder or visualizer を再 spawn

Fix Loop (AgentTeams 内で実行):
  1. REJECT + target: data → builder Teammate を再 spawn → visualizer → reviewer
  2. REJECT + target: pptx → visualizer Teammate を再 spawn → reviewer
  3. APPROVE → Phase 8 へ進む
  最大 iteration: 10
```

### Visualizer Spawn Template

visualizer を spawn する際は必ず以下のプロンプトを使うこと:

```
Read .claude/skills/post-instructions-orchestrator/agents/visualizer-post-instructions.md for full visualization instructions.
Project: output/post-instructions/{project}
PPTX: output/post-instructions/{project}/{project}.pptx
DataBinding: output/post-instructions/{project}/planning/data_binding.json
Assets: output/post-instructions/{project}/planning/assets_resolved.json

CRITICAL: テキスト書き込み時に必ず明示的なフォント色を設定すること。
テーマ継承色（inherited）は使用禁止。全てのテキスト run に solidFill で 030303 を設定する。
ただし _bg / _fill / _header / _label / _Label / _Breadcrumb を含む Shape は例外とし、テンプレートのフォント色を維持すること。
visible:false の Shape はテキストを空にしてからオフキャンバスに移動すること（この処理はラベル例外より優先）。
endParaRPr 順序修正を binding 最終ステップとして実行すること。
binding 適用後に update_slide_numbers() を実行すること。
```

**AgentTeams で実行する。sequential subagent spawn は使用しない。**

最大 iteration: 10

## Output Contract

最終成果物:
- `output/post-instructions/{project}/{project}.pptx`
- `output/post-instructions/{project}/planning/data_binding.json`
- `output/post-instructions/{project}/checkpoint/review_verdict.json`
- `output/post-instructions/{project}/checkpoint/export_result.json`

run_state:

```json
{
  "project": "{project}",
  "mode": "post-instructions",
  "execution_mode": "classic_small|thin_large",
  "status": "running|complete|escalated",
  "current_phase": "phase1|phase2|phase3|phase4|phase5|phase6|phase7|phase8"
}
```

## Maintainability Rule

- Keep this orchestrator focused on mode selection, phase order, and artifact gates.
- Push phase-specific procedure into subordinate skills instead of growing this file.

## Absorbed Stage References

The following pipeline-internal sub-skills have been consolidated into this orchestrator.
Their execution contracts are preserved as reference docs under `reference/`:

| Phase | Reference doc | Original skill |
|-------|--------------|----------------|
| Phase 1: Intake | `reference/post-instructions-intake.md` | `post-instructions-intake` (tier2, removed) |
| Phase 1.5: Product Research | `reference/post-instructions-product-research.md` | `post-instructions-product-research` (tier2, removed) |
| Phase 2: KOL Research | `reference/post-instructions-kol-research.md` | `post-instructions-kol-research` (tier2, removed) |
| Phase 8: Export | `reference/post-instructions-export.md` | `post-instructions-export` (tier2, removed) |

KOL manifest schema: `knowledge/kol-manifest-schema.md`

## Self-Check

1. `classic_small` / `thin_large` を state に保存している
2. Lead が長文 raw research を抱え込んでいない
3. phase handoff を file で残している
4. legacy contract tree や重複 mode 定義に依存していない
5. export まで contract が閉じている
