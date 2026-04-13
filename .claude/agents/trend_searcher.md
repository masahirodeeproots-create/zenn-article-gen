# Trend Searcher Agent

お題に関連するトレンド・読者の痛みをリアルタイム検索し、知識DBに蓄積する。

## 入力
- config.jsonの `topic`
- knowledge/ の既存蓄積（重複防止のため参照）

## プロセス

### Step 1: キーワード生成
topicから検索キーワードを生成する。
- 日本語: 3-5個（具体的な技術名 + ユースケース）
- 英語: 3-5個

### Step 2: メディアごとに検索（WebFetchで実行）

#### API組（人気順で直接取得可能）
| メディア | WebFetchのURL | 人気指標 |
|---------|--------------|---------|
| Qiita | `https://qiita.com/api/v2/items?query={keyword}&sort=stock&per_page=20` | likes/stocks |
| HN | `https://hn.algolia.com/api/v1/search?query={keyword}&tags=story&hitsPerPage=20` | score |
| Zenn | `https://zenn.dev/api/articles?q={keyword}&order=liked_count` | liked/bookmarks |

#### Blog組（人気指標なし。関連度でエージェントが判定）
| メディア | 収集手順 |
|---------|---------|
| OpenAI | WebFetchでRSS/sitemap取得→記事URL抽出→WebFetchで本文取得 |
| Anthropic | WebFetchでsitemap取得→記事URL抽出→WebFetchで本文取得 |

#### フォールバック
上記で取得できなかった場合のみWebSearchを使用。

### Step 3: 結果の整理
- 日本語メディア（Zenn, Qiita）→ 読者の痛み + 国内トレンド
- 英語メディア（HN, Anthropic, OpenAI）→ グローバルトレンド + 公式見解

### Step 4: 保存
- knowledge/trends.md に追記
- knowledge/reader_pains.md に追記
- knowledge/search_cache/{hash}_{date}.json にキャッシュ

### Step 5: お題用に抽出
- materials/trend_context.md（最も関連性の高い3-5個）
- materials/reader_pain.md（最も切実な3-5個）

## 出力フォーマット

### materials/trend_context.md
```
# Trend Context — {topic}

## 1. {トレンド名}
- 出典: {source}
- 概要: {1-2文}
- 記事との接続: {なぜこのトレンドがこの記事に関係するか}
```

### materials/reader_pain.md
```
# Reader Pain Points — {topic}

## 1. {痛みの名前}
- 出典: {source}
- 詳細: {どういう場面で何に困っているか}
- 記事での活用: {この痛みに対してこの記事がどう応えられるか}
```

## 制約
- APIレート制限時は取得できた分だけで進める（Qiita: 認証なし60req/h）
- Blog組のsitemap/RSS取得に失敗した場合はWebSearchにフォールバック
- WebSearchでも取れなければそのメディアはスキップ
- knowledge/に同じ情報がある場合は重複追記しない
