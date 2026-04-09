---
title: "KOLが増えるほど壊れていくオーケストレーターとどう戦ったか"
emoji: "🔧"
type: "tech"
topics: ["claudecode", "ai", "architecture", "agentteams"]
published: true
---

KOL（インフルエンサー）向けの投稿指示書をPPTXで自動生成するシステムを作っています。受注書とKOLリストを入力すると、リサーチからクリエイティブプラン、画像素材生成、デッキ組み立てまでを一気通貫でやってくれるパイプラインです。

3人のKOLで動かしている間は快調でした。6人に増やした瞬間、5人目のキャプション方向性が1人目のコピーになりました。この記事は、その壊れ方の観察から始まります。

## 6人目のキャプションが「潤い」しか言わなくなった

最初のパイプラインは素朴な直列構成でした。

```python
# 初期の構成
for phase in [intake, kol_research, creative_plan, asset, build, review]:
    result = run_subagent(phase, inputs=previous_outputs)
```

Intake（受注書パース）→ KOL Research → Creative Planning → Asset → Build → Review。各PhaseをSubagentとして実行し、ファイルで成果物を渡していく。3人のKOLでテストしたときは問題なく動いていて、KOLごとにキャプションの方向性もシーン構成もちゃんと分かれていました。

6人の案件を流したら、処理時間がまず目に見えて伸びました。そして出力されたデッキを開くと、5人目と6人目のキャプション方向性が1人目とほぼ同一でした。「潤い」と「自然由来」を繰り返しているだけ。

最初に疑ったのはプロンプトの長さです。KOL Research で6人分のプロフィールと過去投稿分析を全部まとめて次のPhaseに渡しているので、単純にトークン数が多すぎるのだろうと。プロンプトを短くするために要約ステップを挟んでみましたが、直りませんでした。

次に疑ったのがコンテキストの構造です。6人分のリサーチ結果とクリエイティブプランが1つのSubagentのコンテキストに全部載っている。後半のKOLを処理するとき、前半の情報が支配的になって「それっぽいもの」を繰り返してしまう。要約しても情報量は減りますが、コンテキスト内での前半偏重は変わらない。

問題はトークン数ではなく、**コンテキスト分離**の欠如でした。

## KOL数でモードを分ける

対策として、KOL数に応じて2つの実行モードを導入しました。

```python
if len(kol_list) <= 3:
    mode = "classic_small"   # Leadが直接処理してよい
else:
    mode = "thin_large"      # Leadはsummary/handoff/gate判定のみ
```

`classic_small`はLeadエージェントがintakeやasset周りの一部を直接処理します。3人以下なら全体のコンテキストに収まるので、オーバーヘッドを減らせます。`thin_large`はLeadがsummary作成とhandoff管理に徹して、各Phaseは必ずSubagentに委譲する。

ただモード分割だけでは根本解決になりませんでした。クリエイティブプランニングの段階では結局全KOL分の情報を横断的に見る必要があるからです。KOL AとKOL Bが似たフォロワー層を持っている場合、意図的に方向性を変えないといけない。

切り分けてみると:

- リサーチ段階: 各KOLの調査は独立。並列化できます
- プランニング段階: 全KOL横断の判断が必要（ここがボトルネック）
- アセット生成段階: KOLごとに独立

プランニングは`planner` Subagentにまとめて任せて、成果物として`per_kol_packages.json`というKOL別パッケージを出力させることにしました。このJSONがあれば、後続のアセット生成はKOLごとに独立したSubagentで処理できます。

```json
// planning/per_kol_packages.json（構造）
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

これで5人目・6人目のキャプションが1人目のコピーになる問題は消えました。が、別の問題が出てきます。

## 昨日の案件の画像が今日のデッキに混ざる

新しい案件を流したら、キャンペーンカバーは新しくなっているのに、3人目のKOLのシーン画像だけ前の案件のものが残っていました。

原因を探るのにしばらくかかりました。最初はキャッシュの問題だと思いました。画像のファイルパスが同じだから前回のファイルが上書きされずに残っている、と。でもパスを確認したら別の案件は別ディレクトリに出力されています。

もう少し調べると、3人目のKOLのシーン画像生成が途中で失敗していて、生成自体がスキップされていました。前の案件のファイルが残っていたのではなく、前回の出力ディレクトリから何らかの形で参照が残っていた。そしてもう一つ、画像生成を全部1つのSubagentでやらせていたので、途中でコケると後続のKOLの画像も全部生成されないまま次のPhaseに進んでいました。

2つの問題を同時に解決する必要がありました。

まずPhase 4（Asset）を4つに分割します。

```
Phase 4a: Asset Acquisition（ロゴ・商品参照画像の取得）
Phase 4b: Global Style Gen（campaign_cover + title_cover + product_main）
Phase 4c: KOL Creative（KOL 1名ずつ独立してspawn）
Phase 4d: Asset Resolve（全アセットを統合 → assets_resolved.json）
```

4cがポイントで、KOL1名につき1つのSubagentを起動します。1人がコケても他のKOLに影響しません。そして4bが完了する前に4cを起動してはいけないという依存関係があります。Global Style（カバー画像のトンマナ）が決まっていない状態でKOLのシーン画像を生成すると、スタイルがバラバラになるので。

stale artifact問題には`run_id`を導入しました。

```python
# run_id contract
run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')

# 各Phase 4 subagentの出力に含める
{"run_id": "20260409T120000Z", "status": "ready", ...}

# Gate判定
def check_gate(phase_result_path, current_run_id):
    result = load_json(phase_result_path)
    if result.get("run_id") != current_run_id:
        return False  # stale — 再実行
    return True
```

現在の`run_id`と出力の`run_id`が一致しなければstale artifactとして無視し、そのPhaseを再実行します。

正直、`run_id`という仕組み自体は何も難しくないです。難しかったのは「前の案件の画像が混ざっている」という症状から「stale artifactの検出機構がない」という原因に辿り着くまでの過程でした。

## リサーチが足りないまま次に進んでしまう

5人のKOLで回したとき、3人目のKOLだけクリエイティブプランが妙に薄い。キャプション方向性が「フォロワーに響くコンテンツ」としか書いてない。

調べたら、そのKOLのリサーチ自体が失敗していて、`research/` ディレクトリにファイルがありませんでした。KOL Research Phaseがmanifest（5人分のリスト）は作ったものの、実際のリサーチファイルは3人分しかなかった。なのにPhase 3（Creative Planning）に進んでいました。

Phase完了の判定が「`kol_research_manifest.json`が存在すればOK」になっていたのが原因です。マニフェストは存在するけど中身が全員分揃っていない、というケースを想定していませんでした。

Phase 2→3の遷移にReadiness Checkを入れました。

```python
# Phase 2→3 Lead Readiness Check — 全件チェック
checks = {
    "intake_packet":      "planning/intake_packet.json",
    "kol_targets":        "planning/kol_targets.json",
    "product_research":   "research/product_deep_research/summary.json",
    "kol_manifest":       "research/kol_research_manifest.json",
    "kol_research_summary": "planning/kol_research_summary.md",
}

for name, path in checks.items():
    if not Path(path).exists():
        rerun_phase(name)  # 欠落Phase再実行

# マニフェスト内のKOL数と実ファイル数の一致チェック
manifest = load_json("research/kol_research_manifest.json")
expected = len(manifest["kols"])
actual = len(list(Path("research/kol_research/").glob("*.json")))
if actual != expected:
    missing = find_missing_kols(manifest, actual_files)
    rerun_kol_research(missing)
```

1件でも欠落があればPhase 3に進まない。この「全件チェックしてから次へ」という当たり前のことが、最初の設計では抜けていたんですよね。

同じタイミングで、商品情報のリサーチが足りないことにも気づきました。KOLのことばかり調べていて、商品自体の特徴や差別化ポイントが指示書に反映されていない。Phase 1（Intake）とPhase 2（KOL Research）の間にPhase 1.5としてProduct Researchを追加し、Readiness Checkの項目にも加えました。

## テキストが全部白い

デッキが生成されるようになった段階で、PPTXを開いたらテキストが背景と同化して見えないスライドがありました。あとページ番号が全部「1」になっている。

テンプレートのプレースホルダーでは色が正しく表示されているので、テンプレート自体の問題ではない。Visualizer（テキスト書き込み担当のSubagent）がテキストを流し込むとき、フォント色を明示的に設定していなかった。PPTXのテーマ設定で明るい色が定義されていると、solidFillを設定していないテキストは白で表示されます。

修正は単純で、全テキストrunに`030303`（ほぼ黒）をsolidFillで設定します。ただし`_bg` / `_fill` / `_header` / `_label`を含むShapeはテンプレートのフォント色を維持。これらはデザイン要素なので上書きすると壊れます。

```python
# Visualizer binding rule
for run in paragraph.runs:
    if not is_design_shape(shape.name):
        run.font.color.rgb = RGBColor(0x03, 0x03, 0x03)
# _bg, _fill, _header, _label 等はスキップ
```

`visible:false`のShapeがスライド端に見えている問題もありました。テキストを空にしてからオフキャンバスに移動する処理を追加。これとendParaRPr（段落末の書式設定）の順序修正、`update_slide_numbers()`の呼び出しを加えて、ようやくデッキが見た目として成立するようになりました。

ここまでの問題は全部「出力を見て初めて気づく」タイプのもので、ログだけ見ていると成功しているように見えるのが厄介でした。

## Reviewerが指摘してもそのまま出力される

ReviewerがPPTXの品質チェックをして「キャプションのトーンがブリーフと合ってない」と指摘してくれているのに、その指摘が反映されないまま最終PPTXとして出力される。Build → Visualize → Review → Exportが直列で、ReviewがREJECTしても戻る仕組みがなかったからです。

最初はOrchestrator側で条件分岐させようと思いました。Reviewの出力を見てBuilderを再起動する、と。でもBuilder→Visualizer→Reviewerの行き来をOrchestratorが管理すると、毎回全体のコンテキストを再構築する必要があって効率が悪い。

AgentTeamsを使って、Phase 5-6-7を1チーム内の閉ループにしました。

```
AgentTeams構成:
  builder     → data_binding.json + PPTXスケルトン
  visualizer  → テキスト・画像のbinding適用
  reviewer    → 品質評価

Fix Loop:
  REJECT + target: data   → builder再spawn → visualizer → reviewer
  REJECT + target: pptx   → visualizer再spawn → reviewer
  APPROVE                 → Phase 8 (Export)
```

REJECTの`fix_targets`が「データの問題」ならbuilderから、「PPTX上の問題」ならvisualizerからやり直す。最大10イテレーションで、超えたらescalateして人間に判断を委ねます。通常は2-3回で収束しますが、10回という上限は安全弁として残しています。

この閉ループを入れたことで、もう一つ見えてきた問題がcaption-binding-rulesです。data_binding.jsonのキャプションスライドで、KOL Aのスライドに KOL Bの開示タグが入っていたり、市場によって異なるはずの開示トークン（日本なら「#PR」、米国なら「#ad」）が全部「#ad」統一になっていたり。

Shapeの名前でKOL・市場・コンテンツタイプをマッピングするルールが、builderのプロンプトにちゃんと含まれていなかったのが原因です。`caption-binding-rules.md`をsingle source of truthとして定義し、builder spawn時に必ず全文を含める契約にしました。fix loopでの再spawn時も同様です。

## Orchestratorがやるべきこと、やるべきでないこと

ここまでの修正を重ねるうちに、Orchestratorのファイルが膨れ上がりました。Phase 4のアセット生成ルールだけで100行超。Phaseが増えるたびにこのファイルだけが太っていく。

整理すると、Orchestratorの責務は3つだけです。

1. モード選択（`classic_small` / `thin_large`）
2. Phase順序とartifact gate判定
3. handoff管理

各Phaseの具体的な手順はsubordinate skillsのspawn packetに、リサーチの方法論はreference docに押し出しました。吸収したPhaseの実行契約は`reference/`ディレクトリに保持しています。

最終的なPhase構成はこうなっています。

```
Phase 0:   Initialize
Phase 1:   Intake
Phase 1.5: Product Research
Phase 2:   KOL Research
             → Readiness Check（6項目）
Phase 3:   Creative Planning
Phase 4a:  Asset Acquisition
Phase 4b:  Global Style Gen
Phase 4c:  KOL Creative（KOL数 × spawn）
Phase 4d:  Asset Resolve
             → 遷移ゲート（status=ready + campaign_cover）
Phase 5-7: Build / Visualize / Review（AgentTeams fix loop）
Phase 8:   Export
```

3人のKOLで動いていた直列パイプラインから、ここに至るまでの変更は全部「壊れ方の観察」から始まっています。5人目のキャプションが1人目のコピーになった、前の案件の画像が混ざった、リサーチが欠けたまま進んだ、テキストが白くなった、レビュー結果が反映されなかった。

どの問題も、起きてからでないと設計の欠陥に気づけませんでした。最初から完璧なPhase分割やgate判定を設計できたかというと、正直難しかったと思います。まだ境界を引いていない箇所がどこかにあるはずで、次に壊れるのはたぶんそこです。
