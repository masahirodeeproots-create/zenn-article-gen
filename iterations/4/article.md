---
title: "KOLが増えるほど壊れていくオーケストレーターとどう戦ったか"
emoji: "🔧"
type: "tech"
topics: ["claudecode", "ai", "architecture", "agentteams"]
published: true
---

KOL向け投稿指示書をPPTXで自動生成するシステムを作っています。受注書とKOLリストを食わせたら、商品リサーチからデッキ生成まで一気通貫で出力するオーケストレーターです。

3人のKOLで動かしている間は順調でした。6人に増やした瞬間、5人目のキャプション方向性が1人目とほぼ同一になりました。「潤い」と「自然由来」を繰り返すだけの指示書です。エラーは出ていません。処理は正常に完走しています。でも出力が壊れている。

この記事はその問題の正体を追った記録です。結論を先に書くと、壊れ方はすべて「ファイルは存在するが、中身が今回の実行にとって正しいかをシステムが知らない」という同じ構造を持っていました。

## 「コンテキストが溢れている」は半分しか正しくなかった

最初の設計はシンプルな直列パイプラインです。

```python
for phase in [intake, kol_research, creative_plan, asset, build, review]:
    result = run_subagent(phase, inputs=previous_outputs)
```

Intakeで受注書をパースし、KOL Researchで各KOLを調べ、Creative Planningでキャプション方向性やシーン構成を決め、Assetで画像を生成し、BuildでPPTXを組み立て、Reviewで品質チェック。各Phaseはsubagentとして動き、成果物をファイルで渡す構成です。

6人のKOLで5人目の出力が1人目と同じになった原因を、最初はコンテキストウィンドウの上限だと考えました。全KOLのリサーチ結果を1つのsubagentに載せると、後半でコンテキストが溢れて前半のキーワードを繰り返すのだろうと。

この仮説に基づいてKOL数で実行モードを分け、4人以上の場合はLeadがgate判定だけに徹する`thin_large`モードを導入しました。

```python
if len(kol_list) <= 3:
    mode = "classic_small"   # Leadがintake/asset周りを直接処理
else:
    mode = "thin_large"      # Leadはsummary/handoff/gate判定のみ
```

ただ、これだけでは直りませんでした。`thin_large`にしてLeadのコンテキストを軽くしても、アセット生成のsubagent自体が全KOLの画像を1つのコンテキストで処理していたので、そこで同じ問題が再現します。

Leadのコンテキストを節約しても、Phase 4のdesignerが6人分のシーン画像24枚を一気に扱っている限り、後半のKOLの画像は前半と同じスタイルに収束してしまいます。ここからPhase 4の分割に話が進みます。

## 1つのsubagentに全画像を任せると何が起きるか

Phase 4（アセット生成）は、最初は1つのdesignerサブエージェントが全部やっていました。ロゴ取得、キャンペーンカバー画像のAI生成、KOLごとのシーン画像4枚の生成、そして最終的なアセット統合。6人のKOLだとシーン画像だけで24枚です。

3人目のKOLのシーン画像が前の案件のまま残っていたことがありました。新しい案件を流したのにキャンペーンカバーだけ新しくなっていて、KOL 3人目のシーン画像だけ古い。

最初はファイルパスが被ってキャッシュが残っているのかと思いました。でもファイルのタイムスタンプを見ると、古いファイルは前回の実行時刻のままです。つまり今回の実行では3人目の画像生成自体が失敗してスキップされていた。ファイルが「存在する」のでGateチェックは通過してしまったんです。

もう1つ。画像生成が途中でコケて、最後のKOLの画像がないままBuildに進んだケースもありました。designerサブエージェントが4人目まで処理した時点でコンテキストが限界に達し、5人目と6人目の画像がないまま次のPhaseに遷移していました。

Phase 4を4つに分割しました。

```
Phase 4a: Asset Acquisition
  ロゴ・商品参照画像を取得 → source_assets_manifest.json

Phase 4b: Global Style Gen
  campaign_cover(16:9) + title_cover(21:9) + product_main(9:16)
  → global_assets_manifest.json
  Gate: 3ファイルが全て存在すること

Phase 4c: KOL Creative × KOL数
  KOL 1名ずつ独立してsubagent spawn
  各KOLのシーン画像4枚 + KOLリファレンス画像

Phase 4d: Asset Resolve
  全アセットを統合 → assets_resolved.json (status=ready)
```

4cでKOL 1名ずつ別のsubagentを起動します。1人がコケても他に影響しません。

4bと4cの順序は重要です。以前並列化を急いで4bと4cを同時に走らせたとき、KOLごとにまるで別のブランドのようなビジュアルが生成されました。4cのworkerはglobal_assets_manifest.jsonを参照してスタイルを統一するので、4bが完了する前に4cを起動してはいけません。4bのゲートに「3ファイルが全て存在すること」を要求しているのは、画像生成APIが2枚成功して1枚失敗するケースへの対処です。

分割はうまく機能しましたが、新しい問題を生みました。

## 「ファイルが存在する」と「正しいファイルが存在する」は違う

Phase 4を分割して各subagentの出力をGateでチェックする設計にしたのですが、このGateが「ファイルの存在チェック」だけだったのが次の問題です。

前回の実行が途中で失敗して再実行したとき、作業ディレクトリには前回生成された`campaign_cover.png`が残っています。今回の実行でPhase 4bが失敗しても、Gateは前回のファイルを「今回の成果物」だと思って通過させます。

この問題を最初はファイルのタイムスタンプで解決しようとしました。「実行開始時刻以降に更新されたファイルだけを有効とする」というロジックです。でもビルドサーバーの時計がずれていたり、ファイルのコピーでタイムスタンプが変わったりして信頼できませんでした。

次に考えたのが、実行ごとにディレクトリを分ける方法です。`output/run_20260409T120000Z/`のように。でもこれだと過去の実行結果と今回の差分を比較するのが面倒になります。デバッグでは「前回と今回の出力の違い」を同じディレクトリ構造で見たいことが多いんですよね。

最終的に、run_id contractという仕組みに落ち着きました。

```python
from datetime import datetime, timezone

# 実行開始時にrun_idを生成してrun_state.jsonに保存
run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
```

各Phase 4のsubagentが出力する`*_phase_result.json`に`run_id`フィールドを含めます。

```python
def check_phase_gate(phase_result_path, current_run_id):
    """Gateチェック: ファイルの存在だけでなくrun_idの一致も確認"""
    if not os.path.exists(phase_result_path):
        return False
    
    result = load_json(phase_result_path)
    if result.get("run_id") != current_run_id:
        # stale artifact: ファイルは存在するが今回のものではない
        logger.warning(f"Stale artifact detected: {phase_result_path}")
        return False
    
    return result.get("status") == "completed"
```

run_idが一致しなければstale artifactとして無視し、そのPhaseを再実行します。日時ベースの文字列にしたのは、デバッグ時に「この成果物はいつの実行で生成されたか」が一目でわかるからです。

ではrun_idを入れればすべて解決かというと、そうでもありませんでした。

## Readiness Checkが拾った「存在するけど不完全」な成果物

5人のKOLで回したとき、3人目のKOLだけクリエイティブプランが異常に薄かったんです。キャプション方向性が「フォロワーに響くコンテンツ」という1文だけ。他のKOLには「保湿力の持続性」「無添加処方への共感」のような具体的な方向性が書かれているのに、3人目だけ抽象的です。

調べてみると、そのKOLのリサーチファイル自体が`research/`ディレクトリにありませんでした。Phase 2（KOL Research）が部分的に失敗しているのに、Phase 3（Creative Planning）に進んでしまっていた。

run_id contractはこの問題を防げません。run_idは「このファイルが今回のrunに属するか」を検証しますが、「必要なファイルが全部揃っているか」は検証しません。`kol_research_manifest.json`は5人分のエントリがあるのに、実際のリサーチファイルは4人分しかない。マニフェストのrun_idは正しいし、マニフェスト自体は存在している。でも中身が不完全です。

Phase 2→3の遷移前にReadiness Checkを導入しました。

```python
def check_phase3_readiness(project_dir):
    required_files = {
        "intake_packet":     "planning/intake_packet.json",
        "kol_targets":       "planning/kol_targets.json",
        "product_research":  "research/product_deep_research/summary.json",
        "kol_manifest":      "research/kol_research_manifest.json",
        "kol_summary":       "planning/kol_research_summary.md",
    }
    
    for name, path in required_files.items():
        if not (project_dir / path).exists():
            return False, f"{name} missing"
    
    # マニフェストのKOL数 vs 実ファイル数
    manifest = load_json(project_dir / "research/kol_research_manifest.json")
    expected = len(manifest["kols"])
    actual = len(list((project_dir / "research/kol_research").glob("*.json")))
    
    if actual != expected:
        return False, f"KOL research: {actual}/{expected} files"
    
    return True, "ready"
```

最後の「マニフェストのKOL数と実ファイル数の一致チェック」がこのReadiness Checkの肝です。1件でも欠落があれば該当Phaseを再実行します。

`product_research`のチェック項目は、Phase 1.5として後から商品リサーチを追加したことに由来します。最初はKOLリサーチだけだったんですが、商品の差別化ポイントを知らないままKOLへの指示を作ると、どのKOLにも「おすすめです」としか書けない指示書が出来上がりました。商品を知らないとキャプションの具体性が出ないんです。

ここまでの問題を振り返ると、Gateが見ているものの「深さ」がそれぞれ違います。Phase 4分割前はGateすらなく、品質劣化が素通りしていました。run_id contractは「ファイルの新鮮さ」を見るようになりました。Readiness Checkは「ファイルの完全性」まで見るようになりました。

:::details Phase 5-7のAgentTeams Fix Loop

Build → Visualize → ReviewはAgentTeamsで実行しています。ReviewerがREJECTを返した場合、`target: data`ならbuilderから、`target: pptx`ならvisualizerから再spawnします。最大10回。

初期の実装でFix Loopが収束しなかった原因はReviewerの`target`判定精度でした。Reviewerが「スライドの数値が間違っている（→ data）」と「テキストの配置がずれている（→ pptx）」を正確に区別できないと、builderを再実行しても問題がvisualizerにあるという空振りが起きます。Reviewerのプロンプトに判断基準を詳細に書いて初めてループが収束しました。

Visualizerには「テキスト書き込み時は必ずフォント色`030303`を明示指定、テーマ継承色は使用禁止」というルールがあります。PPTXのテーマ継承色はビューワーによって解釈が変わるため、PowerPointでは正常に見えるのにKeynoteではテキストが白くなって消える問題がありました。このルールを入れてからREJECT率が大幅に下がりました。

builderのspawn時にはcaption-binding-rulesの全内容をプロンプトに含めます。市場によって開示トークンが異なり（JP: `#PR`、US: `#ad`、TH: `#โฆษณา`）、このルールなしだと全部`#ad`になります。fix loopで再spawnするときも同じルールを含めないと同じ問題を再現します。

:::

`execution_mode`のドリフト問題（`run_state.json`のmodeと`plan.json`のmodeが不一致になりうる）はまだ手動確認で補っています。各Phase遷移時のinvariantチェックを入れたいんですが、Pythonなら`@phase_entry`デコレータで済む横断的関心事を、自然言語のプロンプトでどう表現するかという問題が解けていません。コードには「フェーズ前処理」という抽象化がありますが、プロンプトにはまだそれがないんですよね。
