#!/usr/bin/env python3
"""
微信读书批量并行搜索 — 高效推荐引擎工具

用法:
  python3 weread_search.py "书名1" "书名2" ... "书名N"
  python3 weread_search.py --file books.txt   # 每行一本书名

输出: JSON 数组，包含每本书的搜索结果
"""
import sys, json, subprocess, os
from concurrent.futures import ThreadPoolExecutor, as_completed

WR = os.path.join(os.path.dirname(__file__), "weread.py")

def search_one(keyword):
    try:
        r = subprocess.run([WR, "search", keyword, "--json"],
                          capture_output=True, text=True, timeout=15)
        d = json.loads(r.stdout)
        items = d.get("items", [])
        if items:
            b = items[0]
            rating = b.get("newRating", 0)
            return {
                "query": keyword,
                "title": b["title"],
                "author": b.get("author", ""),
                "rating": round(rating / 10, 1) if rating else None,
                "rating_count": b.get("newRatingCount", 0),
                "category": b.get("category", ""),
                "bookId": b["bookId"],
                "readingCount": b.get("readingCount", 0)
            }
        return {"query": keyword, "error": "no results"}
    except Exception as e:
        return {"query": keyword, "error": str(e)}

def main():
    if len(sys.argv) < 2:
        print("用法: weread_search.py 书名1 书名2 ...")
        sys.exit(1)

    if sys.argv[1] == "--file":
        with open(sys.argv[2]) as f:
            books = [line.strip() for line in f if line.strip()]
    else:
        books = sys.argv[1:]

    results = []
    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = {ex.submit(search_one, b): b for b in books}
        for future in as_completed(futures):
            results.append(future.result())

    # 保持原始顺序
    order = {b: i for i, b in enumerate(books)}
    results.sort(key=lambda x: order.get(x.get("query", ""), 999))

    print(json.dumps(results, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
