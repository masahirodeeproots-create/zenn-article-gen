---
title: "KOLが増えるほど壊れていくオーケストレーターとどう戦ったか"
emoji: "🎬"
type: "tech"
topics: ["claudecode", "ai", "architecture"]
published: true
---

KOL向け投稿指示書の自動生成システムを作っていて気づいたのは、**エージェントの失敗はほぼすべて「コンテキストが想定以上に膨らんだとき」に発生する**という事実でした。KOLが増えるたびに何かが壊れ、修正を重ねた結果が今の構造です。これはその記録です。

## アセット生成を1つのエージェントに任せると何が起きるか

システムの中核はPPTXデッキの生成です。受注済みのインフルエンサーマーケティング案件ごとに、KOL別・プラットフォーム別の指示書スライドを生成します。各デッキにはクライアントのロゴ、AI生成のキャンペーンカバー、KOL専用のシーン画像が含まれます。

最初の実装では、アセット生成をすべて1つのサブエージェントが担っていました。「全アセットを取得・生成してください」という指示を1回発行する設計です。KOLが2〜3人の案件ではこれが機能していました。

KOL数が5人を超えたとき、初めてデッキの中身を見て問題に気づきました。4人目のKOLのシーン画像が、1人目のKOLとほぼ同じ構図・色調になっていたんです。KOLごとに異なるビジュアルイメージを指定したにもかかわらず、後半のKOLへの指示が実質的に無視されていました。

この失敗の原因を追うと、コンテキストの積み上がり方の問題でした。KOL 1人あたり4枚のシーン画像が必要で（YouTube Long形式は6枚）、5人なら20〜24枚分の生成指示と確認結果が1つのコンテキストに積み重なります。そこにグローバルアセット（キャンペーンカバー16:9、タイトルカバー21:9、商品メイン9:16）の生成状態も加わります。コンテキストが一定のサイズを超えると、エージェントは後半の指示を前半の指示と区別できなくなるようで、「このKOLには何を生成したか」という追跡が崩れていきます。

解決策として Phase 4 を4つの独立したサブエージェント起動に分割しました。

```
Phase 4a: asset-acquisition
  受注資料からクライアントロゴ・商品参照画像を取得
  → source_assets_manifest.json

Phase 4b: global-style-generator
  キャンペーン全体に共通するアセットをAI生成
    - キャンペーンカバー (16:9)
    - タイトルカバー    (21:9)
    - 商品メイン        (9:16)
  → global_assets_manifest.json
  Gate: 上記3ファイルの存在確認 AND run_id の一致

Phase 4c: kol-creative-worker × KOL数（並列実行可）
  KOL 1名ずつ独立してspawn
  → per_kol_assets_{slug}.json + scene 画像 4〜6枚
  ※ 4b の Gate をパスしていない場合、4c の起動を禁止

Phase 4d: asset-resolver
  source + global + per-KOL アセットを統合
  → assets_resolved.json (status=ready)
```

4cでKOL 1名ずつ独立したworkerをspawnするようにしたことで、各workerのコンテキストは「担当KOL 1名のプロファイル + 4〜6枚の画像生成結果」に限定されます。KOL数が増えても各workerの負荷は変わらないので、後半のKOLの品質が前半より落ちるという現象が解消されました。

4bのゲートを4c起動の前提条件にしているのは、グローバルスタイルが確定する前にKOL別シーン画像を生成すると視覚的一貫性が崩れるためです。この依存関係をコードで明示しないと、並列化の最適化を入れたときに順序が狂います。以前まさにそれが起きました。

ただしこの分割には代償があります。4a〜4dの各spawnのオーバーヘッドが積み重なるので、KOL 2〜3人の小規模案件では処理時間が増えます。これが後述の`classic_small`モードを設けた理由の一つです。

## stale artifactがゲートをすり抜けるまで

Phase 4を分割した後、今度は「前回の実行で生成したファイルが今回の成果物として認識される」問題が出てきました。

実際に起きたのはこういうケースです。案件Aの初回実行がPhase 4b完了後に中断し、`campaign_cover.png`などのグローバルアセットがワークスペースに残った状態で修正後の再実行をしました。Phase 4bが今回の実行で失敗したとしても、ゲートチェックはワークスペースに残っていた前回の`campaign_cover.png`を発見して「4b完了」と判断します。そのまま4cが走り出し、古いカバーと今回生成したKOL画像が混在したデッキが完成しました。

厄介なのは**この状況でエラーが記録されない**ことです。ゲートチェックの観点では「ファイルが存在する = 成功」なので、ログに失敗が残りません。「成功したはずの実行が間違ったアウトプットを出す」という状態になり、再現条件の特定に数時間かかりました。

対策として、各Phase 4 spawnの出力JSONに`run_id`を埋め込む方式を採用しました。

```json
{
  "run_id": "20240315T092344Z",
  "phase": "4b",
  "status": "completed",
  "assets": {
    "campaign_cover": "cache/images/global/campaign_cover.png",
    "title_cover":    "cache/images/global/title_cover.png",
    "product_main":   "cache/images/global/product_main.png"
  }
}
```

実行開始時に`checkpoint/run_state.json`へ`run_id`を書き込んでおき、ゲート判定でこの値を照合します。

```python
def validate_phase_gate(manifest_path: str, run_state: dict) -> GateResult:
    if not os.path.exists(manifest_path):
        return GateResult(passed=False, reason="manifest_not_found")

    with open(manifest_path) as f:
        manifest = json.load(f)

    current_run_id = run_state["run_id"]
    artifact_run_id = manifest.get("run_id")

    if artifact_run_id != current_run_id:
        logger.warning(
            f"Stale artifact: {manifest_path} "
            f"(artifact={artifact_run_id}, current={current_run_id})"
        )
        return GateResult(passed=False, reason="stale_artifact", stale=True)

    if manifest.get("status") != "completed":
        return GateResult(passed=False, reason="incomplete")

    return GateResult(passed=True)
```

`stale=True`が返ると、オーケストレーターは「ファイルは存在するが今回のものではない」として該当Phaseを再実行します。

`run_id`の形式は`datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')`を使っています。UUIDではなく日時ベースの文字列にしたのは、デバッグ時に生成タイムスタンプが一目でわかるためです。秒単位で複数の実行が走るケースでは衝突する可能性はありますが、現時点では手動再実行がメインで秒単位の衝突は実用上発生していません。スケジュール自動実行を入れる段になればUUIDに切り替える予定です。

またワークスペースをクリアする代わりに`run_id`で鮮度を管理する設計にしたので、前回の生成物をデバッグ時に参照できるという副次的な利点があります。比較してみると今回の失敗がどこで起きたかわかりやすいです。

## KOL数でオーケストレーターの構造が切り替わる

Phase 4の分割とrun_idの問題が落ち着いたあと、もう一つの問題が残っていました。オーケストレーター自体（Lead）がKOL数に比例して処理を抱え込みすぎることです。

Phase 2のKOLリサーチで1名ずつ調査結果を読み込んでいくとき、KOL数が多いとLead自身のコンテキストが膨らみます。これが問題として現れたのは、Phase 2完了後にPhase 3のCreative Plannerを起動したとき——Plannerへの指示の質が、KOL数が少ない案件と比べて明らかに粗くなっていました。Plannerに渡す`per_kol_packages.json`の`caption_direction`フィールドが、KOL 5〜6人目では「〜をぜひ試してください！」という汎用フレーズだらけになっていて、各KOLの個性が反映されていませんでした。

この問題に対してオーケストレーターを2モードで動かす構造を導入しました。

```
classic_small: KOL ≤ 3
  Lead が intake / asset 周りの一部を直接処理できる
  Phase 4c 並列spawn なし

thin_large: KOL ≥ 4
  Lead は phase gate 管理と handoff に専念
  全処理をサブエージェントに委譲
```

モードは`checkpoint/run_state.json`に保存します。

```json
{
  "run_id": "20240315T092344Z",
  "execution_mode": "thin_large",
  "kol_count": 6,
  "current_phase": "phase4c"
}
```

ここで注意が必要なのが、`run_state.execution_mode`と実際のKOL数のドリフトです。Phase 0でKOL数を確認して`classic_small`と記録したあと、Phase 2のKOLリサーチ中にリストへの追記が発生してKOL数が4を超えると、run_stateは`classic_small`のままで実際の要件は`thin_large`になります。今のところPhase 2完了後の手動確認ステップで補っていますが、この確認を忘れた場合にサイレントに間違ったモードで実行が続くリスクがあります。

対処として各Phase間のゲートにinvariant checkを追加するつもりでいます。

```python
# 未実装 — 設計案
def check_execution_mode_invariant(run_state: dict, kol_manifest: dict) -> None:
    """
    Phase 2→3 および Phase 3→4 の遷移ゲートで呼び出す。
    KOL数と execution_mode の整合性を確認する。
    """
    actual_kol_count = len(kol_manifest.get("kols", []))
    expected_mode = "thin_large" if actual_kol_count >= 4 else "classic_small"
    recorded_mode = run_state.get("execution_mode")

    if recorded_mode != expected_mode:
        raise InvariantViolation(
            f"execution_mode drift: run_state={recorded_mode}, "
            f"kol_count={actual_kol_count} requires {expected_mode}. "
            f"Update run_state before proceeding."
        )
```

これをPhase 2→3の遷移ゲートに挟めば、KOLリストが途中で変わるケースに自動対処できます。Phase 3→4でも同様に確認する必要があります。いずれの遷移でも`kol_manifest`が確定しているので照合は簡単なはずです。

ただし現時点ではまだ実装していません。動的KOLリスト変更が実運用でどれくらいの頻度で発生するか、もう少し実績を積んでから実装するか判断するつもりです。

## Phase 3: Plannerが1KOLずつの指示書を作るとき

`thin_large`モードでLeadが指示品質の問題を抱えていた原因の一つは、Leadが渡すべき構造化データ——`per_kol_packages.json`——のスキーマが曖昧だったことです。Phase 3のPlannerがこのJSONを生成し、Creative Worker（Phase 4c）とBuilder（Phase 5）がそれぞれ入力として使います。

```json
{
  "kol_id": "kol_003",
  "slug": "yuki_natural",
  "platform": "instagram",
  "scene_count": 4,
  "render_medium": "semi_real_anime",
  "caption_direction": {
    "required_appeal": ["保湿力の持続性", "無添加処方"],
    "required_words": ["潤い", "自然由来"],
    "ng_expressions": ["ぜひ試してください", "おすすめです"],
    "note": "ベース文テンプレート禁止。KOLの口調を活かすこと。"
  },
  "caution_points": [
    "#PR 表示を必ず含める（景品表示法）",
    "効果効能の断言禁止（薬機法）",
    "「治る」「改善」等の医療的表現禁止"
  ]
}
```

`ng_expressions`フィールドに「ベース文テンプレートを禁止する」という注記を入れているのは、キャプションの型を与えすぎるとKOLの口調が消えてしまう問題への対処です。Plannerが汎用フレーズをテンプレートとして渡すと、そのKOLのフォロワーが見たときに「これ誰が書いたキャプション？」と感じます。フォロワーはそのKOLの言葉遣いに愛着を持っているので、テンプレート調のキャプションは逆効果です。

`scene_count`はプラットフォームによって変わります。YouTube Longだけ6（3列×2行のグリッドレイアウト）で、それ以外は4です。Plannerへの指示にこのルールを明記しておかないと、Plannerは全プラットフォームで4を選んでしまいます。YouTube Longで4を設定すると空カラムが表示されるバグが出るので、ここは明示的に制約する必要がありました。

`caution_points`の内容は市場によって変わります。JPなら景品表示法・薬機法ベース、USならFTCのendorsement guidelinesに基づく`#ad`表示、TH/VN/IDは各国規制に準拠したポイントです。Plannerが市場を誤認識すると`caution_points`の内容が丸ごと間違いになるので、Phase 1のIntakeで市場を確定してからPhase 3に入る順序は崩せません。

---

`execution_mode`のドリフト問題はまだ手動確認で補っています。これが次に何かを壊すとしたら、並列実行のスケジュール自動化を入れたタイミングでしょう。

:::details Phase 5-8: Build〜Export のFix Loop

Build（Phase 5）→ Visualize（Phase 6）→ Review（Phase 7）はAgentTeamsで実行しています。

```
Fix Loop (AgentTeams 内):
  ReviewがREJECTを返した場合:
    target: data  → Builder を再spawn → Visualizer → Reviewer
    target: pptx  → Visualizer を再spawn → Reviewer
  最大 iteration: 10
  APPROVE → Phase 8 (Export)
```

Visualizerには1つ固定のルールがあります。PPTXにテキストを書き込む際、フォント色に`030303`を明示的に指定すること。テーマ継承色（inherited）の使用を禁止しています。一部のPPTX互換環境でテーマ継承色が正しく表示されないため、色を明示指定することで環境依存の見た目崩れを防ぎます。

Visualizerのspawn時には必ず以下のプロンプトフラグメントを含めるようにしています。

```
CRITICAL: テキスト書き込み時に必ず明示的なフォント色を設定すること。
テーマ継承色（inherited）は使用禁止。全てのテキスト run に solidFill で 030303 を設定する。
ただし _bg / _fill / _header / _label / _Label / _Breadcrumb を含む Shape は例外とし、
テンプレートのフォント色を維持すること。
visible:false の Shape はテキストを空にしてからオフキャンバスに移動すること。
endParaRPr 順序修正を binding 最終ステップとして実行すること。
```

Fix Loopでbuilderを再spawnする場合も同じプロンプトを使います。

:::
