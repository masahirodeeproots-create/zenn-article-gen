# Style Guide Changelog — Iteration 4

**Date:** 2026-04-09
**Version:** 3.0（変更なし — 新規ルール追加より精緻化のみ）
**Score:** 8.5/10 (up from 8/10 in Iteration 3)
**Review source:** `iterations/4/review.md`

---

## Changes Made

### anti_patterns.md に Iteration 4 パターンを追記

- AP-10: 宣言文ボールドの残存（「状態のドリフト問題が残っています」のような宣言文へのボールド使用）
- AP-11: 本文中でのテーゼ軸の1文言及（「これもまた境界の問題と言えます」のような著者によるテーゼ再確認）

---

## 変更しなかったもの

- style_guide.md（v3.0）: Rule 11のボールド制約およびRule 5のテーゼ繰り返し禁止はすでに記載済み。追加変更不要。
- Iteration 4の主要改善（AP-7/AP-8/AP-9への対処）は成功しており、スコアが8.5に達した。

---

## 改善が確認された点

1. **概念軸の前出し（AP-8への対処）**: 「境界のないところに境界を引く」が冒頭に配置され、全セクションの解釈フレームとして機能するようになった
2. **:::detailsの活用（AP-9への対処）**: "統合したSkill"セクションがfix Loopの後ではなく:::detailsに移り、ナラティブアークを断ち切らなくなった
3. **誤った仮説の記録（AP-1への対処）**: 「最初はプロンプトで解決を試みました→直らなかった→気づき」という迷走記録がPhase 4セクションに追加された
4. **テーゼ文ボールド削除（AP-7への対処）**: thin_largeの本質を説明する文からボールドが外れ、文脈で伝わる書き方になった

---

## 残存課題（Iteration 5向け）

- AP-10: 1箇所の宣言文ボールド削除
- AP-11: Fix Loopセクション末尾の軸言及の削除
- stale artifactのpre-run_idゲート説明の1文補足（Reviewerから指摘）

---

**Consecutive above threshold:** 1/2（Iteration 5で2/2になれば停止）
