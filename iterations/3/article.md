---
title: "KOLが増えるほど壊れていくオーケストレーターとどう戦ったか"
emoji: "🔧"
type: "tech"
topics: ["claudecode", "ai", "architecture", "agentteams"]
published: true
---

KOL向けの投稿指示書をPPTXで自動生成するパイプラインを運用しています。受注書とKOLリストを入力すると、リサーチからデッキ生成まで一気通貫で動くものです。3人のKOLでは快調でした。6人に増やした瞬間、5人目のキャプション方向性が1人目のコピーになりました。

パイプラインが壊れるのは、各Phaseが前のPhaseの成果物を「ファイルがあれば正しい」と信頼しているからです。この仮定は3人では成立して、6人では崩壊しました。

## 6人で壊れたこと、そこからPhase 4を4つに割るまで

最初の構成は直列パイプラインです。

```python
for phase in [intake, kol_research, creative_plan, asset, build, review]:
    result = run_subagent(phase, inputs=previous_outputs)
```

6人の案件で、5人目と6人目のキャプション方向性が「潤い」と「自然由来」の繰り返しになっていました。全KOL分のリサーチ結果が1つのSubagentのコンテキストに載っている状態でCreative Planningを実行すると、後半のKOLで前半の情報が支配的になります。

最初に疑ったのはトークン数です。6人分のプロフィールと過去投稿分析が長すぎるのだろうと。要約ステップを挟んでみたんですが直りませんでした。要約しても前半偏重は変わらない。問題はトークン数ではなく**コンテキスト分離**の欠如でした。

KOL数に応じて`classic_small`（3人以下、Leadが直接処理）と`thin_large`（4人以上、Leadはhandoffとgate判定のみ）を分けました。ただこれだけでは後半KOLの品質問題は完全には消えなくて、本当に効いたのはPhase 4の分割です。

画像素材の生成を1つのSubagentに全部任せていたら、2つの壊れ方が同時に出ました。

新しい案件なのに、3人目のKOLのシーン画像だけ前の案件のものが混ざっている。調べたら3人目の画像生成が途中で失敗してスキップされていて、前の実行の成果物がそのまま残っていました。キャッシュの問題だと思って1時間くらい無駄にしたのが本当に悔しかったです。単に「生成に失敗したファイルは存在しない → 古いファイルが残る」という話でした。

もう1つ。1つのSubagentで全画像を生成しているので、途中で1人分がコケると後続のKOL全員の画像がないまま次のPhaseに進んでしまう。

Phase 4を4つに分割しました。

```
Phase 4a: Asset Acquisition
  → ロゴ・商品参照画像を取得
  → planning/source_assets_manifest.json

Phase 4b: Global Style Gen
  → campaign_cover(16:9), title_cover(21:9), product_main(9:16)
  → planning/global_assets_manifest.json
  → Gate: 3画像の存在確認

Phase 4c: KOL Creative × KOL数
  → KOL 1名ずつ独立してsubagent spawn
  → 4bのGateパス前は起動禁止

Phase 4d: Asset Resolve
  → 全アセットを統合
  → planning/assets_resolved.json (status=ready)
```

4cがこの分割の核です。KOL 1名につき1つのSubagentを起動します。1人がコケても他に影響しません。

4bが完了する前に4cを起動してはいけません。Global Style（カバー画像のトンマナ）が未定の状態でKOLのシーン画像を作ると、スタイルがバラバラになります。以前並列化を急いで4bと4cを同時に走らせたとき、KOLごとにまるで別案件みたいなビジュアルになりました。あれは笑ってしまいましたけど、納品できるものではなかったです。

### stale artifactとrun_id、そしてstatusの罠

前の実行の成果物が残る問題（stale artifact）には`run_id`で対処しました。

```python
from datetime import datetime, timezone

run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
# checkpoint/run_state.json に保存

def check_gate(phase_result_path, current_run_id):
    result = load_json(phase_result_path)
    if result.get("run_id") != current_run_id:
        return False  # stale
    return True
```

UUIDではなく日時ベースにしたのは、デバッグ時に「いつの実行か」が一目でわかるからです。

ここで終わりだと思うでしょう。終わりませんでした。

`run_id`を入れた後でも、campaign_coverの生成に失敗した案件でBuildに進んでしまい、PPTXの表紙が真っ白になったことがあります。`assets_resolved.json`を開いたら`status: partial`と書いてある。`run_id`は一致している。Gate判定がファイルの存在と`run_id`の一致しか見ていなくて、`status`フィールドを見ていませんでした。

なんでこうなるかというと、Gate判定を書くときに「チェックすべき項目」を最初から網羅的にリストアップできないからです。成果物のフォーマットが変わるたびにGateの検証項目も増える。自分のパイプラインで同じような「ファイルはあるけど中身がおかしい」問題を踏んだことがある人は多いんじゃないでしょうか。

```python
def check_build_gate(project_dir):
    resolved = load_json(project_dir / "planning/assets_resolved.json")
    
    if resolved["status"] != "ready":
        return False
    if "campaign_cover" not in resolved.get("global_assets", {}):
        return False
    if resolved.get("run_id") != current_run_id:
        return False
    
    return True
# 不合格 → global-style-generatorから再実行 → asset-resolverを通し直す
```

`status`が`ready`であること、`campaign_cover`エントリの存在、`run_id`の一致。この3つを全部見てようやくBuildに進めます。チェックの粒度を上げるたびに「まだ見落としがある」と気づく繰り返しでした。

## リサーチが欠けたままPhase 3に進んでいた

Phase 4の話から戻ります。

5人のKOLで回したとき、3人目だけクリエイティブプランが「フォロワーに響くコンテンツ」としか書いてない。researchディレクトリを見たらそのKOLのファイルがない。マニフェストには5人分あるのにresearchファイルは3人分。Phase完了判定が「マニフェストの存在」だけだったので素通りしていました。

Phase 2→3にReadiness Checkを入れました。

```python
def check_phase3_readiness(project_dir):
    required = {
        "intake_packet":      "planning/intake_packet.json",
        "kol_targets":        "planning/kol_targets.json",
        "product_research":   "research/product_deep_research/summary.json",
        "kol_manifest":       "research/kol_research_manifest.json",
        "kol_summary":        "planning/kol_research_summary.md",
    }
    for name, path in required.items():
        if not (project_dir / path).exists():
            return False, f"{name} missing"

    manifest = load_json(project_dir / "research/kol_research_manifest.json")
    expected = len(manifest["kols"])
    actual = len(list((project_dir / "research/kol_research").glob("*.json")))
    if actual != expected:
        return False, f"KOL research: {actual}/{expected}"
    return True, "ok"
```

1件でも欠落があればPhase 3に進まない。`product_research`の項目は後から追加したもので、最初のパイプラインにはProduct Research自体がありませんでした。商品の特徴を知らないまま指示書を作ると、全KOLに「おすすめです」しか書けなくなります。

## Build/Visualize/ReviewをAgentTeamsで閉じる

ここまではPhase間の遷移ゲートの話でした。もう1つ、Buildの後のレビュー結果が反映されない問題がありました。

Reviewerが「キャプションのトーンがブリーフと合っていない」と指摘してくれるのに、Build → Visualize → Review → Exportが直列で、REJECTしても巻き戻れない。AgentTeamsでPhase 5-6-7を1チーム内の閉ループにしました。

```python
# AgentTeams fix loop（擬似コード）
team = AgentTeam(builder, visualizer, reviewer)

for iteration in range(MAX_FIX_ITERATIONS):  # max 10
    if iteration == 0:
        team.run(builder)
    
    team.run(visualizer)
    verdict = team.run(reviewer)
    
    if verdict.status == "APPROVE":
        break
    elif verdict.fix_target == "data":
        team.run(builder)  # data_binding.jsonに問題 → builderから
    elif verdict.fix_target == "pptx":
        pass  # PPTX上の問題 → visualizerから再実行
else:
    escalate_to_human()
```

通常2-3回で収束します。10回は安全弁です。

この閉ループで見えてきたのがcaption-bindingの問題です。KOL Aのスライドに KOL Bの開示タグが入っていたり、市場による開示トークンの違い（JP: `#PR`、US: `#ad`、TH: `#โฆษณา`）が無視されて全部「#ad」になっていたり。builderのプロンプトにShapeマッピングのルールが含まれていなかったのが原因で、`caption-binding-rules.md`を**single source of truth**として定義し、builder spawn時に必ず全文を含める契約にしました。

:::details Visualizerのフォント色問題
PPTXのテキストが背景と同化して白くなるスライドがありました。Visualizerがフォント色を明示設定していなかったため、テーマカラーの継承で白になっていた。全テキストrunに`030303`をsolidFillで設定、`_bg`/`_fill`/`_header`/`_label`等のデザインShapeは例外。`visible:false`のShapeはテキストを空にしてオフキャンバスへ。endParaRPr順序修正と`update_slide_numbers()`も同タイミングで追加。地味な修正ですがこれがないとデッキが見た目として成立しません。
:::

最終的なPhase構成です。

```
Phase 0:   Initialize
Phase 1:   Intake
Phase 1.5: Product Research
Phase 2:   KOL Research
             → Readiness Check（6項目 + KOLファイル数一致）
Phase 3:   Creative Planning
Phase 4a-d: Asset（4分割、run_id + status + campaign_cover）
Phase 5-7: Build / Visualize / Review（AgentTeams、max 10）
Phase 8:   Export
```

Orchestratorの責務はmode選択・Phase順序・artifact gateの3つだけにして、各Phaseの手順はsubordinate skillsのspawn packetに分離しています。

ここまでの設計判断は全部「壊れてから直す」で得たものです。Phase 4cでKOLが15人になったらSubagentのspawn上限に引っかかるのか、どこかで並列度を絞る必要があるのかは検証していません。Phase 4b→4cの依存関係が正しく機能しているかのテストも、実案件でしか確認できていないので、エッジケースでどうなるかはわかりません。
