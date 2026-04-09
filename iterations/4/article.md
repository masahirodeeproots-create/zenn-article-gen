---
title: "AIエージェント8体で1枚のPPTXを作る — 「誰が何を知るべきか」の設計"
emoji: "🏗️"
type: "tech"
topics: ["claudecode", "ai", "architecture", "multiagent"]
published: true
---

KOL（インフルエンサー）向けの投稿指示書をPPTXで自動生成するシステムを作りました。受注書とKOLリストを渡すと、リサーチからデッキ生成まで全自動で回ります。案件ごとにキャプション方向性やシーン構成が全部違うので、手作業だと3人分で半日。

最終的に8体のAIエージェントが分業する構成になりました。この設計で一番考えたのは「タスクをどう割るか」ではなく**「各エージェントに何を見せるか」**でした。情報の境界を先に設計すると、タスクの分割は勝手に決まります。

## 6人で壊れた

最初は素朴な直列パイプライン。Intake、KOL Research、Creative Planning、Asset、Build、Review。各フェーズをsubagent — 親エージェントが起動する子プロセスのようなもの — として実行して、成果物はファイルで渡します。3人のKOLなら問題なし。

6人で回したら5人目と6人目のキャプションが1人目のコピーになりました。「潤い」と「自然由来」の繰り返し。attentionの問題です。6人分のリサーチ結果を全部1つのコンテキストに載せると、前半の情報が支配的になって後半はそのコピーを生成し始めます。

```
┌────────────────────────────────────────────────────────┐
│ リサーチ:    各KOLの調査は独立       → 並列化できる    │
│ プランニング: 全KOL横断の判断が必要   → ボトルネック   │
│ アセット生成: KOLごとに独立          → 並列化できる    │
└────────────────────────────────────────────────────────┘
```

プランニングだけは全KOLを横断的に見る必要があります。でもその出力を `per_kol_packages.json` というKOL別パッケージに分割しておけば、後続フェーズは各KOLを独立処理できます。

エージェントへの情報の渡し方を設計しないかぎり、デフォルトは「全員が全部知っている」です。少人数なら動く。スケールした瞬間に壊れる。皆さんの組織でも同じことありませんか。5人のスタートアップなら全員が全情報を持っていても回るけど、50人になったら情報の流通設計なしには崩壊します。

KOL数で実行モードも分けました。3人以下の `classic_small` はLeadエージェントが直接処理もする。4人以上の `thin_large` はLeadがゲート判定だけに専念して処理は全部subagentに委譲します。

## Phase 4を4つに割った話

ここが本丸です。

画像素材の生成で2つの問題が同時に起きました。新しい案件を流したのに3人目のKOLのシーン画像だけ前の案件のものが残っている。しかも1つのsubagentで全画像を生成しているから、3人目でコケると4人目以降も全滅して、画像がないまま次のフェーズに進んでいました。

3時間くらい追いかけ回しました。なんで3人目だけ画像が古いんだと。ログを見ても「生成成功」って書いてあるんですよね。んで結局わかったのが、3人目の画像生成が実は失敗していて、前回の実行で残っていたファイルを今回の成果物だと思い込んでいたということ。はー。本当に腹が立ちました。

ここからAsset生成（Phase 4）を4つに分割します。

```
Phase 4a: Asset Acquisition
  └─ ロゴ・商品参照画像を取得
  └─ → source_assets_manifest.json

Phase 4b: Global Style Gen
  └─ campaign_cover (16:9) + title_cover (21:9) + product_main (9:16)
  └─ → global_assets_manifest.json
  └─ ★ デッキ全体のビジュアルトーンをここで確立

Phase 4c: KOL Creative  ×KOL人数分
  └─ KOL 1名ずつ独立したsubagentをspawn
  └─ 各KOLのシーン画像4枚 + reference image
  └─ → assets_plan_{slug}.json
  └─ ⚠️ 4bの完了が前提条件

Phase 4d: Asset Resolve
  └─ source + global + per-KOL のアセットを統合
  └─ → assets_resolved.json (status=ready)
```

### 4bと4cの依存関係

この分割で核心になっているのは4bと4cの関係です。

4bが生成するのはキャンペーン全体のビジュアルトーン。カバー画像、タイトルカバー、商品メイン画像。デッキを開いたときの第一印象を決める画像群で、色味、テクスチャ、空気感を確立します。4cはそのトーンに合わせて各KOLのシーン画像を生成する。

**4bが完了する前に4cを起動してはいけません。** global_assets_manifest.jsonがない状態でKOLごとのシーン画像を生成するとどうなるか。あるKOLのシーン画像はパステル調で、別のKOLはビビッドで、また別のKOLはモノクロ寄り。1つの案件のデッキなのにスライドをめくるたびに別の世界観が出てくる。全体の視覚的統一感は4bが確立し、4cはその制約の中で各KOLの個性を表現します。依存の方向を逆にするとデッキが破綻します。

4cでKOL 1名ごとに独立したsubagentをspawnするのもポイントです。1人がコケても他に影響しない。6人のKOLで3人目だけ失敗しても残り5人は正常。3人目だけ再実行すればいい。

### 4aと4bを分けるべきか — 正直迷いました

ロゴの取得もカバー画像の生成も、どっちもAssetフェーズの話なんですよね。1つにまとめたほうがsubagentのspawnオーバーヘッドが減る。でもやってみて気づいたのは、障害モードが全く違うということです。4aの失敗は「ロゴが見つからない」「解像度が低い」でネットワーク起因。4bの失敗は「プロンプト品質」「スタイル不一致」で画像生成AI起因。一緒にするとロゴ取得に失敗したときにカバー画像生成まで巻き添えになって、ロゴを修正して再実行するとカバー画像もまた作り直し。分けておけば失敗フェーズだけピンポイントで再実行できます。

...ただ、2-3人のKOLの小規模案件で4回spawnするのはオーバーヘッドかもしれません。classic_smallモードでは4aと4bをまとめるオプションを入れてもいい気がしていますが、まだ実装していないです。

### stale artifactとrun_id

前の案件のファイルが残る問題は `run_id` で解決しました。各実行にUTCタイムスタンプを振って、Phase 4の各subagentの出力にも同じrun_idを含める。ゲート判定でrun_idの一致を検証し、不一致なら前回の残骸として無視して再実行。

```
checkpoint/run_state.json  →  {"run_id": "20260409T120000Z", ...}
各 *_phase_result.json     →  {"run_id": "20260409T120000Z", ...}
Gate判定: run_id不一致 → stale → 該当Phase再実行
```

仕組みとしては何も難しくないです。でもマルチエージェントでは複数のsubagentが非同期にファイルを書き出すから、「このファイルは今回の成果物か前回の残りか」が自明ではありません。人間なら記憶に頼れますがエージェントには記憶がないので、ファイル自体に出自を刻印する必要があります。

### 遷移ゲート

4dの `assets_resolved.json` に `status: ready` と書いてあってもまだ安心できません。一度 `status: partial` のまま通過してPPTXの表紙が真っ白になった案件がありました。statusが`ready`かつ`campaign_cover`エントリが`global_assets`に存在する、この両方を通過条件にしています。

経験上、ゲートが甘くてゴミが後段に流れるほうが、ゲートが厳しくて止まるよりも遥かにデバッグコストが高いです。

## その他の設計判断

**Readiness Check**: Phase 2→3の遷移で6項目を全件チェック。intake_packet、kol_targets、product research summary、KOL manifest、KOL research summary、全KOL分のresearchファイル数の一致。1件でも欠落があれば先に進みません。5人中3人分しかリサーチが完了していないのにPhase 3に進んで、3人目のプランが「フォロワーに響くコンテンツ」みたいな空虚なものになっていたのがきっかけです。

**Build→Review fix loop**: Phase 5-7をAgentTeamsで1チームにまとめた閉ループです。ReviewerがREJECTしたら修正対象に応じてBuilderかVisualizerから再実行。最大10回、通常2-3回で収束します。

```
┌──────────────────────────────────────────┐
│         AgentTeams (Phase 5-6-7)          │
│                                           │
│  Builder ──→ Visualizer ──→ Reviewer      │
│     ↑                          │          │
│     └──── REJECT(data) ────────┘          │
│              REJECT(pptx) ──→ Visualizer  │
│              APPROVE ──→ Export            │
└──────────────────────────────────────────┘
```

:::details Visualizerの「見えないテキスト」問題とcaption-binding-rules
PPTXを開いたらテキストが全部白で見えなかったり、KOL Aのスライドに KOL Bの開示タグが入っていたり。テーマカラー継承の問題は全テキストrunに`030303`をsolidFillで設定、caption bindingの問題は`caption-binding-rules.md`をsingle source of truthとしてbuilder spawnプロンプトに含めることで解決しました。
:::

## 全体像

```
Phase 0:   Initialize
Phase 1:   Intake
Phase 1.5: Product Research
Phase 2:   KOL Research
             → Readiness Check（6項目）
Phase 3:   Creative Planning
Phase 4a:  Asset Acquisition
Phase 4b:  Global Style Gen
Phase 4c:  KOL Creative (×KOL人数)
Phase 4d:  Asset Resolve
             → 遷移ゲート（status=ready + campaign_cover）
Phase 5-7: Build / Visualize / Review (AgentTeams, max 10 loop)
Phase 8:   Export
```

Orchestratorの責務はモード選択、フェーズ順序、artifact gateの判定だけです。各Phaseの手順は下位のskill定義と参照ドキュメントに分離。500行を超えたあたりで「このファイルを読むのは人間じゃなくてエージェントなんだから、エージェントにとって読みやすい構造にすべきだ」と気づいて分離しました。

マルチエージェントを「タスクの分割」として設計すると、情報の境界が曖昧なまま残ります。「何を見せるか」を先に決めたほうがタスク分割も決まる。15人のKOLでPhase 4cを15並列spawnしたらどうなるかはまだ試していません。
