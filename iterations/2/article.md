---
title: "AIエージェント8体で1枚のPPTXを作る — 「誰が何を知るべきか」の設計"
emoji: "🏗️"
type: "tech"
topics: ["claudecode", "ai", "architecture", "multiagent"]
published: true
---

KOL（インフルエンサー）向けの投稿指示書をPPTXで自動生成するシステムを作りました。受注書とKOLリストを渡すと、リサーチからデッキ生成まで全自動で回ります。最終的に8体のAIエージェントが分業する構成になったんですけど、ここに至るまでに一番考えたのは「どのエージェントに何を見せるか」の設計でした。

**マルチエージェントシステムの核心は、タスクの分割ではなく情報の分割にある。** これがこの記事の全てです。

## 「全員が全部知っている」はスケールしない

最初のバージョンは素朴な直列パイプラインでした。Intake → KOL Research → Creative Planning → Asset → Build → Review。各フェーズをsubagent（親エージェントから呼び出される子エージェント）として実行して、成果物をファイルで渡していく。3人のKOLで試したら問題なく動きました。

6人のKOLで回したら5人目と6人目のキャプション方向性が1人目とほぼ同じになっていて、「潤い」と「自然由来」をひたすら繰り返しているだけでした。

これ、最初はコンテキストウィンドウ（LLMが一度に読める情報量の上限）に近づいてるのかなと思って、要約ステップを挟んでみたんですけど直らなくて。んで、もうちょっと調べたら本質的にはattentionの問題でした。6人分のリサーチ結果を全部1つのコンテキストに載せると、前半の情報が支配的になって後半は前半のコピーを生成し始める。コンテキストが長くなったこと自体が問題というより、長いコンテキストの中で情報の重み付けがフラットになってしまうという、まあLLMの構造的な限界です。

ここでKOL数に応じた2モード制（`classic_small`: 3人以下はLeadが直接処理、`thin_large`: 4人以上はLeadがgate判定のみに専念）を入れたんですけど、これだけでは不十分でした。モードを分けても、Creative Planningの段階では結局全KOL分の情報を見ているから。

で、問題を切り分けてみて気づいたんです。

```
┌─────────────────────────────────────────────────────────┐
│ リサーチ:    各KOLの調査は独立       → 並列化できる     │
│ プランニング: 全KOL横断の判断が必要   → ここがボトルネック │
│ アセット生成: KOLごとに独立          → 並列化できる     │
└─────────────────────────────────────────────────────────┘
```

プランニングだけは横断的に見ないといけない。これは避けられません。でもプランニングの成果物を `per_kol_packages.json` というKOL別のパッケージに分割して出力させれば、後続のフェーズはKOLごとに独立して処理できます。

ここから見えてきたのは、「このエージェントは何を知るべきか」を明示的に設計しないかぎり、デフォルトでは「全員が全部知っている」状態になるということです。LLMのコンテキストに全部載せるのが一番楽だし、少人数なら実際それで動く。でもスケールした瞬間に壊れます。皆さんの組織でも同じこと起きてませんか？ スタートアップで5人のときは全員が全部知っていても回るけど、50人になったら情報の流通経路を設計しないと崩壊する。AIエージェントでもまったく同じことが起きました。

## なぜPhase 4を4つに割らないといけなかったのか

これが一番設計判断が込み入ったところで、一番語りたいところです。

画像素材の生成で起きた問題は2つありました。1つ目は、新しい案件を流したのに3人目のKOLのシーン画像だけ前の案件のものが残っていたこと。2つ目は、1つのsubagentで全画像を生成しているので途中でコケると後続のKOLの画像がないまま次のフェーズに進んでしまうこと。

結論から言うと、Asset生成（Phase 4）を4つに分割しました。

```
Phase 4a: Asset Acquisition
  └─ ロゴ・商品参照画像を取得
  └─ → source_assets_manifest.json

Phase 4b: Global Style Gen
  └─ campaign_cover (16:9) + title_cover (21:9) + product_main (9:16)
  └─ → global_assets_manifest.json
  └─ 🔑 全体の視覚的トンマナをここで確立

Phase 4c: KOL Creative  ×KOL人数
  └─ KOL 1名ずつ独立したsubagentをspawn
  └─ 各KOLのシーン画像4枚 + reference image
  └─ → assets_plan_{slug}.json
  └─ ⚠️ 4bの完了が前提条件

Phase 4d: Asset Resolve
  └─ source + global + per-KOL のアセットを統合
  └─ → assets_resolved.json (status=ready)
```

この分割の核心は4bと4cの依存関係にあります。

4bが生成するのはキャンペーン全体のビジュアルトーン — カバー画像とかタイトルカバーとか、デッキ全体の色味と雰囲気を決める画像群です。4cはそのトーンに合わせて各KOLのシーン画像を生成する。**4bが完了する前に4cを起動してはいけない。** グローバルスタイルが存在しない状態でKOL個別の画像を生成すると、KOLごとにスタイルがバラバラになります。あるKOLのシーン画像はパステル調で、別のKOLはビビッド、みたいな。1つの案件なのにデッキを開いたら統一感がない。

で、4cでKOL 1名につき1つのsubagentを起動するのもポイントです。1人がコケても他に影響しない。6人のKOLで回して3人目だけ画像生成に失敗しても、残り5人の画像は正常に生成されている。失敗した3人目だけ再実行すればいい。1つのsubagentに全部やらせていたときは、3人目でコケたら4人目以降も全滅していました。

ここの設計で一番悩んだのは、実は4aと4bを分ける必要があるかどうかでした。ロゴと商品参照画像を取得する（4a）のと、カバー画像を生成する（4b）のは、1つのsubagentでまとめてもよさそうに見える。でもやってみると、ロゴ取得はネットワークアクセスが主体で失敗パターンが「画像が見つからない」「解像度が低い」。一方カバー画像生成は画像生成AIの呼び出しで、失敗パターンが「プロンプトの品質」「スタイルの一貫性」。障害モードが全く違うので、一緒にすると一方の失敗が他方を巻き込む。分けました。

### stale artifactとrun_id — 地味だけど必須の仕組み

前の案件の画像が残る問題。3時間くらい「なんで3人目だけ画像が古いんだ」って追いかけ回して、原因が「前回の失敗で残ったファイルを今回の成果物だと思い込んでいた」だったときは笑ってしまいました。いや笑えない。本当に腹が立ちました。

解決策自体は地味で、`run_id` というタイムスタンプを各実行に振って、Phase 4の各subagentが出力するファイルにも `run_id` を含める。Gate判定時にrun_idの一致を検証し、不一致ならstale artifact（古い実行の残骸）として無視する。それだけです。

```
checkpoint/run_state.json  →  {"run_id": "20260409T120000Z", ...}

各 *_phase_result.json    →  {"run_id": "20260409T120000Z", ...}

Gate判定: run_id不一致 → stale → 該当Phaseを再実行
```

仕組みとしては何も面白くない。でもこれがないと、テスト実行を繰り返すたびに前回の残骸に騙される。マルチエージェントシステムでは複数のsubagentが非同期にファイルを書き出すから、「このファイルは今回の実行で生成されたものか、前回の残りか」が自明ではないんです。人間なら「さっき消したはず」と記憶に頼れますが、エージェントにそんな記憶はありません。

### Phase 5-6遷移ゲート — assets_resolvedだけでは足りない

4dが出力する `assets_resolved.json` に `status: ready` と書いてあっても安心できないという話も補足しておきます。

実際に `status: partial` のままBuildに進んでしまい、PPTXの表紙が真っ白になった案件がありました。assets_resolved.jsonの存在だけをチェックしていて、中身の `status` フィールドと `campaign_cover` の存在を見ていなかった。`status` が `ready` かつ `campaign_cover` エントリが `global_assets` に存在する、この両方を満たさないとBuildに進まない、というゲートを入れて解決しました。

ゲートの条件を厳しくしすぎると前に進めなくなるんじゃないか、という心配があるかもしれません。でも経験上、ゲートが甘くてゴミが後続に流れるほうが遥かにコストが高いです。後段でおかしな出力が出て、原因を遡ると3フェーズ前の入力が欠けていた、みたいなデバッグに比べれば、ゲートで止まって「campaign_coverがありません」と言われるほうがずっとマシです。

## Readiness Check、fix loop、その他の話

Phase 4の設計に比べると他のトピックは正直そこまで込み入っていないので、手短にまとめます。

**Readiness Check**: Phase 2（KOL Research）→ Phase 3（Creative Planning）の遷移時に6項目を全件チェックします。intake_packet、kol_targets、product research、KOL manifest、KOL research summary、そして全KOL分のresearchファイル数がmanifest記載のKOL数と一致するか。1件でも欠落があれば先に進まず、該当Phaseを再実行します。きっかけは、5人中3人分しかリサーチが完了していないのにPhase 3に進んでしまい、3人目のクリエイティブプランが「フォロワーに響くコンテンツ」みたいな空虚なものになっていたこと。

**Build→Review fix loop**: Phase 5（Build）・6（Visualize）・7（Review）をAgentTeams（チーム内でエージェント同士が協調するClaude Codeの仕組み）で1チームにまとめて、ReviewerがREJECTしたらfix_targetsに応じてBuilderかVisualizerから再実行する閉ループです。

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

最大10回ループ。通常2-3回で収束します。これを入れる前は、Reviewerが「キャプションのトーンがブリーフと合ってない」と指摘しているのにそのまま最終出力されていました。

:::details Visualizerの「見えないテキスト」問題
PPTXを開いたらテキストが全部白で背景と同化して見えなかったことがあります。テンプレートのテーマカラーを継承してしまい、solidFillを明示的に設定していないテキストが白になる。全テキストrunに `030303` をsolidFillで設定するルールにしました。ただし `_bg` / `_fill` / `_header` / `_label` を含むShapeはテンプレートの色を維持します。あとページ番号が全部「1」になる問題もあって、binding適用後に `update_slide_numbers()` を呼ぶ必要がありました。
:::

## 最終的な全体像

```
Phase 0:   Initialize
Phase 1:   Intake
Phase 1.5: Product Research
Phase 2:   KOL Research
             → Readiness Check（6項目全件）
Phase 3:   Creative Planning (planner subagent)
Phase 4a:  Asset Acquisition (designer subagent)
Phase 4b:  Global Style Gen  (designer subagent)
Phase 4c:  KOL Creative      (designer subagent × KOL人数)
Phase 4d:  Asset Resolve      (designer subagent)
             → 遷移ゲート（status=ready + campaign_cover存在）
Phase 5-7: Build / Visualize / Review (AgentTeams fix loop, max 10)
Phase 8:   Export
```

Orchestrator自体の責務は、モード選択（classic_small / thin_large）、フェーズ順序、artifact gateの判定。それだけに絞りました。各Phaseの具体手順はsubordinate skills（下位のスキル定義）とreference docs（参照ドキュメント）に分離してあります。Orchestratorのファイルが500行を超えたあたりで耐えられなくなったので。

この設計をやって一番強く思ったのは、マルチエージェントを「タスクの分割」として設計すると情報の境界が曖昧なまま残るということです。「このエージェントに何を見せるか」を先に決めたほうが、結果としてタスクの分割も自然に決まる。少なくともこのシステムではそうでした。15人のKOLでPhase 4cを15並列spawnしたときにどうなるかはまだ検証していません。
