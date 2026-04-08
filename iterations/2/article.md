---
title: "Claude Codeで投稿指示書自動生成システムを作った話 — KOLが増えるほど壊れていくオーケストレーターとどう戦ったか"
emoji: "🎬"
type: "tech"
topics: ["claudecode", "ai", "architecture"]
published: true
---

KOLが4人を超えたとき、システムは静かに壊れ始めました。エラーは出ません。処理は完走します。でも生成されるクリエイティブ計画の質が、KOLを追うごとに明らかに落ちていきます。**この問題は「コンテキストの境界をどこに引くか」という1つの問いに帰着しました。** エージェントの分割も、stale artifactの検出も、Readiness Checkも、すべてその問いへの異なる答えです。

## KOLが4人を超えたとき、何が起きたか

マーケティングの受注案件で、KOL（インフルエンサー）向けの投稿指示書をPPTXで自動生成するシステムを作りました。入力は受注資料のPDFとKOLリスト。出力はKOL別・プラットフォーム別のスライドデッキで、各スライドにはKOLのクリエイティブ方向性、キャプション方向性、AIで生成したシーン画像、市場の法規制に基づいたcaution_pointsなどが入ります。

処理はPhase 0から8までの8フェーズで構成されています。受注資料のパースから始まり、製品リサーチ、KOLリサーチ、クリエイティブプランニング、アセット生成、スライドビルド、ビジュアライズ、レビュー、エクスポートまで一気通貫で処理します。

最初のバージョンはシンプルでした。LeadエージェントがKOLリサーチをすべて担当し、そのままクリエイティブプランニングに流し込む。KOLが2〜3人なら問題なく動いていました。

KOLが4人を超えると、Leadのコンテキストが壊れ始めました。

具体的に何が起きたかというと、Phase 3（クリエイティブプランニング）で4人目のKOLに対して生成された`caption_direction`が、1人目のKOLとほぼ同一の内容になっていました。「潤い」「自然由来」というワードが全員分のキャプション方向性に繰り返され、KOL個人の口調や投稿スタイルの個性がどこにも反映されていませんでした。リサーチで取得した「フォロワー属性」「投稿トーン」「カテゴリ別エンゲージメント」などの情報がプランニングに生きていない状態です。

モデルが情報を「忘れる」というより、限られたアテンションが全KOL分の情報に薄く広がって、どのKOLにも同じようなデフォルト調の出力になっていく感覚です。各KOLのリサーチが4人分積み重なると、Leadが持つコンテキストは「広くて浅い状態」になります。

これが、システムを2モードに分岐させた理由です。

```json
// checkpoint/run_state.json の一部
{
  "execution_mode": "thin_large",
  "kol_count": 5,
  "phase": 2
}
```

`classic_small`（KOL≤3）ではLeadが直接リサーチの一部を担当できます。`thin_large`（KOL≥4）ではLeadは成果物ゲートの管理だけに専念し、すべての処理をWorkerに委譲します。LeadがKOLのコンテキストを「所有」しないようにするのが、thin_largeの本質です。

thin_largeで重要なのは、Leadが何を「知らない」かを設計することです。LeadはKOLリサーチの詳細を読み込みません。Workerがリサーチしてファイルとしてアウトプットしたものを、Leadは存在チェックだけします。「Workerが書いたファイルが全件揃っているか」という確認のためだけにLeadはKOL数を知っていて、中身は読まない。この設計、言葉にすると単純なんですが、「どこまでLeadに渡すか」の線引きは実装してみると割と難しいです。

## Phase 3に進む前のReadiness Check

thin_largeモードで次に問題になったのが、Phase 2（KOLリサーチ）からPhase 3（クリエイティブプランニング）への移行タイミングです。

WorkerたちのKOLリサーチが「全員分終わっているか」をLeadはどう判断するのか。最初は「Workerを全部spawnして完了を待つ」という実装でしたが、これはWorkerのひとつが無音で失敗したとき（タイムアウト等）に気づけませんでした。5人分のKOLをspawnして4人分しかファイルが生成されていないのに、LeadはPhase 3に進もうとします。そして4人分のデータでプランニングを実行した結果、1人分のKOLが抜けた指示書が出来上がる。レビュー段階まで気づけないことがありました。

そこでPhase 3への移行前に、LeadがReadiness Checkを実行するようにしました。

```
Phase 2→3 Readiness Check:
  ✓ intake_packet.json が存在するか
  ✓ kol_targets.json が存在するか
  ✓ product_deep_research/summary.json が存在するか
  ✓ kol_research_manifest.json が存在するか
  ✓ kol_research_summary.md が存在するか
  ✓ manifestに記載されたKOL数 == 実際のresearchファイル数
```

最後の「KOL数の一致チェック」が肝心です。`kol_research_manifest.json`にはKOLが何名分リサーチされる予定かが記録されています。それと実際のリサーチファイル数が一致しているかを確認することで、「5人中4人分しか揃っていないのにPhase 3に進んでしまう」バグを防いでいます。

1件でも欠落があればPhase 3には進まず、欠落したartifactの再取得を試みます。ここでも、Leadは「中身を読む」のではなく「数と存在を確認する」という役割に留まっています。

余談ですが、このチェックリストをLeadのプロンプトに埋め込んでいるので、チェック項目が増えるたびにLeadのシステムプロンプトが太くなっていきます。コンテキストを節約するために分離したはずの設計が、別の形でコンテキストを消費しているというのは少し皮肉です。

## Phase 4を4分割した理由

同じ発想をPhase 4（アセット取得・解決）にも適用しました。

Phase 4はもともと1回のsubagent spawnで実装していました。クライアントのロゴ取得、グローバルスタイルのAI画像生成、KOL別シーン画像生成、そしてすべてのアセットを統合するresolverをひとつのエージェントが担当するイメージです。

これも同じパターンで壊れました。KOLが増えると、ひとつのエージェントが「ロゴを取得しながらグローバルカバーを生成しながらKOL別シーン画像を並列で考える」状態になり、生成される画像のスタイルが一貫しなくなりました。具体的にはグローバルスタイル（キャンペーンカバー）と各KOLのシーン画像のカラートーンがバラバラになり、同じデッキとして成立しない見た目になりました。

そこで4つのsubagentに分割しています。

```
Phase 4a: asset-acquisition
  → クライアントロゴ・商品参照画像を取得
  → 出力: source_assets_manifest.json

Phase 4b: global-style-generator
  → campaign_cover / title_cover / product_main をAI生成（16:9 / 9:16）
  → 出力: global_assets_manifest.json
  → Gate: 3ファイルがすべて存在すること

Phase 4c: kol-creative-worker × KOL数（並列実行）
  → KOL 1名ずつ独立してspawn
  → シーン画像4枚 + KOLリファレンス画像を生成

Phase 4d: asset-resolver
  → source + global + per-KOL を統合
  → 出力: assets_resolved.json (status=ready)
```

4cが並列実行できるのは、各KOLのworkerがグローバルアセットを「読み取るだけ」で変更しないからです。4bのゲートをパスしていない状態で4cを起動することは禁止しています。

4aと4bが直列なのも意図的です。4bでグローバルなビジュアルスタイルを確定する前に4cのKOL別シーン画像を生成し始めると、スタイルが整合しない画像が出てきます。先にブランドカラーとトーンを固めてから個別に展開する、という順序を強制するためです。

4bのゲート条件として「`campaign_cover.png` + `title_cover.png` + `product_main.png` の3ファイルが全て存在すること」を設けています。これは画像生成APIが部分的に成功して部分的に失敗するケースへの対処です。2枚生成できて1枚失敗した場合、4bを再実行して3枚揃えてから4cに進みます。ゲート条件を「少なくとも1枚」にしていたら、整合性のないアセットで後続フェーズが動いてしまいます。

## 分割したら別の問題が生まれた

4分割はうまく機能しましたが、新しい問題を生み出しました。

前回の実行で生成されたファイルが残っているとき、次の実行でそれを「今回の成果物」と誤認してPhaseをスキップするバグが発生しました。PPTXの生成は重いので途中から再実行することが多く、作業ディレクトリにはよく前回のアセットが残っています。

ファイルの存在チェックだけではこのバグを防げません。`campaign_cover.png`が存在するかどうかを確認しても、それが「今回のrun_idで生成されたものか」はわからないからです。タイムスタンプで判断しようとも考えたのですが、ファイルがコピーされたり環境によって時刻がずれたりすることがあり、信頼できませんでした。

**解決策はrun_idによる成果物のタグ付けです。**

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

ゲート判定時にmanifestの`run_id`と`run_state.json`の`run_id`を照合し、不一致であればstale artifactと判断して該当Phaseを再実行します。

コンテキスト爆発の問題とstale artifactの問題は違う層の話に見えますが、「スコープの混在」という構造は同じです。コンテキスト爆発は複数のKOLの情報が1エージェントのコンテキストに混在する問題で、stale artifactは複数のrunの成果物が同じファイルシステムに混在する問題です。run_idはファイルシステム上の状態に「どのrunに属するか」というスコープをつける仕組みです。

## run_stateのドリフトという未解決問題

run_idで成果物のスコープを管理できたのですが、別のドリフト問題が残っています。

`run_state.json`には`execution_mode`フィールドがあり、`plan.json`にも同名のフィールドがあります。この2つは常に一致しなければならないinvariantです。しかし現状、このinvariantを保証するコードはありません。

どこかのPhaseで`run_state.execution_mode`を更新し忘れると、Leadが`thin_large`モードで動いているのにplanが`classic_small`を前提にするという状態が生まれます。この不一致の検出が難しい理由は、症状が現れるのが数フェーズ後になるからです。Workerを過剰に立てたり、逆にLeadが直接処理を抱えようとしてコンテキストが溢れたりします。発生源のフェーズと症状が現れるフェーズが離れているので、ログを見てもすぐには原因がわかりません。

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

なぜ実装できていないかというと、このチェックをどのタイミングで呼ぶのが正しいかがまだ決まっていないからです。各Phaseの入口で毎回チェックするのが安全ですが、そうするとLeadのプロンプトにinvariantチェックのロジックを何度も書く必要があります。共通のPhase前処理としてどう表現するかは、現在の実装では解決できていません。

Pythonのデコレータのような「フェーズ前処理」の仕組みをLLMオーケストレーターでどう実現するかという問いに言い換えられます。コードなら`@phase_entry`デコレータを1行書けば済みますが、自然言語の指示書ではそうはいきません。

## Phase 5-6-7のFix Loopで気づいたこと

Build（Phase 5）→ Visualize（Phase 6）→ Review（Phase 7）はAgentTeamsのFix Loopで実装しています。ReviewerがREJECTを返したとき、`target: data`であればbuilderから、`target: pptx`であればvisualizerから再実行します。最大10回までイテレーションします。

```
Fix Loop:
  REJECT + target: data  → builder再spawn → visualizer → reviewer
  REJECT + target: pptx  → visualizer再spawn → reviewer
  APPROVE                → Phase 8へ
  最大iteration: 10
```

このループで一番効いたのは、`target`フィールドの精度を上げることでした。初期の実装ではReviewerが「これはデータの問題か、PPTXレンダリングの問題か」を正確に区別できず、builderを再実行したのに問題がvisualizerにあった、という無駄なroundtripが多発していました。

ReviewerのプロンプトにREJECT判断の基準（「スライドの数値が正しくない → data」「テキストの位置がずれている → pptx」）を詳細に書いて初めて精度が上がりました。Reviewerが持つ判断基準の精度が、Fix Loopの収束速度を直接決めます。

もう一点、visualizerに「フォント色を必ず明示的に指定すること（030303）、テーマ継承色は使わないこと」というルールを入れていなかったとき、生成されるPPTXがPowerPointとKeynoteで違う見え方をすることがありました。テーマ継承色（inherited）はビューワーによって解釈が変わるため、PPTXの互換性を保つには明示的な色指定が必須です。このルールをvisualizerのシステムプロンプトに追加しただけでREJECT率が大幅に下がりました。

なかなか厄介なのは、`target: data`のREJECTが続くとbuilderが毎回同じエラーを繰り返す可能性がある点です。10回のイテレーション上限はその安全弁ですが、同じREJECT理由が3回以上続いた場合の「エスカレーション」はまだ実装していません。

:::details 余談：Skill統合とコンテキストのトレードオフ

このシステムを作る前、intake・product-research・kol-research・exportはそれぞれ独立したtier2 Skillとして実装していました。それをオーケストレーター内の参照ドキュメント（`reference/*.md`）として統合しました。

独立Skillとして残しておくとSkillルーターによる検索・ロードのコストがかかります。一方、参照ドキュメントとして統合するとオーケストレーター起動時のコンテキストが増えます。「毎回必ず使うか」が分岐点で、intake・product-research・kol-researchはほぼ毎回呼ばれるので統合を選びました。exportは案件によってはSkip可能なので独立のままにしています。

ただし統合は元に戻す工数がかかります。再利用の需要が出てきたとき、参照ドキュメントとして埋め込まれていると取り出すのが面倒です。

:::

---

`execution_mode`のドリフト問題は依然として残っていますが、次にもっと気になっているのはPlanner側の話です。市場別のcaution_points（景品表示法、FTCガイドライン等）がPlannerのコンテキストにハードコードされていて、規制が変わっても自動では更新されません。誰かが更新を忘れた場合の検出機構がなく、古いcaution_pointsのままKOLにポストさせると法的リスクになります。これはrun_idで解決したファイルシステムのstale問題と同じ構造で、コンテキストに埋め込まれた知識がいつ「stale」になるかを追跡できていない問題です。次に何かが壊れるとしたら、まだ境界を引いていないそこかもしれません。
