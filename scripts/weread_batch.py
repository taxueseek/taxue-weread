#!/usr/bin/env python3
"""
微信读书批量查询 — 一次进程调用，避免多次启动开销

用法:
  python3 weread_batch.py info <bookId1> <bookId2> ...
  python3 weread_batch.py search "关键词1" "关键词2" ...
  python3 weread_batch.py notes <bookId>
  python3 weread_batch.py chapters <bookId>
  python3 weread_batch.py bookmarks <bookId> [--count 20]

输出: JSON
"""
import sys, json, subprocess, os
from concurrent.futures import ThreadPoolExecutor, as_completed

WR = os.path.join(os.path.dirname(__file__), "weread.py")


def cmd(*args):
    """执行命令，返回 stdout"""
    r = subprocess.run([WR] + list(args), capture_output=True, text=True, timeout=15)
    return r.stdout.strip()


def parse_json(stdout):
    """
    解析 weread.py 的 JSON 输出。
    weread.py 的 mirror 等命令会输出进度信息（如 [1/2] 并发获取...），
    需要跳过这些非 JSON 行，找到第一个 { 开始的 JSON 对象。
    """
    if not stdout:
        return None
    json_start = stdout.find('{')
    if json_start == -1:
        return None
    return json.loads(stdout[json_start:])


def info_batch(book_ids):
    """批量获取书籍详情"""
    results = []
    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = {ex.submit(cmd, "book", str(bid)): bid for bid in book_ids}
        for f in as_completed(futs):
            stdout = f.result()
            if stdout:
                info = {"book_id": str(futs[f])}
                for line in stdout.split("\n"):
                    line = line.strip()
                    if line.startswith("《") and line.endswith("》"):
                        info["title"] = line.strip("《》")
                    elif line.startswith("作者:"):
                        info["author"] = line.split(":", 1)[1].strip()
                    elif line.startswith("评分:"):
                        info["rating"] = line.split(":", 1)[1].strip()
                    elif line.startswith("分类:"):
                        info["category"] = line.split(":", 1)[1].strip()
                    elif line.startswith("出版社:"):
                        info["publisher"] = line.split(":", 1)[1].strip()
                    elif line.startswith("简介:"):
                        info["intro"] = line.split(":", 1)[1].strip()[:200]
                results.append(info)
    return results


def search_batch(keywords):
    """批量搜索"""
    results = {}
    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = {ex.submit(cmd, "search", kw, "--json"): kw for kw in keywords}
        for f in as_completed(futs):
            stdout = f.result()
            if stdout:
                items = json.loads(stdout).get("items", [])
                for item in items[:5]:
                    bid = item["bookId"]
                    if bid not in results:
                        results[bid] = {
                            "title": item["title"],
                            "author": item.get("author", ""),
                            "rating": round(item.get("newRating", 0) / 10, 1),
                            "rating_count": item.get("newRatingCount", 0),
                            "category": item.get("category", ""),
                            "book_id": bid
                        }
    return list(results.values())


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    action = sys.argv[1]

    if action == "info":
        results = info_batch(sys.argv[2:])
        print(json.dumps(results, ensure_ascii=False, indent=2))

    elif action == "search":
        results = search_batch(sys.argv[2:])
        print(json.dumps(results, ensure_ascii=False, indent=2))

    elif action == "notes":
        stdout = cmd("notes", "--book", sys.argv[2], "--json")
        print(stdout if stdout else "[]")

    elif action == "chapters":
        stdout = cmd("book", sys.argv[2], "--chapters")
        if stdout:
            chapters = []
            in_toc = False
            for line in stdout.split("\n"):
                if "章节目录" in line:
                    in_toc = True
                    continue
                if in_toc:
                    line = line.strip()
                    if line and not line.startswith("──"):
                        chapters.append(line)
            print(json.dumps(chapters, ensure_ascii=False, indent=2))

    elif action == "bookmarks":
        book_id = sys.argv[2]
        count = 20
        if "--count" in sys.argv:
            idx = sys.argv.index("--count")
            if idx + 1 < len(sys.argv):
                count = int(sys.argv[idx + 1])
        stdout = cmd("bestbookmarks", book_id, "--json")
        if stdout:
            d = json.loads(stdout)
            items = d.get("items", [])[:count]
            print(json.dumps(items, ensure_ascii=False, indent=2))

    else:
        print(f"未知操作: {action}")
        sys.exit(1)


if __name__ == "__main__":
    main()
