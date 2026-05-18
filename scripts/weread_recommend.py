#!/usr/bin/env python3
"""
微信读书精细化推荐引擎 v3

用法:
  python3 weread_recommend.py books "投资 心理学" [--limit 10]
  python3 weread_recommend.py authors "投资 思维" [--limit 5]
  python3 weread_recommend.py chapters <book-id> "财富 幸福" [--limit 5]
  python3 weread_recommend.py versions "思考快与慢"
  python3 weread_recommend.py similar <book-id> [--limit 5]
  python3 weread_recommend.py profile --data /tmp/user_data.json
"""
import sys, json, subprocess, os, re
from concurrent.futures import ThreadPoolExecutor, as_completed

WR = os.path.join(os.path.dirname(__file__), "weread.py")


# ─── 底层搜索 ────────────────────────────────────────────────────────

def _search_single(keyword, count=10):
    """搜索单个关键词，返回原始 items"""
    r = subprocess.run([WR, "search", keyword, "--json"],
                      capture_output=True, text=True, timeout=15)
    if not r.stdout.strip():
        return []
    return json.loads(r.stdout).get("items", [])[:count]


def search(keyword, count=10):
    """
    搜索书籍，支持多关键词。
    - 单关键词：直接搜
    - 多关键词：并行搜 N 个，合并去重，按评分×评价人数排序
    """
    keywords = keyword.strip().split()
    if not keywords:
        return []

    all_raw = []
    seen = set()

    if len(keywords) == 1:
        raw_list = [_search_single(keywords[0], count * 2)]
    else:
        raw_list = []
        with ThreadPoolExecutor(max_workers=5) as ex:
            futs = {ex.submit(_search_single, kw, count * 2): kw for kw in keywords}
            for f in as_completed(futs):
                try:
                    raw_list.append(f.result())
                except:
                    pass

    for raw in raw_list:
        for b in raw:
            bid = b["bookId"]
            if bid not in seen:
                seen.add(bid)
                rating = b.get("newRating", 0)
                rc = b.get("newRatingCount", 0)
                all_raw.append({
                    "title": b["title"],
                    "author": b.get("author", ""),
                    "rating": round(rating / 10, 1),
                    "rating_count": rc,
                    "reading_count": b.get("readingCount", 0),
                    "category": b.get("category", ""),
                    "book_id": bid,
                    "_score": (rating / 10) * (1 + min(rc, 10000) / 1000)
                })

    all_raw.sort(key=lambda x: x["_score"], reverse=True)
    for b in all_raw:
        del b["_score"]
    return all_raw[:count]


def get_book_info(book_id):
    """获取书籍详情（文本解析）"""
    r = subprocess.run([WR, "book", str(book_id)],
                      capture_output=True, text=True, timeout=15)
    text = r.stdout
    info = {"book_id": str(book_id)}
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("《") and line.endswith("》"):
            info["title"] = line.strip("《》")
        elif line.startswith("作者:"):
            info["author"] = line.split(":", 1)[1].strip()
        elif line.startswith("评分:"):
            info["rating_str"] = line.split(":", 1)[1].strip()
        elif line.startswith("分类:"):
            info["category"] = line.split(":", 1)[1].strip()
        elif line.startswith("出版社:"):
            info["publisher"] = line.split(":", 1)[1].strip()
        elif line.startswith("简介:"):
            info["intro"] = line.split(":", 1)[1].strip()
    return info


# ─── 批量查询（一次进程调用）────────────────────────────────────────

def batch_query(book_ids):
    """
    批量查询多本书的信息，一次进程调用。
    避免多次启动 Python 进程的开销（每次 ~85ms）。
    """
    results = []
    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = {ex.submit(get_book_info, bid): bid for bid in book_ids}
        for f in as_completed(futs):
            try:
                results.append(f.result())
            except:
                pass
    return results


# ─── 推荐书 ──────────────────────────────────────────────────────────

def recommend_books(query, limit=10, prefer_categories=None, exclude_ids=None):
    """
    推荐书。
    - query: 空格分隔的关键词
    - prefer_categories: 优先分类
    - exclude_ids: 排除的 bookId 集合（用户已读过的）
    """
    books = search(query, limit * 3)
    exclude_ids = exclude_ids or set()

    # 过滤已读
    books = [b for b in books if b["book_id"] not in exclude_ids]

    if prefer_categories:
        preferred = [b for b in books if any(cat in b.get("category", "") for cat in prefer_categories)]
        others = [b for b in books if b not in preferred]
        books = preferred + others

    return books[:limit]


# ─── 推荐作者 ────────────────────────────────────────────────────────

def _get_author_books(author_name):
    """获取作者的所有书"""
    r = subprocess.run([WR, "author", author_name, "--json"],
                      capture_output=True, text=True, timeout=15)
    if not r.stdout.strip():
        return None
    d = json.loads(r.stdout)
    books = d.get("books", [])
    if not books:
        return None
    ratings = [b.get("rating", 0) for b in books if b.get("rating", 0) > 0]
    return {
        "author": author_name,
        "total_books": len(books),
        "top_books": [b["title"] for b in sorted(books, key=lambda x: x.get("rating", 0), reverse=True)[:3]],
        "avg_rating": round(sum(ratings) / len(ratings) / 10, 1) if ratings else 0,
        "best_book_id": books[0]["bookId"] if books else None
    }


def recommend_authors(query, limit=5, exclude=None):
    """推荐作者：搜索相关书 → 提取作者 → 获取作者作品 → 排序"""
    books = search(query, 30)
    exclude = exclude or set()
    authors = {}

    for b in books:
        author = b.get("author", "")
        if not author or author in exclude:
            continue
        # 去掉国籍标记、译者等
        author = re.sub(r'\[.*?\]', '', author).strip()
        author = re.sub(r'著|编|译$', '', author).strip()
        if not author or len(author) > 15:
            continue
        if author not in authors:
            authors[author] = b.get("rating", 0)

    sorted_authors = sorted(authors.keys(), key=lambda a: authors[a], reverse=True)

    results = []
    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = {ex.submit(_get_author_books, a): a for a in sorted_authors[:limit * 2]}
        for f in as_completed(futs):
            try:
                info = f.result()
                if info and info["total_books"] > 0:
                    results.append(info)
            except:
                pass

    results.sort(key=lambda x: x["avg_rating"] * min(x["total_books"], 5), reverse=True)
    return results[:limit]


# ─── 推荐章节 ────────────────────────────────────────────────────────

def _parse_chapters(book_id):
    """解析章节目录"""
    r = subprocess.run([WR, "book", str(book_id), "--chapters"],
                      capture_output=True, text=True, timeout=15)
    chapters = []
    in_toc = False
    for line in r.stdout.split("\n"):
        if "章节目录" in line:
            in_toc = True
            continue
        if not in_toc:
            continue
        line = line.strip()
        if not line or line.startswith("──"):
            continue
        # 判断层级
        if line.startswith("   ") or line.startswith("\t"):
            level = 2
        else:
            level = 1
        title = line.strip()
        if title:
            chapters.append({"idx": len(chapters), "title": title, "level": level})
    return chapters


def _get_bestbookmarks(book_id, count=50):
    """获取热门划线"""
    r = subprocess.run([WR, "bestbookmarks", str(book_id), "--json"],
                      capture_output=True, text=True, timeout=15)
    if not r.stdout.strip():
        return []
    d = json.loads(r.stdout)
    return d.get("items", []) or d.get("bookmarks", [])[:count]


def recommend_chapters(book_id, query, limit=5):
    """
    推荐章节。
    策略：
    1. 获取章节目录 + 热门划线
    2. 划线有 chapterUid，通过 bestbookmarks 返回的 chapterUid 映射到章节
    3. 按查询关键词匹配划线内容 → 找到相关章节
    4. 如果没匹配到，返回前 N 个一级章节
    """
    chapters = _parse_chapters(book_id)
    bookmarks = _get_bestbookmarks(book_id, 50)
    keywords = query.strip().split()

    if not chapters:
        return []

    # 建立 chapterUid → 章节索引 映射
    # chapterUid 是递增的，按顺序对应章节
    uid_map = {}
    for bm in bookmarks:
        uid = bm.get("chapterUid", 0)
        if uid and uid not in uid_map:
            # 找到最近的章节
            idx = min(uid - 1, len(chapters) - 1) if uid <= len(chapters) else min(uid % len(chapters), len(chapters) - 1)
            uid_map[uid] = idx

    # 按关键词匹配划线
    chapter_scores = {}
    for bm in bookmarks:
        text = bm.get("markText", "") or bm.get("mark", "")
        matched_kws = [kw for kw in keywords if kw in text]
        if matched_kws:
            uid = bm.get("chapterUid", 0)
            idx = uid_map.get(uid, 0)
            if idx not in chapter_scores:
                chapter_scores[idx] = {"score": 0, "highlights": [], "matched_keywords": set()}
            chapter_scores[idx]["score"] += len(matched_kws)
            chapter_scores[idx]["highlights"].append(text[:120])
            chapter_scores[idx]["matched_keywords"].update(matched_kws)

    if chapter_scores:
        sorted_chapters = sorted(chapter_scores.items(), key=lambda x: x[1]["score"], reverse=True)
        return [{
            "chapter": chapters[idx]["title"],
            "level": chapters[idx]["level"],
            "relevance_score": data["score"],
            "matched_keywords": list(data["matched_keywords"]),
            "sample_highlights": data["highlights"][:3]
        } for idx, data in sorted_chapters[:limit]]
    else:
        # 没有匹配到，返回前 N 个一级章节
        top_chapters = [ch for ch in chapters if ch["level"] == 1][:limit]
        return [{
            "chapter": ch["title"],
            "level": ch["level"],
            "relevance_score": 0,
            "matched_keywords": [],
            "sample_highlights": [],
            "note": "未匹配到相关关键词，返回目录前几章"
        } for ch in top_chapters]


# ─── 版本对比 ────────────────────────────────────────────────────────

def recommend_versions(query):
    """
    版本对比：搜索同一本书的所有版本，推荐最优版本。
    修复：正则 split 改为更稳健的分组策略。
    """
    results = _search_single(query, 20)
    if not results:
        return []

    # 按基础书名分组：取前2-4个字作为分组 key
    groups = {}
    for b in results:
        title = b["title"]
        # 取前 min(4, len(title)//2) 个字符作为分组 key
        key_len = max(2, min(4, len(title) // 2))
        base = title[:key_len]
        if base not in groups:
            groups[base] = []
        groups[base].append(b)

    output = []
    for base_key, versions in groups.items():
        if len(versions) < 2:
            continue

        # 找到最完整的书名（包含版本信息）
        base_name = max(versions, key=lambda b: len(b["title"]))["title"].split("（")[0].split("(")[0].strip()

        versions.sort(key=lambda b: (
            b.get("newRating", 0),
            b.get("newRatingCount", 0),
            -len(b["title"])
        ), reverse=True)

        best = versions[0]
        output.append({
            "base_title": base_name or base_key,
            "versions": [{
                "title": b["title"],
                "author": b.get("author", ""),
                "rating": round(b.get("newRating", 0) / 10, 1),
                "rating_count": b.get("newRatingCount", 0),
                "book_id": b["bookId"],
                "is_recommended": b == best
            } for b in versions],
            "recommended": {
                "title": best["title"],
                "author": best.get("author", ""),
                "rating": round(best.get("newRating", 0) / 10, 1),
                "book_id": best["bookId"],
                "reason": f"评分最高（{round(best.get('newRating',0)/10,1)}%），评价人数{best.get('newRatingCount',0)}人"
            },
            "version_count": len(versions)
        })

    return output


# ─── 相似书 ──────────────────────────────────────────────────────────

def recommend_similar(book_id, limit=5):
    """
    相似书推荐。
    策略：discover → 二次搜索验证评分 → 过滤低质量
    """
    r = subprocess.run([WR, "discover", "--book", str(book_id), "--json"],
                      capture_output=True, text=True, timeout=15)
    if not r.stdout.strip():
        return []
    d = json.loads(r.stdout)
    raw = d.get("books", []) or d.get("items", []) or []

    results = []
    seen_ids = set()

    for b in raw:
        title = b.get("title", "")
        author = b.get("author", "")
        bid = str(b.get("bookId", ""))
        if not title or bid in seen_ids:
            continue
        seen_ids.add(bid)

        # 二次搜索获取准确评分
        verified = _search_single(title, 3)
        if verified:
            v = verified[0]
            results.append({
                "title": v["title"],
                "author": v.get("author", author),
                "rating": round(v.get("newRating", 0) / 10, 1),
                "rating_count": v.get("newRatingCount", 0),
                "category": v.get("category", ""),
                "book_id": v["bookId"]
            })
        else:
            results.append({
                "title": title,
                "author": author,
                "rating": round(b.get("newRating", 0) / 10, 1),
                "rating_count": b.get("newRatingCount", 0),
                "category": b.get("category", ""),
                "book_id": bid
            })

    # 过滤低质量
    results = [r for r in results if (r["rating"] or 0) > 70 and (r["rating_count"] or 0) > 10]
    return results[:limit]


# ─── 综合画像推荐 ────────────────────────────────────────────────────

def recommend_profile(user_data, limit_per_category=5):
    """基于用户画像综合推荐"""
    results = {}
    exclude_ids = set(user_data.get("read_book_ids", []))

    if user_data.get("top_categories"):
        cat_query = " ".join([c.split("-")[-1] for c in user_data["top_categories"]])
        results["based_on_interest"] = recommend_books(cat_query, limit_per_category, exclude_ids=exclude_ids)

    if user_data.get("preferred_authors"):
        author_query = " ".join(user_data["preferred_authors"][:3])
        results["similar_authors"] = recommend_authors(author_query, 3, exclude=set(user_data["preferred_authors"]))

    if user_data.get("blind_spots"):
        blind_query = " ".join(user_data["blind_spots"])
        results["blind_spot_fill"] = recommend_books(blind_query, limit_per_category, exclude_ids=exclude_ids)

    return results


# ─── CLI ──────────────────────────────────────────────────────────────

USAGE = """\
微信读书精细化推荐引擎 v3

用法:
  python3 weread_recommend.py books "投资 心理学" [--limit 10]
  python3 weread_recommend.py authors "投资 思维" [--limit 5]
  python3 weread_recommend.py chapters <book-id> "财富 幸福" [--limit 5]
  python3 weread_recommend.py versions "思考快与慢"
  python3 weread_recommend.py similar <book-id> [--limit 5]
  python3 weread_recommend.py batch <bookId1> <bookId2> ...
  python3 weread_recommend.py profile --data /tmp/user_data.json
"""


def main():
    if len(sys.argv) < 2:
        print(USAGE)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "books":
        query = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "投资 理财"
        results = recommend_books(query, 10)
        print(json.dumps(results, ensure_ascii=False, indent=2))

    elif cmd == "authors":
        query = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "投资"
        results = recommend_authors(query, 5)
        print(json.dumps(results, ensure_ascii=False, indent=2))

    elif cmd == "chapters":
        if len(sys.argv) < 4:
            print("用法: chapters <book-id> <query>")
            sys.exit(1)
        book_id = sys.argv[2]
        query = " ".join(sys.argv[3:])
        results = recommend_chapters(book_id, query, 5)
        print(json.dumps(results, ensure_ascii=False, indent=2))

    elif cmd == "versions":
        query = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""
        if not query:
            print("用法: versions <书名>")
            sys.exit(1)
        results = recommend_versions(query)
        print(json.dumps(results, ensure_ascii=False, indent=2))

    elif cmd == "similar":
        if len(sys.argv) < 3:
            print("用法: similar <book-id>")
            sys.exit(1)
        book_id = sys.argv[2]
        results = recommend_similar(book_id, 5)
        print(json.dumps(results, ensure_ascii=False, indent=2))

    elif cmd == "batch":
        if len(sys.argv) < 3:
            print("用法: batch <bookId1> <bookId2> ...")
            sys.exit(1)
        book_ids = sys.argv[2:]
        results = batch_query(book_ids)
        print(json.dumps(results, ensure_ascii=False, indent=2))

    elif cmd == "profile":
        user_data = {}
        if len(sys.argv) > 2 and os.path.exists(sys.argv[2]):
            with open(sys.argv[2]) as f:
                user_data = json.load(f)
        results = recommend_profile(user_data)
        print(json.dumps(results, ensure_ascii=False, indent=2))

    else:
        print(f"未知命令: {cmd}")
        print(USAGE)
        sys.exit(1)


if __name__ == "__main__":
    main()
