---
title: "KOLが増えるほど壊れていくオーケストレーターとどう戦ったか"
emoji: "🎬"
type: "tech"
topics: ["claudecode", "ai", "architecture"]
published: true
---

KOLが4人を超えたとき、システムは静かに壊れ始めました。エラーは出ません。処理は完走します。でも生成物の品質が、KOLを追うごとに落ちていきます。壊れるたびに直し、直すたびに新しい破綻が出てくる。しばらくそのサイクルを繰り返したあと、ほとんどの問題が「あるエージェントが持つべきでない情報を持っていた」か「あるrunの成果物と別のrunの成果物が混在していた」という、同じ構造に収まっていることに気づきました。境界のないところに境界を引く、という操作の話です。

## KOL 5人案件で最初に壊れたこと

作っていたのは、インフルエンサーマーケティングの受注案件でKOL向け投稿指示書（PPTX）を自動生成するオーケストレーター（`post-instructions-orchestrator`）です。入力は受注資料のPDFとKOLリスト、出力はKOL別・プラットフォーム別のスライドデッキで、各スライドにはクリエイティブ方向性、キャプション方向性、AIで生成したシーン画像、市場の法規制に基づいたcaution_pointsが入ります。

処理はPhase 0から8まで8フェーズのパイプラインです。受注資料のパース（Phase 1）から始まり、製品リサーチ（Phase 1.5）、KOLリサーチ（Phase 2）、クリエイティブプランニング（Phase 3）、アセット生成（Phase 4）、スライドビルド（Phase 5）、ビジュアライズ（Phase 6）、レビュー（Phase 7）、エクスポート（Phase 8）まで一気通貫で処理します。

最初のバージョンではLeadエージェントがKOLリサーチをすべて担当し、Phase 3（クリエイティブプランニング）に直接流し込んでいました。KOL 2〜3人のうちは問題ありませんでした。

KOL 5人案件で初めて試したとき、Phase 3のPlannerが生成した`per_kol_packages.json`を確認すると、4人目と5人目のKOLへの`caption_direction`が1人目・2人目のものと構造的に同一になっていました。`required_words`は"潤い"と"自然由来"を繰り返し、`required_points`も"成分の浸透感"と"朝のルーティン感"のほぼコピーです。5人のKOLはそれぞれフォロワー属性もトーンもまったく違うのに、後半の2人だけがデフォルト調のキャプション方向性になっていました。クライアントに納品すると5人全員に同じトーンで投稿させることになります。

「モデルが後半のKOLを忘れた」という感覚に近いですが、正確には「限られたアテンションが5人分のリサーチ結果に薄く広がって、個々のKOLに尖ったプランニングをする余力がなくなった」という状態です。各KOLのリサーチはフォロワー属性、投稿トーン、カテゴリ別エンゲージメント、過去のブランドコラボ履歴を含みます。5人分積み重なるとLeadのコンテキストは「広くて浅い」状態になり、プランニングに入っても後半KOLの個性を拾えなくなります。

これが、システムを2モードに分岐させた直接のきっかけです。

```json
{
  "execution_mode": "thin_large",
  "kol_count": 5,
  "phase": 2
}
```

`classic_small`（KOL≤3）ではLeadが直接リサーチの一部を担当できます。`thin_large`（KOL≥4）ではLeadは成果物ゲートの管理だけに専念し、全処理をWorkerに委譲します。LeadがKOLのコンテキストを「所有」しないようにする——これがthin_largeモードの核心です。

こう書くと単純に聞こえますが、実装してみると「どこまでLeadに渡すか」の線引きが難しかったです。LeadはKOLが何人いるかは知っています（Readiness Checkでファイル数と突き合わせるために必要）。しかしLeadはKOL_01が「スキンケア特化の25-34歳フォロワーが多いInstagramクリエイター」であることを知らなくていいです。それを知っているのはkol-01-researchというWorkerのコンテキストだけで十分です。「誰が何を持つか」という境界の設計が、thin_largeモードそのものです。

## Readiness Checkという設計

thin_largeモードにしたことで、次の問いが生まれました。WorkerたちのKOLリサーチが「全員分終わっているか」をLeadはどう判断するのか。

最初は「全WorkerをspawnしてTask完了を待つ」でしたが、Workerがタイムアウトで無音失敗したとき気づけませんでした。5人中4人のリサーチが完了した状態でPhase 3に進んでも、エラーにならず処理が続いてしまいます。Phase 3のPlannerが存在しないKOLのリサーチファイルを参照しようとして初めて、4人分しかないことが判明します。それまで何も起きないのが問題です。

AgentTeamsでWorkerを並列spawnするとき、個々のWorkerの成否を上流のLeadが把握する仕組みは自動的には用意されていません。失敗を検出するには、Workerの出力物の存在をLeadが能動的にチェックする必要があります。Readiness Checkはその能動的チェックを形式化したもので、言い換えると「信頼するな、確認せよ」を指示書に書いたものです。

```
Phase 2→3 Readiness Check:
  ✓ intake_packet.json
  ✓ kol_targets.json
  ✓ product_deep_research/summary.json
  ✓ kol_research_manifest.json
  ✓ kol_research_summary.md
  ✓ manifestに記載されたKOL数 == 実際のresearchファイル数
```

最後の「KOL数の一致チェック」が肝心です。`kol_research_manifest.json`には何名分リサーチされる予定かが記録されています。それと実際のリサーチファイル数が一致しているかを確認することで、「5人中4人しか揃っていないのにPhase 3に進む」バグを防ぎます。Leadは中身を読みません。数と存在だけを確認します。

このチェックリストをLeadのプロンプトに埋め込んでいるので、8フェーズのパイプラインで各フェーズにReadiness Checkを持つと、それだけでLeadのシステムプロンプトのかなりの割合を占有します。コンテキストを節約するためにWorkerに分散したはずのアーキテクチャが、別の形でLeadのコンテキストを膨らませているという皮肉な状態で、現状はまだ解決できていません。

## Phase 4の4分割

thin_largeで後半KOLのコンテキスト問題が落ち着いたあとも、同じ構造の問題がアセット生成フェーズで起きました。

Phase 4（アセット取得・解決）はもともと1回のsubagent spawnで実装していました。クライアントのロゴ取得、グローバルスタイルのAI画像生成、KOL別シーン画像生成、アセット統合をひとつのエージェントが担当する構成です。

KOL 5人案件でこの1エージェント構成を試したとき、4cにあたるKOL別シーン画像がグローバルスタイル（4bで生成されるはずのcampaign_cover）と整合しない画像が出てきました。5人のKOL全員のシーンがそれぞれ独自のスタイルで生成され、キャンペーン全体のビジュアルトンマナがバラバラになった状態です。1エージェントが「全部やる」コンテキストを持っていたために、4bの生成が終わる前に4cの処理が混在してしまいました。

最初はプロンプトで「4bが完了してから4cを始めること」と指示することで解決を試みました。プロンプトで順序を指定すれば守られるだろうという仮定です。実際にやってみると、1つのエージェントが全フェーズを担当しているとき、プロンプトの制約よりコンテキストに積み上がった処理状態のほうが強く動作に影響することがわかりました。4bの生成中に4cの画像生成プロンプトを考え始めるのを、指示書だけでは止めきれませんでした。

そこで4つのsubagentに分割しています。

```
Phase 4a: asset-acquisition
  → クライアントロゴ・商品参照画像を取得
  → 出力: source_assets_manifest.json

Phase 4b: global-style-generator
  → campaign_cover(16:9) / title_cover(16:9) / product_main(9:16) をAI生成
  → 出力: global_assets_manifest.json
  → Gate: 3ファイルがすべて存在すること

Phase 4c: kol-creative-worker × KOL数（並列実行）
  → KOL 1名ずつ独立してspawn
  → シーン画像4枚 + KOLリファレンス画像を生成
  → 4bのGateをパスしていない場合は起動禁止

Phase 4d: asset-resolver
  → source + global + per-KOL を統合
  → 出力: assets_resolved.json (status=ready)
```

4aと4bが直列なのは意図的です。4bでグローバルなビジュアルスタイル（ブランドカラー・トーン）を確定する前に4cのKOL別シーン画像を生成し始めると、スタイルが整合しない画像が出てきます。4bのゲート条件に「`campaign_cover.png`・`title_cover.png`・`product_main.png`の3ファイルが全て存在すること」を設けているのも同じ理由で、画像生成APIが2枚成功して1枚失敗したとき、4bを再実行して3枚揃えてから4cに進みます。

4cが並列実行できるのは、各KOLのworkerがグローバルアセットを「読み取るだけ」で変更しないからです。依存関係を明確に切ることで並列性と安全性が両立します。並列化は最初から目的にした設計ではなく、コンテキストを分離した結果として得られるものでした。

Phase 3のPlannerが生成する`per_kol_packages.json`に、4cに関するひとつ厄介なルールがあります。YouTube Longのみ`scene_count: 6`（3列×2行）で、他のプラットフォームは`scene_count: 4`です。この区別を忘れると、YTLong用スライドの3列目が空カラムになるバグが出ます。

```json
{
  "kol_id": "kol_03",
  "platform": "YTLong",
  "scene_count": 6,
  "render_medium": "semi_real_anime",
  "caption_direction": {
    "required_points": ["成分の浸透感", "朝のルーティン感"],
    "required_words": ["潤い", "自然由来"],
    "ng_expressions": ["〜な感じ", "おすすめ"],
    "note": "ベース文テンプレート禁止 — KOLの口調を維持する"
  }
}
```

`caption_direction`に「ベース文テンプレート禁止」と書いてあるのは、テンプレートを渡すとKOLの固有の口調が潰れてしまうからです。`render_medium`は`hand_drawn_info`・`semi_real_anime`・`commercial_anime`の3択で制約しています。制約を設けないとモデルが「フォトリアル」や「イラスト調」といった曖昧な指定を生成し、4cの画像生成プロンプトが発散するからです。

## stale artifactとの戦い

4分割がうまく機能し始めると、別の問題が浮上しました。今度はコンテキストの混在ではなく、ファイルシステム上での混在です。

PPTXの生成は重いので途中から再実行することが多く、作業ディレクトリには前回の実行アセットが残っています。ある案件でPhase 4bがタイムアウトして中断した翌日に再実行したとき、前日の`campaign_cover.png`が作業ディレクトリに残っていて、ゲートチェックが「3ファイル全部存在する」と判断してPhase 4cが起動しました。その結果、前日のグローバルスタイルとは異なるrunでKOL別シーン画像が生成されて、整合しないアセットがresolver（4d）に流れ込みました。`assets_resolved.json`はstatusがreadyになっていたのにFix Loop（Phase 5-7）でREJECTが続いて、初めて何かおかしいと気づいた、という経緯です。

タイムスタンプで判断しようとも考えました。しかしビルドサーバーの時刻がずれていたりファイルがコピーされたりすると信頼できません。「ファイルが存在するかどうか」だけでは、そのファイルが「今回のrunで生成されたものか」はわかりません。

解決策は、各Phase 4の出力JSONにrun_idを含めることです。

```python
# 各Phase 4 subagentの出力JSONに必ずrun_idを含める
def write_manifest(artifacts: list[dict], run_id: str, output_path: str):
    manifest = {
        "run_id": run_id,
        "generated_at": datetime.utcnow().isoformat(),
        "artifacts": artifacts,
        "status": "ready"
    }
    with open(output_path, "w") as f:
        json.dump(manifest, f, indent=2)

# ゲート判定時にrun_idを照合する
def validate_gate(manifest_path: str, expected_run_id: str) -> bool:
    with open(manifest_path) as f:
        manifest = json.load(f)
    if manifest.get("run_id") != expected_run_id:
        # stale artifact — このPhaseを再実行する
        return False
    return all(
        Path(a["path"]).exists()
        for a in manifest["artifacts"]
        if a.get("required")
    )
```

ゲート判定時にmanifestの`run_id`と`run_state.json`の`run_id`を照合し、不一致であればstale artifactと判断して該当フェーズを再実行します。

このrun_idの仕組みを実装したとき、thin_largeモードでやっていたことと同じ構造だと気づきました。thin_largeでは「5人分のKOLプロファイルが1エージェントのコンテキストに混在する」問題をエージェント分割で解決しました。stale artifactは「今回のrunと前回のrunの成果物が同じファイルシステムに混在する」問題で、run_idはファイルシステム上の状態に「どのrunに属するか」というスコープをつける仕組みです。

どちらも境界のないところに境界を引く、という操作です。thin_largeは「このKOLの情報はこのWorkerのコンテキスト内にある」という境界で、run_idは「このファイルはこのrunに属する」という境界です。Readiness Checkも「このフェーズに進む前にすべての前提条件が揃っている」という境界です。問題の現れ方は違いましたが、修正の形は毎回同じでした。

## まだ解決していないドリフト問題

run_idで成果物のスコープを管理できたのですが、**状態のドリフト問題が残っています。**

`run_state.json`と`plan.json`にはどちらにも`execution_mode`フィールドがあります。この2つは常に一致しなければならないinvariantです。どこかのフェーズで`run_state.execution_mode`を更新し忘れると、Leadが`thin_large`モードで動いているのにplanが`classic_small`を前提にするという状態が生まれます。症状が現れるのは数フェーズ後で、Workerを過剰にspawnしたりLeadが直接処理を抱えてコンテキストが溢れたりします。

```python
# 未実装 — 設計案
def assert_state_plan_invariant(run_state: dict, plan: dict):
    if run_state["execution_mode"] != plan["execution_mode"]:
        raise InvariantViolation(
            f"State/Plan drift detected: "
            f"run_state={run_state['execution_mode']}, "
            f"plan={plan['execution_mode']}"
        )
```

なぜ実装できていないかというと、このチェックをどのタイミングで呼ぶのが正しいかが決まっていないからです。各フェーズの入口で毎回チェックするのが安全ですが、そうするとLeadのプロンプトにinvariantチェックのロジックを何度も書く必要があります。Pythonなら`@phase_entry`デコレータを1行書けば済むのですが、自然言語の指示書ではそのような「フェーズ前処理」の抽象化が難しいです。

ひとつの方向性は、invariantチェック専用のValidatorエージェントを立てることです。各フェーズに進む前にLeadがValidatorをspawnし、Validatorが`run_state.json`と`plan.json`の整合性を確認してOK/NGを返す。LeadはValidatorの結果だけを受け取ればよく、invariantチェックのロジックをLeadのプロンプトに書かずに済みます。ただしエージェントが1つ増えるオーバーヘッドがあり、コンテキストを節約するためにエージェントを分割したはずがコスト構造を複雑にするという、Readiness Checkのときと同じジレンマに戻ってきます。

`execution_mode`のドリフトが実際に問題になったことはまだありません。ただし「ないことを確認した」というより「まだ踏んでいない」という状況です。KOL数が途中で変わる案件（「やっぱり6人にして」という変更）が来たとき、初めてinvariantチェックの実装を迫られると予測しています。

## Phase 5-6-7のFix Loop

Build（Phase 5）→ Visualize（Phase 6）→ Review（Phase 7）はAgentTeamsのFix Loopで実装しています。ReviewerがREJECTを返したとき、`target: data`であればbuilderから、`target: pptx`であればvisualizerから再実行します。最大10回のイテレーションです。

```
Fix Loop:
  REJECT + target: data  → builder再spawn → visualizer → reviewer
  REJECT + target: pptx  → visualizer再spawn → reviewer
  APPROVE                → Phase 8へ
  最大iteration: 10
```

初期の実装でFix Loopが収束しないケースが多かったのですが、原因はReviewerの`target`フィールドの精度でした。Reviewerが「スライドの数値が間違っている（→ data）」と「テキストの位置がずれている（→ pptx）」を正確に区別できないと、builderを再実行しても問題がvisualizerにあったというすれ違いが起きます。ReviewerのシステムプロンプトにREJECT判断基準の詳細を書いて初めてループが収束するようになりました。

Visualizerで見落としていたのがフォント色の明示指定です。テーマ継承色（inherited）を使うとPowerPointとKeynoteで異なる表示になります。Visualizerのシステムプロンプトに「テキスト書き込み時は必ず明示的なフォント色（030303）を設定すること、テーマ継承色は使用禁止」というルールを追加したところ、REJECT率が大幅に下がりました。PPTXの互換性問題はビューワーの解釈に依存するため、実際に複数のビューワーで確認するまで気づけませんでした。これもまた「どのビューワーか」という境界の問題と言えます。

:::details Skillの統合と分離

このシステムを作る前、intake・product-research・kol-research・exportはそれぞれ独立したtier2 Skillとして実装していました。現在はオーケストレーター内の参照ドキュメント（`reference/*.md`）として統合しています。

判断基準は「毎回呼ばれるか」です。独立Skillとして残しておくとSkillルーターによる検索・ロードのコストがかかります。参照ドキュメントとして統合するとオーケストレーター起動時のコンテキストが増えます。intake・product-research・kol-researchはほぼ毎回呼ばれるので統合を選びました。exportは案件によってはSkip可能なので独立のままにしています。

統合は元に戻す工数がかかります。intakeのロジックを別のオーケストレーターでも使いたくなったとき、参照ドキュメントとして埋め込まれていると取り出すのが面倒です。統合はコンテキスト効率を上げますが、モジュール性を犠牲にします。

:::

---

`execution_mode`のドリフト問題がまだ残っているということは、まだ境界を引き切れていない場所があるということでもあります。KOL数が途中で変わる案件は今のところ「新規runとして再実行」という運用で回避していますが、これは設計ではなくオペレーションによる回避です。設計で解決していないことをオペレーションで隠しているとき、いつかそのオペレーションが破綻します。次に壊れるとしたら、たぶんそこです。
