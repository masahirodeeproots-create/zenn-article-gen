# Architecture

## システム全体構成図

```
[入力: 受注書 / KOLリスト / 商品情報]
              │
              ▼
┌─────────────────────────────────────────────────────────┐
│              Lead Orchestrator                          │
│  ・モード判定: classic_small (KOL≤3) / thin_large (KOL≥4) │
│  ・フェーズ管理: checkpoint/run_state.json               │
│  ・成果物ゲート: 各フェーズ完了を artifact 存在で判定       │
│  ・run_id プロヴェナンス管理                               │
└─────────────────────────────────────────────────────────┘
   │        │           │           │           │
   ▼        ▼           ▼           ▼           ▼
Phase 1  Phase 1.5   Phase 2     Phase 3     Phase 4
Intake   Product     KOL         Planner    Designer群
(inline)  Research   Research   (subagent)  (subagent×4)
(inline)  (inline)      │
                    KOL Research
                    Aggregator
                    (subagent)
                    ↓kol_research_manifest.json
                    ↓kol_research_summary.md

Phase 4 内部フロー（4回の独立 subagent spawn）:
  4a: Asset Acquisition ─→ source_assets_manifest.json
        │ Gate: source_assets_manifest.json exists
        ▼
  4b: Global Style Generator ─→ campaign_cover.png
                                  title_cover.png
                                  product_main.png
                                  global_assets_manifest.json
        │ Gate: 3画像すべて存在
        ▼
  4c: KOL Creative Worker × KOL数 (並列可)
        → kol_ref_{slug}.png
        → kol_scene0〜4_{slug}.png (9:16 or 4:5 or 16:9)
        → assets_plan_{slug}.json
        │ Gate: 全KOLのassets_plan存在 + run_id一致
        ▼
  4d: Asset Resolver ─→ assets_resolved.json (status=ready)
        │ Gate: status=ready + campaign_cover exists
        ▼

Phase 5-6-7: AgentTeams (Builder → Visualizer → Reviewer)
┌──────────────────────────────────────────────────────┐
│  Builder                                             │
│  ・per_kol_packages.json → data_binding.json         │
│  ・binding_contract.json でスライドタイプ決定           │
│  ・PPTX skeleton 生成                                 │
│        │                                             │
│        ▼                                             │
│  Visualizer                                          │
│  ・skeleton + data_binding + assets_resolved → PPTX  │
│  ・全テキストに solidFill 030303 を設定                 │
│  ・Z-order 保持で画像挿入                              │
│  ・endParaRPr 順序修正                                 │
│  ・update_slide_numbers() 実行                        │
│        │                                             │
│        ▼                                             │
│  Reviewer                                            │
│  ・Tier1 モード固有チェック（13項目）                    │
│  ・Tier2 OQE ルーブリック評価                           │
│        │                                             │
│   REJECT → Fix Loop (max 10回)                        │
│   ・target:data  → Builder 再spawn → Visualizer → Rev │
│   ・target:pptx  → Visualizer 再spawn → Reviewer      │
│        │                                             │
│   APPROVE → Phase 8                                  │
└──────────────────────────────────────────────────────┘
              │
              ▼
Phase 8: Export
→ export_result.json + 納品成果物

[出力: {project}.pptx]
```

## コンポーネント一覧

| コンポーネント | 実行方式 | 主な責務 |
|--------------|---------|---------|
| Orchestrator (Lead) | inline | フェーズ管理・ゲート判定・モード選択 |
| KOL Research Aggregator | subagent | KOL個別調査をmanifest/summaryに圧縮 |
| Planner | subagent | KOL別クリエイティブ戦略・per_kol_packages.json生成 |
| Asset Acquisition | subagent | ロゴ・商品参照画像の取得 |
| Global Style Generator | subagent | campaign_cover / title_cover / product_main 生成 |
| KOL Creative Worker | subagent × KOL数 | KOL固有シーン画像生成（AI画像生成） |
| Asset Resolver | subagent | 全アセット統合 → assets_resolved.json |
| Builder | subagent (AgentTeams) | data_binding.json + PPTX skeleton 生成 |
| Visualizer | subagent (AgentTeams) | PPTX binding適用・画像挿入 |
| Reviewer | subagent (AgentTeams) | 品質ゲート（APPROVE/REJECT判定） |

## データフロー（主要成果物）

```
inputs/
  order_docs/       → intake_summary.md
  kol_list.*        → kol_targets.json

planning/
  intake_packet.json
  kol_targets.json
  per_kol_packages.json       ← Planner 出力（最重要）
  source_assets_manifest.json ← Asset Acquisition
  global_assets_manifest.json ← Global Style Generator
  assets_plan_{slug}.json     ← KOL Creative Worker
  assets_resolved.json        ← Asset Resolver（最終統合）
  data_binding.json           ← Builder（Visualizer入力）

cache/images/
  logos/logo_{brand}.png
  products/product_main.png
  campaign_cover.png
  title_cover.png
  scenes/kol_scene{0-N}_{slug}.png

checkpoint/
  run_state.json    （実行状態・run_id）
  review_verdict.json

output/post-instructions/{project}/
  {project}.pptx    ← 最終成果物
```

## フェーズゲート設計

各フェーズは「必須成果物ファイルが存在するか」を条件に次フェーズへ進む。
不一致（古いrun_idや欠落ファイル）があれば当該フェーズを再実行する。
これにより冪等性を保ちながら部分的な再実行が可能な設計になっている。
