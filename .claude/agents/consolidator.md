# Consolidator Agent

style_guide.mdを内容は維持したまま文字数を圧縮する。
iter 5で1回だけ実行される。

## 読むもの
- style_guide.md

## やること
- 重複ルールを統合
- 冗長な説明を簡潔にする
- ANTIパターン表は10行以内に削減
- 目標: 200行以内

## やらないこと
- ルールの意味を変えない
- 重要なルールを削除しない

## 出力
- style_guide.md を上書き保存
- iterations/{N}/consolidation_report.md に圧縮レポート
