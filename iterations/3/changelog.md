# Style Guide Changelog — Iteration 3

**Date:** 2026-04-09
**Version:** 3.0 (post-consolidation update)
**Score:** 8/10 (up from 7/10 in Iteration 2)
**Review source:** `iterations/3/review.md`

---

## Note: Consolidationが先行

Iteration 3のこのchangelogは、Consolidation（v2.3→v3.0、295行→200行）の後に実施するStyle Guide Updaterの記録です。新規ルール追加より既存ルールの精緻化を優先します。

---

## Changes Made

### 1. Rule 11（ボールド予算）の精緻化: テーゼ文ボールド禁止を明文化

**Why:** Iteration 3記事で「**thin_largeの本質は、Leadが何を「知らないか」を設計すること**」のようなテーゼ文のボールドが2〜3箇所あった。これは教科書的な「重要箇所」マーカーとして機能し、読者に「ここを読め」と押しつけるスタイルになる。ベンチマーク記事はボールドを文中の特定語句に限定し、文全体をボールドにしない。

**変更内容（Consolidation済みv3.0に統合済み）:**
- 「テーゼ文をボールドにしない（テーゼは文脈で伝える）」を Rule 11 に追記
- ANTI-PATTERNSテーブルに「テーゼ文のボールド強調」を追加

---

### 2. Rule 5（概念スレッド）の精緻化: 概念軸の「前出し」強化

**Why:** Iteration 3記事の「境界のないところに境界を引く」という最も重要な洞察が記事の2/3以降で出てきた。この洞察が冒頭にあれば全セクションがその軸の異なる側面として読めるようになる。ベンチマーク記事（`react-server-components-multi-stage.md` の「RSC=多段階計算」）は冒頭で軸を提示し、以後の全セクションがその軸を肉付けする。

**現状のRule 5（v3.0）はすでにこの要件を含んでいる。** 変更不要。

---

### 3. anti_patterns.md に Iteration 3 のパターンを追記

- AP-7: テーゼ文のボールド強調（mid-paragraph callout）
- AP-8: 概念軸の後出し（late-arriving thesis）
- AP-9: 記事ナラティブアークを断ち切る横断的セクションの挿入

---

## 変更しなかったもの

- CRITICAL要件（Rule 1-9）: Iteration 3でも全て達成。変更不要
- Rule 10/10a: 知的連鎖と失敗の誠実な再現 — Iteration 3記事で概ね実装されていた
- Consolidationで削除したANTI-PATTERNSの復元: 不要（主要パターンはanti_patterns.mdで追跡）

---

## スコア推移

| Iteration | Overall | Writing Style | Structure | Authenticity | Technical |
|-----------|---------|---------------|-----------|--------------|-----------|
| 1         | 6/10    | 5/10          | 6/10      | 5/10         | 8/10      |
| 2         | 7/10    | 7/10          | 7/10      | 7/10         | 8/10      |
| 3         | 8/10    | 7/10          | 7/10      | 9/10         | 9/10      |

---

**Targeted improvement for Iteration 4:** Writing Style (7→8+)、Structure (7→8+) by applying AP-7/AP-8/AP-9
