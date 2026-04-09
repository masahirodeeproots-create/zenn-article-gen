---
title: "KOLが増えるほど壊れていくオーケストレーターとどう戦ったか"
emoji: "🔧"
type: "tech"
topics: ["claudecode", "ai", "architecture", "agentteams"]
published: true
---

KOL向けの投稿指示書をPPTXで自動生成するパイプラインを運用しています。受注書とKOLリストを入力すると、リサーチからデッキ生成まで一気通貫で動くものです。3人のKOLでは快調でした。6人に増やした瞬間、5人目のキャプション方向性が1人目のコピーになりました。

KOLが増えるとパイプラインが壊れるのは、実行中の各Phaseが前のPhaseの成果物を「信頼しすぎている」からです。ファイルがあれば中身は正しいと仮定して次に進む。この仮定が3人では成立して、6人では崩壊しました。

## 6人で壊れたこと、そこからPhase 4を4つに割るまで

最初の構成は素朴な直列パイプラインでした。

```python
for phase in [intake, kol_research, creative_plan, asset, build, review]:
    result = run_subagent(phase, inputs=previous_outputs)
```

6人の案件を流したら、5人目と6人目のキャプション方向性が「潤い」と「自然由来」の繰り返しになっていました。Creative Planningの段階で全KOL分のリサーチ結果が1つのSubagentのコンテキストに載っていて、後半のKOLを処理するときに前半の情報が支配的になる。

最初に疑ったのはトークン数です。6人分のプロフィールと過去投稿分析を全部渡しているから長すぎるのだろう、と。要約ステップを挟んでみましたが直りませんでした。要約しても情報量は減るだけで、コンテキスト内での前半偏重は変わらない。問題はトークン数ではなく**コンテキスト分離**の欠如でした。

KOL数に応じてexecution modeを分けました。3人以下なら`classic_small`（Leadが直接処理）、4人以上なら`thin_large`（Leadはhandoffとgate判定に専念）。ただ正直これだけでは品質問題は完全には消えなくて、本当に効いたのはPhase 4の分割です。

画像素材の生成を1つのSubagentに全部任せていたところ、2つの問題が同時に出ました。

1つ目。新しい案件を流したのに、3人目のKOLのシーン画像だけ前の案件のものが混ざっていました。これはキャッシュの問題だと思って調べたんですが、そうではなくて、3人目の画像生成が途中で失敗してスキップされていた。ファイルが存在しないので上書きもされず、前の実行の成果物が残っていました。

2つ目。1つのSubagentで全画像を生成しているので、途中で1人分がコケると後続のKOL全員の画像がない状態で次のPhaseに進んでしまう。

Phase 4（Asset）を4つに分割しました。

```
Phase 4a: Asset Acquisition
  → ロゴ・商品参照画像の取得
  → planning/source_assets_manifest.json を出力

Phase 4b: Global Style Gen
  → campaign_cover(16:9), title_cover(21:9), product_main(9:16)
  → planning/global_assets_manifest.json を出力
  → Gate: 3画像すべての存在を確認

Phase 4c: KOL Creative × KOL数
  → KOL 1名ずつ独立してsubagent spawn
  → 4bのGateをパスしていない場合は起動禁止

Phase 4d: Asset Resolve
  → source + global + per-KOLを統合
  → planning/assets_resolved.json (status=ready) を出力
```

4cがこの分割の核です。KOL 1名につき1つのSubagentなので、1人がコケても他に影響しません。そして4bが完了する前に4cを起動してはいけない。これはGlobal Style（カバー画像のトンマナ）が決まっていない状態でKOLのシーン画像を生成するとスタイルがバラバラになるからで、以前並列化を急いで4bと4cを同時に走らせたとき、KOLごとにまるで別案件のようなビジュアルが出来上がったことがあります。

stale artifact問題（前の実行の成果物が残る問題）には`run_id`で対処しました。

```python
from datetime import datetime, timezone

run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
# checkpoint/run_state.json に保存

# Gate判定
def check_gate(phase_result_path, current_run_id):
    result = load_json(phase_result_path)
    if result.get("run_id") != current_run_id:
        return False  # stale artifact — 再実行
    return True
```

日時ベースの文字列にしたのは、デバッグ時に「いつの実行の成果物か」が一目でわかるからです。UUIDだと見てもわからない。

ここで`run_id`の話をもう少し掘りたいんですが、「ファイルは存在するけど中身が古い」というケースがこのパイプラインでは頻繁に起きます。Phase 4dのasset-resolverが出力する`assets_resolved.json`に`status: partial`と書いてあるのにGateを通過してBuildに進んでしまい、PPTXの表紙が真っ白になったことがあります。ファイルの存在チェックだけではダメで、`status`が`ready`であること、かつ`global_assets`に`campaign_cover`エントリが存在することを見る必要がありました。

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

# 不合格時: global-style-generatorから再実行 → asset-resolverを通し直す
```

「ファイルがある」と「正しいファイルがある」は違います。これはrun_id contractを入れた後でもなお踏んだ罠です。run_idが一致しても、中身のstatusがpartialならそれは使えない。チェックの粒度を上げるたびに「まだ見落としがある」と気づくことの繰り返しでした。

## リサーチ欠損とReadiness Check

Phase 4の話からいったん戻ります。

5人のKOLで回したとき、3人目のKOLだけクリエイティブプランが「フォロワーに響くコンテンツ」としか書いてない。調べたらresearchディレクトリにそのKOLのファイルがなくて、リサーチ自体が失敗していました。マニフェストには5人分のエントリがあるのに実ファイルは3人分。Phase 3に進んでしまったのは、Phase完了判定が「`kol_research_manifest.json`の存在」だけだったからです。

Phase 2→3の遷移にReadiness Checkを入れました。

```python
def check_phase3_readiness(project_dir):
    required_files = {
        "intake_packet":      "planning/intake_packet.json",
        "kol_targets":        "planning/kol_targets.json",
        "product_research":   "research/product_deep_research/summary.json",
        "kol_manifest":       "research/kol_research_manifest.json",
        "kol_summary":        "planning/kol_research_summary.md",
    }
    
    for name, path in required_files.items():
        if not (project_dir / path).exists():
            return False, f"{name} missing"
    
    # マニフェスト内KOL数と実ファイル数の一致
    manifest = load_json(project_dir / "research/kol_research_manifest.json")
    expected = len(manifest["kols"])
    actual = len(list((project_dir / "research/kol_research").glob("*.json")))
    if actual != expected:
        return False, f"KOL research: {actual}/{expected}"
    
    return True, "ok"
```

1件でも欠落があればPhase 3に進まず、該当Phaseを再実行します。`product_research`の項目はここで初めて追加したもので、最初のパイプラインにはProduct Research自体がなかったんですよね。商品の特徴を知らないままKOLへの指示を作ると、全員に同じ「おすすめです」としか書けなくなるので、IntakeとKOL Researchの間にPhase 1.5として追加しました。

Readiness Checkは地味ですが効果は大きかったです。

## Build/Visualize/ReviewをAgentTeamsで閉じる

ここまではPhase間の遷移（前のPhaseの成果物を検証して次に進む）の話でした。もう1つ別系統の問題として、Buildの後のレビュー結果が反映されないまま出力されてしまう問題がありました。

Reviewerが「キャプションのトーンがブリーフと合っていない」と指摘してくれるのに、Build → Visualize → Review → Exportが直列で、REJECTしても巻き戻れない。Orchestrator側でReview結果をハンドリングしてBuilderを再起動する方法も考えましたが、行き来のたびにコンテキストを再構築するのが効率悪すぎます。

AgentTeamsで Phase 5-6-7を1チーム内の閉ループにしました。

```
builder     → data_binding.json + PPTXスケルトン
visualizer  → テキスト・画像のbinding適用
reviewer    → 品質評価

Fix Loop:
  REJECT + target: data → builder再spawn → visualizer → reviewer
  REJECT + target: pptx → visualizer再spawn → reviewer
  APPROVE → Export
  最大10イテレーション（安全弁）
```

これは通常2-3回で収束します。

閉ループを入れてから見えてきたのがcaption-bindingの問題です。data_binding.jsonのキャプションスライドで、KOL Aのスライドに KOL Bの開示タグが入っていたり、市場による開示トークンの違い（JP: `#PR`、US: `#ad`、TH: `#โฆษณา`）が無視されて全部「#ad」になっていたり。builderのプロンプトにShapeマッピングのルールが含まれていなかったのが原因で、`caption-binding-rules.md`をsingle source of truthとして定義し、**builder spawn時に必ず全文を含める**契約にしました。fix loopでの再spawn時も同様です。

:::details Visualizerのフォント色問題
PPTXを開いたらテキストが背景と同化して白くなっているスライドがありました。Visualizerがフォント色を明示設定せずにテキストを流し込んでいたため、テーマカラーの継承で白になっていた。全テキストrunに`030303`をsolidFillで設定し、`_bg`/`_fill`/`_header`/`_label`等のデザインShapeは例外とする修正を入れています。`visible:false`のShapeはテキストを空にしてオフキャンバスへ移動。endParaRPrの順序修正と`update_slide_numbers()`もこのタイミングで追加しました。
:::

最終的なPhase構成はこうなっています。

```
Phase 0:   Initialize
Phase 1:   Intake
Phase 1.5: Product Research
Phase 2:   KOL Research
             → Readiness Check（6項目 + KOLファイル数一致）
Phase 3:   Creative Planning
Phase 4a-d: Asset（4分割、run_id contract）
             → 遷移ゲート（status=ready + campaign_cover + run_id一致）
Phase 5-7: Build / Visualize / Review（AgentTeams fix loop、max 10）
Phase 8:   Export
```

Orchestratorのファイルが膨れすぎたので、責務をmode選択・Phase順序・artifact gateの3つに絞り、各Phaseの手順はsubordinate skillsのspawn packetに押し出しました。

ここまでの設計判断は全部「壊れてから直す」で得たものです。6人で品質が劣化した、前の案件の画像が混ざった、リサーチが欠けたまま進んだ、レビューが反映されなかった。どれも事前には設計できなかった気がします。

Phase 4cでKOLが15人になったらSubagentのspawn上限に引っかかるのか、並列度をどこかで絞る必要があるのかは、まだ検証していません。
