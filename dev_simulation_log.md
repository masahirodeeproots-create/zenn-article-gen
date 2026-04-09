# Development Log: post-instructions-orchestrator

## Round 1: 初期要件

👤 Human:
受注済み案件のKOL向け投稿指示書を自動で作りたいんですよね。今はGoogleスライドで手作業で作ってるんですけど、KOLごとにキャプション方向性とかシーン構成とか全部変えないといけなくて、3人分で半日くらいかかってます。PPTXで出力できるようにしたいです。

案件の入力は受注書とKOLリストがあって、それを食わせたらリサーチからデッキ生成まで一気通貫でやってほしいです。

🤖 Claude:
なるほど、投稿指示書の自動生成パイプラインですね。整理すると:

1. 入力: 受注書 + KOLリスト
2. 処理: リサーチ → プランニング → デッキ生成
3. 出力: PPTX（KOLごとにカスタマイズされたスライド）

まず全体をシンプルな直列パイプラインで設計します:

```
Phase 1: Intake（受注書パース + KOLリスト読み込み）
Phase 2: KOL Research（各KOLの調査）
Phase 3: Creative Planning（KOLごとの方向性策定）
Phase 4: Asset（画像素材の取得・生成）
Phase 5: Build（PPTX生成）
Phase 6: Review（品質チェック）
```

オーケストレーターが各Phaseを順番に呼んでいく形です。各PhaseはSubagentとして実行して、成果物をファイルで渡していきます。

```python
# orchestrator pseudocode
for phase in [intake, kol_research, creative_plan, asset, build, review]:
    result = run_subagent(phase, inputs=previous_outputs)
    if not result.success:
        raise PhaseError(phase)
```

Intake成果物として `intake_summary.md` と `kol_targets.json` を出力、それをKOL Researchに渡す、という流れでどうでしょう？

✅ Result: 6フェーズの直列パイプライン構成。各フェーズがsubagentとして動き、ファイルベースで成果物を渡す基本設計。

---

## Round 2: KOLが増えると後半のKOLがおかしい

👤 Human:
3人のKOLで試したらいい感じだったんですけど、別の案件で6人のKOLでやったら後半のKOLの指示がおかしくなりました。5人目と6人目のキャプション方向性が1人目とほぼ同じになってて、「潤い」と「自然由来」を繰り返してるだけでした。あと処理もめちゃくちゃ遅くなりました。

🤖 Claude:
6人分のKOLリサーチ結果とクリエイティブプランを全部コンテキストに載せると、後半でコンテキストが溢れて前半の情報を繰り返してしまうのかもしれません。

最初に思ったのはコンテキストウィンドウの上限に近づいているのかなと。全KOLのリサーチを1つのsubagentに渡してるので、6人分だとかなりの量になりますね。

対策として、KOL数に応じて実行モードを分けましょう:

```python
if len(kol_list) <= 3:
    mode = "classic_small"  # Leadが直接処理
else:
    mode = "thin_large"     # subagent分割
```

`classic_small`はLeadがintakeやasset周りを直接やる。`thin_large`はLeadがsummaryとhandoffとgate判定に徹して、各フェーズは必ずsubagentに投げる。

👤 Human:
あー、でもそれだけで後半のKOLの品質って直ります？モードを分けても結局クリエイティブプランニングのところでは全KOL分見てるんじゃないですか？

🤖 Claude:
鋭いですね。実はクリエイティブプランニングの段階では全KOL分の情報を見る必要があるので、そこは避けられません。でも問題を切り分けると:

1. **リサーチ段階**: 各KOLのリサーチは独立なので並列化できる
2. **プランニング段階**: 全KOL横断で見る必要がある（ここが詰まるポイント）
3. **アセット生成段階**: KOLごとに独立

プランニングは`planner`というsubagentにまとめて任せますが、成果物として`per_kol_packages.json`というKOL別の計画パッケージを出力させます。その後のアセット生成は各KOLを独立したsubagentで処理すれば、コンテキスト問題は解消するはずです。

```json
// planning/per_kol_packages.json
{
  "kol_packages": [
    {
      "slug": "tanaka_beauty",
      "caption_direction": "...",
      "scene_composition": "...",
      "talking_points": ["..."]
    }
  ]
}
```

✅ Result: `classic_small` / `thin_large` の2モード導入。KOL数3以下は直接処理、4以上はsubagent分割。クリエイティブプランの成果物としてKOL別パッケージを出力する設計。

---

## Round 3: 画像素材が全部前の案件のまま

👤 Human:
新しい案件を流したら、カバー画像とかシーン画像が前の案件のものが混ざってました。キャンペーンカバーは新しくなってるのに、KOL3人目のシーン画像だけ前のが残ってるっぽいです。あと画像生成を全部1つのsubagentでやらせてるせいか、途中でコケて最後のKOLの画像がないまま次のフェーズに進んでました。

🤖 Claude:
これは2つ問題がありますね。

1つ目: 前の案件の画像が残っている問題。これはキャッシュが効いてしまっているのか...いや、ファイルパスが同じだと上書きされるはずですが、3人目だけ前のが残っているということは、3人目の画像生成が失敗してスキップされた可能性があります。

2つ目: 1つのsubagentで全画像を生成しているので、途中で失敗すると後続が全部抜ける。

対策として、Phase 4（Asset）を分割します:

```
Phase 4a: Asset Acquisition（ロゴ・商品参照画像を取得）
Phase 4b: Global Style Gen（カバー画像 + タイトルカバー + 商品メイン画像）
Phase 4c: KOL Creative（KOL 1名ずつ独立してspawn）
Phase 4d: Asset Resolve（全アセットを統合して最終マニフェスト生成）
```

重要なのは4cで、KOL1名ずつ別のsubagentを起動します。1人がコケても他に影響しない。

👤 Human:
分割はいいんですけど、前の案件の画像が残る問題はどうするんですか？

🤖 Claude:
あ、そうでした。stale artifact問題ですね。各Phase 4のsubagentが出力する`*_phase_result.json`に`run_id`を含めるようにして、Gate判定時に現在の`run_id`と一致するかチェックします。

```python
# run_id生成
run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')

# checkpoint/run_state.jsonに保存
{"run_id": "20260409T120000Z", ...}

# Gate判定
def check_gate(phase_result_path, current_run_id):
    result = load_json(phase_result_path)
    if result.get("run_id") != current_run_id:
        # stale artifact — 再実行
        return False
    return True
```

不一致の場合はstale artifactとして無視し、そのPhaseを再実行します。これで前回の残骸に騙されなくなります。

あと、4bが完了する前に4cを起動してはいけないという依存関係もあります。4cはglobal_assets_manifest.jsonがないと、KOLのシーン画像のスタイルが統一されないので。

✅ Result: Phase 4を4a/4b/4c/4dに分割。run_id contractでstale artifact検出。4b→4cの依存関係を明示。KOLごとに独立subagent spawn。

---

## Round 4: リサーチが足りないまま進んでしまう

👤 Human:
5人のKOLで回したら、3人目のKOLだけクリエイティブプランが妙に薄いんです。キャプション方向性が「フォロワーに響くコンテンツ」みたいな抽象的なことしか書いてなくて。調べてみたらそのKOLのリサーチ自体が失敗してたみたいで、research/ にファイルがありませんでした。なのにPhase 3に進んでました。

🤖 Claude:
Phase 2（KOL Research）が部分的に失敗しているのにPhase 3に進んでしまっている。これは大きな問題ですね。

最初はPhase 2の完了判定が「kol_research_manifest.jsonが存在すればOK」になっているのが原因かと思いましたが、マニフェスト自体は5人分あるのにresearchファイルが欠けているということは、マニフェストの存在だけでは不十分です。

Phase 2→3の遷移時にReadiness Checkを入れましょう:

```python
# Phase 2→3 Lead Readiness Check
checks = [
    ("intake_packet.json", "planning/intake_packet.json"),
    ("kol_targets.json", "planning/kol_targets.json"),
    ("Product Research", "research/product_deep_research/summary.json"),
    ("KOL Manifest", "research/kol_research_manifest.json"),
    ("KOL Research Summary", "planning/kol_research_summary.md"),
]

# 全KOL分のresearchファイル数チェック
manifest = load_json("research/kol_research_manifest.json")
kol_count = len(manifest["kols"])
research_files = glob("research/kol_research/*.json")
if len(research_files) != kol_count:
    # 欠落KOLのresearchを再実行
    missing = find_missing_kols(manifest, research_files)
    rerun_kol_research(missing)
```

1件でも欠落があればPhase 3に進まず、欠落artifactの再取得を試みます。

👤 Human:
ちなみに商品調査のフェーズがないんですけど、商品の特徴とかもリサーチしてほしいんですよね。KOLのことだけじゃなくて、この商品の何がすごいのかが指示書にちゃんと入っていてほしいです。

🤖 Claude:
あ、それは確かに抜けていました。Phase 1（Intake）とPhase 2（KOL Research）の間にProduct Researchを入れます。Phase 1.5として:

```
Phase 1: Intake
Phase 1.5: Product Research  ← NEW
Phase 2: KOL Research
Phase 3: Creative Planning
...
```

成果物は `research/product_deep_research/summary.json` と `phase_result.json`。商品の特徴・差別化ポイント・訴求軸をまとめて、Phase 3のCreative Planningに渡します。

Readiness Checkにもこれを追加します。

✅ Result: Phase 2→3のReadiness Check導入（6項目の全件チェック）。Phase 1.5としてProduct Researchを追加。欠落時は該当Phaseを再実行。

---

## Round 5: PPTXのテキストが見えない

👤 Human:
デッキ自体は生成されるようになったんですけど、PPTXを開いたらテキストが全部白になってて背景と同化して見えないスライドがあります。あと最後のページ番号が全部「1」になってます。

🤖 Claude:
テキストが白になっている...テンプレートのテーマカラーを継承しているのが原因かもしれません。PPTXのテーマ設定で明るい色が定義されていると、solidFillを明示的に設定していないテキストは白になる場合があります。

最初はテンプレート側の問題かと思って調べたんですが、よく見るとテンプレートのプレースホルダーでは色が正しく表示されています。Visualizer（テキスト書き込み担当）が色を設定せずにテキストを流し込んでいるのが原因ですね。

修正: 全テキストrunにsolidFillで`030303`（ほぼ黒）を明示的に設定します。テーマ継承色（inherited）は使用禁止。

```python
# Visualizer binding rule
for run in paragraph.runs:
    run.font.color.rgb = RGBColor(0x03, 0x03, 0x03)  # 明示的にほぼ黒
```

ただし例外があります。`_bg` / `_fill` / `_header` / `_label` 等を含むShapeはテンプレートのフォント色を維持。これらはデザイン要素なので色を上書きすると壊れます。

ページ番号はbinding適用後に`update_slide_numbers()`を実行すれば直ります。

👤 Human:
あとなんか`visible:false`って設定されてるShapeがスライドの端っこに見えてるんですけど。

🤖 Claude:
`visible:false`のShapeはテキストを空にしてからオフキャンバスに移動する必要があります。テキストが残っていると透明のつもりでも表示されてしまうことがある。この処理はラベル例外より優先です。

あとendParaRPr（段落末の書式設定）の順序問題もありました。フォント色の設定順序が正しくないと、次の段落に設定が漏れることがあります。endParaRPr順序修正をbinding最終ステップとして実行するようにします。

✅ Result: Visualizerのフォント色ルール確立（030303明示指定、例外Shape定義）。visible:false処理。endParaRPr順序修正。update_slide_numbers()。

---

## Round 6: Reviewerが問題を見つけてもそのまま出力されてしまう

👤 Human:
Reviewerが「キャプションのトーンが案件のブリーフと合ってない」ってちゃんと指摘してくれてるのに、そのまま最終PPTXとして出力されちゃうんですよね。レビュー結果を反映する仕組みがないんですか？

🤖 Claude:
確かに今の構造だと Build → Visualize → Review → Export が直列で、ReviewがREJECTしても戻れないですね。

最初はReviewerの出力を受けてOrchestratorが条件分岐すれば...と思ったんですが、Builder→Visualizer→Reviewerの行き来をOrchestrator側で管理すると、毎回コンテキストの再構築が必要になって効率が悪いです。

AgentTeamsを使って、Phase 5-6-7を1チーム内で管理しましょう:

```
AgentTeams構成:
  - builder → data_binding.json + PPTXスケルトン
  - visualizer → テキスト・画像のbinding適用
  - reviewer → 品質評価

Fix Loop:
  REJECT + target: data → builderを再spawn → visualizer → reviewer
  REJECT + target: pptx → visualizerを再spawn → reviewer
  APPROVE → Phase 8 (Export)へ

最大iteration: 10
```

ReviewerがREJECTした場合、`fix_targets`に基づいてbuilderかvisualizerを再spawnする。データが問題ならbuilderから、PPTX上の問題ならvisualizerから。APPROVEされるまでループします。

👤 Human:
10回もループしたら永遠に終わらないんじゃないですか？

🤖 Claude:
10回は上限であって、通常は2-3回で収束します。10回到達した場合はescalateして人間に判断を委ねます。これは安全弁です。

✅ Result: AgentTeamsによるBuild→Visualize→Reviewのfix loop導入。REJECTのtarget種別に応じた再spawn。最大10イテレーション。

---

## Round 7: data_bindingのキャプション欄に間違ったKOLのデータが入る

👤 Human:
fix loopは動くようになったんですけど、今度はdata_binding.jsonのキャプションスライドで、KOL Aのスライドなのに KOL Bの開示タグが入ってたりします。あと市場によって「#PR」とか「#広告」とか開示トークンが違うはずなのに全部「#ad」になってます。

🤖 Claude:
キャプションスライドのbindingルールが明確じゃないんですね。

調べてみると、キャプションスライドはShapeの名前でKOL・市場・コンテンツタイプをマッピングしているんですが、そのルールがbuilderのプロンプトにちゃんと含まれていませんでした。

`caption-binding-rules.md`というナレッジファイルを作って、Shapeマッピングと市場別開示トークンを定義します:

```markdown
## 市場別disclosure token
- JP: #PR / #タイアップ
- US/EN: #ad / #sponsored
- TH: #โฆษณา
- VN: #quảngcáo

## Shape mapping
- caption_text_{slug}: そのKOLのキャプション本文
- disclosure_{slug}: そのKOLの開示タグ
- scene_image_{n}_{slug}: そのKOLのn番目シーン画像
```

重要なのは、**builderをspawnするときに必ずこのファイルの全内容をプロンプトに含める**こと。fix loopで再spawnする場合も同様です。

✅ Result: caption-binding-rules.mdをsingle source of truthとして定義。builder spawnプロンプトに必ず含める契約。市場別開示トークンとShapeマッピングを明文化。

---

## Round 8: アセットが足りないまま Build に進んでしまう

👤 Human:
campaign_coverが生成に失敗してた案件で、カバーなしのままBuildに進んで、PPTXの表紙が真っ白になってました。assets_resolved.jsonを見たら`status: partial`になってるのに通過してます。

🤖 Claude:
Phase 4d（Asset Resolve）の後のGate判定が甘いですね。`assets_resolved.json`が存在するだけでGate通過させてしまっている。

Phase 5-6への遷移ゲートを厳格化します:

```python
# Phase 5-6遷移ゲート
def check_build_readiness():
    resolved = load_json("planning/assets_resolved.json")
    
    # statusチェック
    if resolved["status"] != "ready":
        return False, "status is not ready"
    
    # campaign_cover存在チェック
    global_assets = resolved.get("global_assets", {})
    if "campaign_cover" not in global_assets:
        return False, "campaign_cover missing"
    
    return True, "ok"

# 不合格時のリカバリ
if not ready:
    # 1. warningsの内容を確認して原因特定
    # 2. global-style-generatorを再実行
    # 3. asset-resolverを再実行してからBuildへ
```

`status: partial`や`campaign_cover`欠落の場合はBuildを開始せず、global-style-generatorから再実行します。

✅ Result: Phase 5-6遷移ゲートの厳格化（status=readyかつcampaign_cover存在の両方を要求）。不合格時のリカバリフロー確立。

---

## Round 9: Orchestrator自体が肥大化してきた

👤 Human:
あとこれは作りの話なんですけど、Orchestratorのファイルがめちゃくちゃ長くなってきて、Phase 4のアセット生成のルールだけで100行以上あります。Phaseが増えるたびにこのファイルだけ膨れるの、メンテナンスきつくないですか？

🤖 Claude:
まさにその通りです。Orchestratorの責務を整理すると:

**Orchestratorがやるべきこと:**
- モード選択（classic_small / thin_large）
- フェーズ順序とartifact gate
- handoff管理

**Orchestratorがやるべきでないこと:**
- 各Phaseの具体的な手順（subagent spawn packetに移す）
- リサーチの方法論（reference docに移す）

Phase固有の手順は subordinate skills に押し出して、Orchestratorはphase order, gate判定, artifact contractに専念する方針にします。

吸収したPhaseの実行契約はreference docとして保持:

```
reference/post-instructions-intake.md
reference/post-instructions-product-research.md
reference/post-instructions-kol-research.md
reference/post-instructions-export.md
```

agents/ディレクトリに各subagentのspawn packet:

```
agents/planner-post-instructions.md
agents/asset-acquisition.md
agents/global-style-generator.md
agents/kol-creative-worker.md
agents/asset-resolver.md
agents/builder-post-instructions.md
agents/visualizer-post-instructions.md
agents/reviewer-post-instructions.md
```

✅ Result: Orchestratorの責務をmode選択・phase order・artifact gateに限定。Phase固有手順はsubordinate skills/reference docsに分離。メンテナンス性向上。

---

## Final State

最終的なPhase構成:

```
Phase 0: Initialize
Phase 1: Intake
Phase 1.5: Product Research
Phase 2: KOL Research
  → Phase 2→3 Readiness Check（6項目全件チェック）
Phase 3: Creative Planning
Phase 4a: Asset Acquisition
Phase 4b: Global Style Gen
Phase 4c: KOL Creative（KOL数分spawn）
Phase 4d: Asset Resolve
  → Phase 5-6遷移ゲート（status=ready + campaign_cover存在）
Phase 5: Build     ┐
Phase 6: Visualize ├── AgentTeams (fix loop, max 10)
Phase 7: Review    ┘
Phase 8: Export
```

設計上の主要な判断:
- `classic_small` / `thin_large` のモード分割: KOL数に応じてLeadの責務を変える
- Phase 4の4分割: 1つのsubagentに全画像を任せない。run_id contractでstale artifact防止
- Readiness Check: Phase遷移前の全件チェック。欠落があれば再実行
- AgentTeams fix loop: Review結果を反映できる閉ループ。最大10回で安全弁
- caption-binding-rules: builder spawn時に必ず含めるsingle source of truth
- Orchestratorのスリム化: mode選択とgate判定に専念、Phase手順はsubordinate skillsへ
