---
title: "AIエージェント8体で1枚のPPTXを作る — 「誰が何を知るべきか」の設計"
emoji: "🏗️"
type: "tech"
topics: ["claudecode", "ai", "architecture", "multiagent"]
published: true
---

KOL（インフルエンサー）向けの投稿指示書をPPTXで自動生成するシステムを作りました。受注書とKOLリストを入力すると、リサーチからデッキ生成まで全部やってくれるやつです。

で、最終的にこのシステムは8つのフェーズに分かれて、それぞれ専用のAIエージェントが担当する構成になりました。最初からこうなったわけじゃないです。最初は「1体のエージェントに全部やらせればいいでしょ」から始まって、壊れるたびに分割していった結果がこの形です。

この記事で伝えたいのは1つだけ。**マルチエージェントシステムの設計で一番大事なのは、「各エージェントが何を知っていいか」の境界設計である**ということです。タスクの分割じゃなくて、情報の分割。

## 3人なら動く、6人で壊れる

最初のバージョンはシンプルな直列パイプラインでした。

```
Intake → KOL Research → Creative Planning → Asset → Build → Review
```

各フェーズをsubagentとして実行して、成果物をファイルで渡していく。3人のKOLで試したら問題なく動きました。

6人のKOLで回したら壊れました。5人目と6人目のキャプション方向性が1人目とほぼ同じになっていて、「潤い」と「自然由来」をひたすら繰り返しているだけ。処理もめちゃくちゃ遅くなりました。

最初は「コンテキストウィンドウの上限に近づいてるのかな」と思ったんですけど、調べてみるともうちょっと根が深い問題でした。6人分のKOLリサーチ結果とクリエイティブプランを全部1つのコンテキストに載せると、後半で前半の情報を繰り返し始めるんです。コンテキストが長くなったことでattentionが希薄になる、LLMの構造的な限界です。

ここで導入したのが `classic_small` / `thin_large` の2モード制です。

```
KOL数 ≤ 3  →  classic_small（Leadが直接処理もする）
KOL数 ≥ 4  →  thin_large（Leadはsummary・handoff・gate判定に専念）
```

でもこれだけでは後半KOLの品質問題は直りませんでした。モードを分けても、結局Creative Planningの段階では全KOL分の情報を見ている。ここが詰まるポイントでした。

## 「全員が全部知っている」が壊れる瞬間

問題を切り分けると、こういう構造が見えてきました。

```
┌─────────────────────────────────────────────────┐
│  リサーチ段階:  各KOLの調査は独立（並列化できる）    │
│  プランニング:  全KOL横断で見る必要あり（ここが詰まる） │
│  アセット生成:  KOLごとに独立（並列化できる）         │
└─────────────────────────────────────────────────┘
```

プランニングは横断的に見る必要がある。これは避けられません。でもプランニングの成果物を `per_kol_packages.json` というKOL別のパッケージに分割して出力させれば、その後のフェーズは各KOLを独立して処理できます。

ここで気づいたのは、「このエージェントは何を知るべきか」を明示的に設計しないと、デフォルトでは「全員が全部知っている」状態になるということです。LLMのコンテキストに情報を全部載せるのが一番楽だし、少人数なら実際それで動く。でもスケールした瞬間に壊れます。

これ、人間の組織と全く同じだなと思いました。スタートアップで5人のときは全員が全部の情報を持っていても回る。50人になったら情報の流通経路を設計しないと崩壊する。AIエージェントも同じでした。

## Phase 4を4つに割った理由

画像素材の生成で、腹が立つバグに遭遇しました。

新しい案件を流したら、キャンペーンカバーは新しく生成されているのに、3人目のKOLのシーン画像だけ前の案件のものが残っている。しかも1つのsubagentで全画像を生成しているので、途中でコケると最後のKOLの画像がないまま次のフェーズに進んでしまう。

これが最も設計判断が詰まったところです。Asset生成（Phase 4）を4つに分割しました。

```
Phase 4a: Asset Acquisition
  └─ ロゴ・商品参照画像を取得
  └─ → source_assets_manifest.json

Phase 4b: Global Style Gen
  └─ campaign_cover (16:9) + title_cover (21:9) + product_main (9:16)
  └─ → global_assets_manifest.json

Phase 4c: KOL Creative  ×KOL人数
  └─ KOL 1名ずつ独立してspawn
  └─ 各KOLのシーン画像4枚 + reference image
  └─ → assets_plan_{slug}.json

Phase 4d: Asset Resolve
  └─ 全アセットを統合
  └─ → assets_resolved.json (status=ready)
```

4cがポイントです。KOL 1名につき1つのsubagentを起動する。1人がコケても他に影響しない。

んで、4bと4cには厳密な依存関係があります。**4bが完了する前に4cを起動してはいけない。** 4bで生成されるグローバルスタイル（キャンペーンカバーのトンマナ）がないと、KOLごとのシーン画像のスタイルがバラバラになるからです。全体の視覚的統一感は4bが作る。4cはその統一感の中で個別のKOLに最適化する。

この「依存の方向」を間違えると、見た目がバラバラなデッキが出来上がります。

### stale artifact問題とrun_id

前の案件の画像が残る問題は、`run_id` という仕組みで解決しました。

各案件の実行時にUTCタイムスタンプで `run_id` を生成して `checkpoint/run_state.json` に保存する。Phase 4の各subagentが出力する `*_phase_result.json` にも `run_id` を含める。Gate判定時に現在の `run_id` と出力の `run_id` が一致するかチェックする。不一致ならstale artifactとして無視して再実行。

正直これは地味な仕組みなんですけど、ないと前回の残骸に騙されて延々とデバッグする羽目になります。実際になりました。3時間くらい「なんで3人目だけ画像が古いんだ」と追いかけて、原因が「前回の失敗で残ったファイルを新しいものだと思い込んでいた」だったときは笑ってしまいました。

## Readiness Check — 「進んでいいか」の門番

5人のKOLで回したとき、3人目のKOLだけクリエイティブプランが妙に薄かったことがあります。キャプション方向性が「フォロワーに響くコンテンツ」みたいな抽象的なことしか書いてない。

調べたら、そのKOLのリサーチ自体が失敗していました。`research/` にファイルがなかった。なのにPhase 3（Creative Planning）に進んでいた。

Phase 2の完了判定が「`kol_research_manifest.json` が存在すればOK」になっていたのが原因です。マニフェストは5人分記載されているけど、実際のリサーチファイルが揃っていない。存在チェックだけでは不十分でした。

Phase 2→3の遷移時にReadiness Checkを入れました。

| チェック項目 | 確認方法 |
|---|---|
| intake_packet.json | ファイル存在 |
| kol_targets.json | ファイル存在 |
| Product Research | summary.json存在 |
| KOL Manifest | manifest存在 |
| KOL Research Summary | summary存在 |
| 全KOL分のresearch | manifest内のKOL数とresearchファイル数の一致 |

**1件でも欠落があればPhase 3に進まない。** 欠落したartifactの該当Phaseを再実行します。

ちなみにこのReadiness Checkを入れたことで、Phase 1.5（Product Research）の必要性にも気づきました。KOLのことだけリサーチしても、「この商品の何がすごいのか」が指示書にちゃんと反映されない。商品の特徴・差別化ポイント・訴求軸をまとめるPhaseがIntakeとKOL Researchの間に必要でした。

## Build→Review のfix loop

```
┌──────────────────────────────────────────┐
│         AgentTeams (Phase 5-6-7)          │
│                                           │
│  Builder ──→ Visualizer ──→ Reviewer      │
│     ↑                          │          │
│     └──── REJECT(data) ────────┘          │
│              REJECT(pptx) ──→ Visualizer  │
│              APPROVE ──→ Phase 8 (Export)  │
│                                           │
│  max iterations: 10                       │
└──────────────────────────────────────────┘
```

Reviewerが「キャプションのトーンがブリーフと合ってない」と指摘しているのに、そのまま最終PPTXとして出力されてしまう。レビュー結果を反映する仕組みがなかった。

最初はOrchestratorが条件分岐すればいいかと思ったんですけど、Builder→Visualizer→Reviewerの行き来をOrchestrator側で管理すると、毎回コンテキストの再構築が必要になって効率が悪い。AgentTeamsを使って、この3つを1チーム内で管理するようにしました。

ReviewerがREJECTした場合、`fix_targets` に基づいてどこから再実行するか決まります。データが問題ならBuilderから、PPTX上の見た目の問題ならVisualizerから。APPROVEされるまでループします。

10回は上限であって安全弁です。通常2-3回で収束します。10回到達したらescalateして人間に判断を委ねる。

### Visualizerの「見えないテキスト」問題

PPTXを開いたらテキストが全部白で背景と同化して見えないスライドがありました。テンプレートのテーマカラーを継承してしまって、solidFillを明示的に設定していないテキストが白になっていた。

全テキストrunに `030303`（ほぼ黒）をsolidFillで明示的に設定するルールにしました。ただし `_bg` / `_fill` / `_header` / `_label` を含むShapeはテンプレートの色を維持する。デザイン要素の色を上書きすると壊れるので。

この手の「テンプレート由来の暗黙の前提」との戦いが、PPTX生成で一番消耗するところだという気がしています。

## 全体像

最終的なシステムはこうなりました。

```
Phase 0: Initialize
Phase 1: Intake
Phase 1.5: Product Research
Phase 2: KOL Research
  → Readiness Check（6項目）
Phase 3: Creative Planning
Phase 4a: Asset Acquisition
Phase 4b: Global Style Gen
Phase 4c: KOL Creative（×KOL人数分spawn）
Phase 4d: Asset Resolve
  → Build遷移ゲート（status=ready + campaign_cover存在）
Phase 5: Build     ┐
Phase 6: Visualize ├── AgentTeams fix loop (max 10)
Phase 7: Review    ┘
Phase 8: Export
```

8体のエージェント。それぞれが「何を知っていいか」を厳密に制御されている。

Orchestrator自体の責務もかなり絞りました。モード選択（classic_small / thin_large）、フェーズ順序、artifact gateの判定。それだけです。各Phaseの具体的な手順はsubordinate skillsとreference docsに押し出してあります。Orchestratorのファイルが膨らんでいくのに耐えられなくなったので。

マルチエージェントを「タスクの分割」として設計すると、だいたい情報の境界が曖昧なまま残ります。「このエージェントは何を見ていいのか、何を見てはいけないのか」を先に決めると、タスクの分割は自然と決まる。少なくともこのシステムではそうでした。まだ答えが出ていないのは、この設計原則が他のドメインでも成り立つかどうかです。
