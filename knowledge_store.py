"""knowledge_store.py — 知識DBデータアクセス層

全ての知識DB操作をこのモジュールに集約する。
今はファイルI/O。関数シグネチャを変えずにBigQueryに差し替え可能。
"""

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path("/tmp/zenn-article-gen")
KNOWLEDGE_DIR = BASE_DIR / "knowledge"
CACHE_DIR = KNOWLEDGE_DIR / "search_cache"


def init_knowledge_dir():
    """知識DBディレクトリを初期化（冪等）"""
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    for fname in ["trends.md", "reader_pains.md"]:
        path = KNOWLEDGE_DIR / fname
        if not path.exists():
            path.write_text(f"# {fname.replace('.md', '').replace('_', ' ').title()}\n\n")


def save_trend(keyword: str, source: str, content: str, date: str):
    """トレンド情報を追記保存

    Args:
        keyword: 検索キーワード
        source: 情報源（"zenn" / "qiita" / "hn" / "anthropic_blog" / "openai_blog"）
        content: トレンド内容
        date: 取得日（ISO 8601: "2026-04-13"）
    """
    path = KNOWLEDGE_DIR / "trends.md"
    entry = f"\n## [{date}] {keyword} ({source})\n\n{content}\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(entry)


def save_pain(keyword: str, source: str, content: str, date: str):
    """読者の痛み情報を追記保存。シグネチャはsave_trendと同一。"""
    path = KNOWLEDGE_DIR / "reader_pains.md"
    entry = f"\n## [{date}] {keyword} ({source})\n\n{content}\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(entry)


def search_trends(query: str, limit: int = 10) -> list:
    """トレンドをキーワード検索。セクション単位でマッチ。"""
    return _search_file("trends.md", query, limit)


def search_pains(query: str, limit: int = 10) -> list:
    """読者の痛みをキーワード検索。"""
    return _search_file("reader_pains.md", query, limit)


def _search_file(filename: str, query: str, limit: int) -> list:
    """知識ファイルをセクション単位で検索（内部関数）"""
    path = KNOWLEDGE_DIR / filename
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    sections = text.split("\n## ")
    results = []
    q = query.lower()
    for section in sections[1:]:
        if q in section.lower():
            header = section.split("\n")[0]
            body = "\n".join(section.split("\n")[1:]).strip()
            results.append({"header": header, "content": body})
            if len(results) >= limit:
                break
    return results


def query_hash(query: str) -> str:
    """クエリからハッシュを生成（英数字12文字）。

    呼び出し元がこれを使ってからcache関数に渡す。
    """
    return hashlib.md5(query.encode()).hexdigest()[:12]


def is_cache_fresh(qhash: str, max_age_days: int = 7) -> bool:
    """キャッシュが有効期限内か判定。

    ファイル名: {query_hash}_{YYYY-MM-DD}.json
    ハッシュは英数字12文字でアンダースコアを含まないため
    split("_", 1) で安全に分離できる。
    """
    cutoff = datetime.now() - timedelta(days=max_age_days)
    for f in CACHE_DIR.glob(f"{qhash}_*.json"):
        date_str = f.stem.split("_", 1)[1]
        try:
            if datetime.strptime(date_str, "%Y-%m-%d") >= cutoff:
                return True
        except ValueError:
            continue
    return False


def save_cache(qhash: str, data: dict):
    """検索結果をキャッシュに保存。"""
    date_str = datetime.now().strftime("%Y-%m-%d")
    path = CACHE_DIR / f"{qhash}_{date_str}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_cache(qhash: str) -> dict | None:
    """最新のキャッシュを読み込み。なければNone。"""
    files = sorted(CACHE_DIR.glob(f"{qhash}_*.json"), reverse=True)
    if not files:
        return None
    with open(files[0], encoding="utf-8") as f:
        return json.load(f)
