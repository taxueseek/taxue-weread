#!/usr/bin/env python3
"""微信读书 CLI — 统一命令行接口。

用法:
  weread.py search <keyword> [--scope 10] [--page 1] [--per-page 10] [--json]
  weread.py shelf [--page 1] [--per-page 10] [--json]
  weread.py book <bookId> [--chapters] [--progress]
  weread.py notes [--book <bookId>] [--page 1] [--per-page 10] [--json]
  weread.py bestbookmarks <bookId> [--chapter <uid>] [--json]
  weread.py underlines <bookId> --chapter <uid> [--json]
  weread.py readreviews <bookId> --chapter <uid> --range "393-401" [--json]
  weread.py readdata [--mode monthly] [--time 0] [--json]
  weread.py review <bookId> [--type 0] [--page 1] [--per-page 10] [--json]
  weread.py discover [--book <bookId>] [--page 1] [--per-page 10] [--json]
  weread.py report
  weread.py export <bookId> [--output 路径]
  weread.py author <作者名> [--json]
  weread.py shelf-stats
  weread.py list-apis

多数命令支持 --json 输出原始 API 响应，方便程序化处理。
"""

import json
import os
import random
import sys
import time
import urllib.request
import urllib.error
from typing import Union

API_URL = "https://i.weread.qq.com/api/agent/gateway"
SKILL_VERSION = "1.6.0"

# ─── cache ────────────────────────────────────────────────────────────

CACHE_DIR = "/tmp/weread_cache"
DEFAULT_TTL = 300  # 5 minutes

def _cache_key(api_name, params):
    """生成缓存 key。"""
    raw = api_name + json.dumps(params, sort_keys=True, ensure_ascii=False)
    import hashlib
    return hashlib.md5(raw.encode()).hexdigest()

def _cache_get(key, ttl=DEFAULT_TTL):
    """读取缓存。返回 None 表示未命中或过期。"""
    path = os.path.join(CACHE_DIR, key + ".json")
    if not os.path.exists(path):
        return None
    if time.time() - os.path.getmtime(path) > ttl:
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

def _cache_set(key, data):
    """写入缓存。"""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, key + ".json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except OSError:
        pass

class WereadError(Exception):
    """API 业务错误（errcode != 0），可安全捕获。"""
    pass

# ─── utilities ───────────────────────────────────────────────────────

def ts_to_date(ts: Union[int, float]) -> str:
    """Unix timestamp → YYYY-MM-DD"""
    return time.strftime("%Y-%m-%d", time.localtime(ts))

def secs_to_hms(secs: int) -> str:
    """秒 → X小时Y分钟"""
    h, m = divmod(secs, 3600)
    m = m // 60
    if h > 0:
        return f"{h}小时{m}分钟"
    return f"{m}分钟"

def star_to_str(score: int) -> str:
    """评分整数 → 星级。100=⭐⭐⭐⭐⭐, 80=⭐⭐⭐⭐, ..."""
    if score is None or score <= 0:
        return "无评分"
    stars = int(score) // 20
    return "⭐" * stars if stars else "无评分"

def rating_to_str(r: Union[int, None]) -> str:
    """评分 (0-1000) → 文字。"""
    if r is None or r == 0:
        return "暂无"
    score = r / 10  # 转为百分制
    if score >= 90:
        return f"神作 {score:.0f}%"
    if score >= 80:
        return f"力荐 {score:.0f}%"
    if score >= 70:
        return f"好评 {score:.0f}%"
    return f"{score:.1f}分"

def make_deep_link(book_id: str, chapter_uid: str = "", range_start: str = "",
                   range_end: str = "", user_vid: str = "") -> str:
    """构造微信读书深度链接。"""
    if chapter_uid and range_start and range_end:
        link = f"weread://bestbookmark?bookId={book_id}&chapterUid={chapter_uid}&rangeStart={range_start}&rangeEnd={range_end}"
        if user_vid:
            link += f"&userVid={user_vid}"
        return link
    if chapter_uid:
        return f"weread://reading?bId={book_id}&chapterUid={chapter_uid}"
    return f"weread://reading?bId={book_id}"

def paginate(items: list, page: int, per_page: int) -> tuple[list, int]:
    """Slice items for pagination. Returns (page_items, total_pages)."""
    total = len(items)
    total_pages = max(1, (total + per_page - 1) // per_page)
    start = (page - 1) * per_page
    end = start + per_page
    return items[start:end], total_pages

def paginate_mark(items: list, page: int, per_page: int) -> tuple[list, int, bool, bool]:
    """Slice items with page boundary info."""
    total = len(items)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    end = start + per_page
    return items[start:end], total_pages, page > 1, page < total_pages

def truncate(text: str, max_len: int = 200) -> str:
    """截断长文本。"""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "…"


# ─── shared helpers ───────────────────────────────────────────────────

def _fetch_all_notebooks(api, max_pages=5, count=50):
    """获取笔记本概览列表。返回 (books, pages_fetched)。
    books: [{bookId, title, author, category, total, reviewCount, noteCount, bookmarkCount, readingProgress, markedStatus, sort}, ...]
    """
    all_books = []
    last_sort = 0
    pages = 0
    while pages < max_pages:
        params = {"count": count}
        if last_sort > 0:
            params["lastSort"] = last_sort
        try:
            result = api.call("/user/notebooks", **params)
        except WereadError:
            break
        for b in result.get("books", []):
            bk = b.get("book", {})
            all_books.append({
                "bookId": b.get("bookId", ""),
                "title": bk.get("title", ""),
                "author": bk.get("author", ""),
                "category": bk.get("category", ""),
                "reviewCount": b.get("reviewCount", 0),
                "noteCount": b.get("noteCount", 0),
                "bookmarkCount": b.get("bookmarkCount", 0),
                "total": b.get("reviewCount", 0) + b.get("noteCount", 0) + b.get("bookmarkCount", 0),
                "readingProgress": b.get("readingProgress", 0),
                "markedStatus": b.get("markedStatus", 0),
                "sort": b.get("sort", 0),
            })
        pages += 1
        if result.get("hasMore") != 1:
            break
        if all_books:
            last_sort = all_books[-1]["sort"]
    return all_books, pages


def print_pagination(page, total_pages, has_prev, has_next):
    """打印分页导航。"""
    if total_pages <= 1:
        return
    nav = []
    if has_prev:
        nav.append(f"--page {page-1} 上一页")
    if has_next:
        nav.append(f"--page {page+1} 下一页")
    print("  ".join(nav))


def add_common_args(p, json_default=True, page_default=True):
    """给 argparse 子命令添加通用参数。"""
    if page_default:
        p.add_argument("--page", type=int, default=1)
        p.add_argument("--per-page", type=int, default=10)
    if json_default:
        p.add_argument("--json", action="store_true")


# ─── API client ───────────────────────────────────────────────────────

class WereadAPI:
    def __init__(self):
        self.key = os.environ.get("WEREAD_API_KEY", "")
        if not self.key:
            print("错误: WEREAD_API_KEY 未设置，请 export WEREAD_API_KEY=***", file=sys.stderr)
            sys.exit(1)

    def call(self, api_name: str, **params) -> dict:
        """调用 API，内置缓存、重试（指数退避+抖动），自动处理 errcode 和 upgrade_info。"""
        # 缓存仅对只读接口启用（不缓存写操作）
        cache_key = _cache_key(api_name, params)
        skip_cache = params.pop("_no_cache", False)
        if not skip_cache:
            cached = _cache_get(cache_key)
            if cached is not None:
                return cached

        body = {"api_name": api_name, "skill_version": SKILL_VERSION, **params}
        data = json.dumps(body).encode("utf-8")

        last_error = None
        for attempt in range(3):
            try:
                req = urllib.request.Request(API_URL, data=data, headers={
                    "Authorization": f"Bearer {self.key}",
                    "Content-Type": "application/json",
                })
                resp = urllib.request.urlopen(req, timeout=30)
                result = json.loads(resp.read())

                if "upgrade_info" in result:
                    msg = result.get("upgrade_info", {}).get("message", "技能版本需升级")
                    print(f"⚠️  {msg}", file=sys.stderr)
                    print("请根据指引升级 weread skill 后重试。", file=sys.stderr)
                    raise SystemExit(2)

                errcode = result.get("errcode", 0)
                if errcode != 0:
                    errmsg = result.get("errmsg", "未知错误")
                    raise WereadError(f"API 错误 (errcode={errcode}): {errmsg}")

                _cache_set(cache_key, result)
                return result

            except WereadError:
                raise  # 业务错误不重试

            except urllib.error.HTTPError as e:
                last_error = e
                if e.code and 500 <= e.code < 600 and attempt < 2:
                    wait = (2 ** attempt) + random.uniform(0, 1)
                    time.sleep(wait)
                    continue
                print(f"HTTP {e.code}: {e.reason}", file=sys.stderr)
                sys.exit(1)

            except (urllib.error.URLError, OSError, TimeoutError) as e:
                last_error = e
                if attempt < 2:
                    wait = (2 ** attempt) + random.uniform(0, 1)
                    time.sleep(wait)
                    continue
                print(f"网络错误: {e}", file=sys.stderr)
                sys.exit(1)

        print(f"重试耗尽: {last_error}", file=sys.stderr)
        sys.exit(1)


# ─── commands ─────────────────────────────────────────────────────────

def cmd_search(api: WereadAPI, args):
    """搜索书籍"""
    params = {"keyword": args.keyword}
    if getattr(args, "scope", None) is not None:
        params["scope"] = args.scope
    if getattr(args, "count", None):
        params["count"] = args.count

    result = api.call("/store/search", **params)

    if getattr(args, "json", False) is True:
        # 扁平化搜索结果
        items = []
        for group in result.get("results", []):
            for b in group.get("books", []):
                bi = b.get("bookInfo", {})
                if bi.get("bookId"):
                    items.append({
                        "bookId": bi.get("bookId", ""),
                        "title": bi.get("title", ""),
                        "author": bi.get("author", ""),
                        "newRating": bi.get("newRating"),
                        "newRatingCount": bi.get("newRatingCount", 0),
                        "category": bi.get("category", ""),
                        "readingCount": b.get("readingCount", 0),
                    })
        return {"keyword": args.keyword, "total": len(items), "items": items}

    results = result.get("results", [])
    if not results:
        print("未找到结果。")
        return

    page = getattr(args, "page", 1)
    per_page = getattr(args, "per_page", 10)

    # flatten books from all result groups
    all_books = []
    for group in results:
        group_title = group.get("title", "")
        group_scope = group.get("scope", 0)
        for b in group.get("books", []):
            bi = b.get("bookInfo", {})
            all_books.append({
                "bookId": bi.get("bookId", ""),
                "title": bi.get("title", ""),
                "author": bi.get("author", ""),
                "cover": bi.get("cover", ""),
                "intro": bi.get("intro", ""),
                "publisher": bi.get("publisher", ""),
                "category": bi.get("category", ""),
                "payType": bi.get("payType", 0),
                "price": bi.get("price", 0),
                "newRating": bi.get("newRating"),
                "newRatingCount": bi.get("newRatingCount", 0),
                "newRatingDetail": bi.get("newRatingDetail", {}).get("title", ""),
                "readingCount": b.get("readingCount", 0),
                "soldout": bi.get("soldout", 0),
                "group_title": group_title,
                "group_scope": group_scope,
            })

    page_items, total_pages, has_prev, has_next = paginate_mark(all_books, page, per_page)

    print(f"搜索: {args.keyword}  共 {len(all_books)} 条结果")
    if total_pages > 1:
        print(f"(第 {page}/{total_pages} 页，每页 {per_page} 条)")
    print()

    for i, b in enumerate(page_items, (page - 1) * per_page + 1):
        rating = rating_to_str(b["newRating"])
        status = " [已下架]" if b["soldout"] else ""
        group = f" [{b['group_title']}]" if b.get("group_title") else ""
        print(f"{i}. {b['title']}{status}{group}")
        print(f"   作者: {b['author']}  |  {rating}  |  {b['readingCount']}人在读")
        if b["price"] > 0:
            print(f"   价格: ¥{b['price']/100:.2f}  |  分类: {b['category']}")
        else:
            print(f"   分类: {b['category']}")
        if b["intro"]:
            print(f"   简介: {truncate(b['intro'], 100)}")
        print(f"   [打开]({make_deep_link(b['bookId'])})")
        print()

    print_pagination(page, total_pages, has_prev, has_next)


# ─── compact field definitions ──────────────────────────────────────
# 每个命令的 --compact 模式输出字段白名单。None 表示输出全部。
# 每个命令的 --compact 输出字段定义。
# 格式：{"顶层字段": ["子字段", ...], ...}。None 表示保留全部子字段。
_COMPACT_FIELDS = {
    "search":       {"items": ["bookId", "title", "author", "newRating", "readingCount"]},
    "shelf":        {"books": ["bookId", "title", "author", "category", "finishReading", "readUpdateTime"]},
    "book":         {"*": ["title", "author", "translator", "newRating", "category", "wordCount"]},
    "readdata":     {"*": ["readDays", "totalReadTime", "dayAverageReadTime", "compare", "preferTimeWord", "readRate"]},
    "review":       {"reviews": ["author", "star", "content"]},
    "discover":     {"items": ["bookId", "title", "author", "newRating", "reason"]},
    "bestbookmarks":{"items": ["markText", "totalCount"]},
    "underlines":   {"underlines": ["range", "count"]},
    "readreviews":  {"reviews": ["totalCount", "author", "content"]},
    "resolve":      {"candidates": ["bookId", "title", "author", "matchScore"]},
    "inspect":      {"*": ["bookId", "title", "author", "rating"], "highlights": ["chapter", "text"], "thoughts": ["chapter", "content"]},
    "mirror":       {"profile": None, "annotations": ["title", "author", "noteDensity", "totalNotes", "highlights", "thoughts"]},
    "organize":     {"books": ["title", "author", "highlights", "thoughts"], "summary": None},
    "export":       {"*": ["title"], "highlights": ["chapter", "text"], "thoughts": ["chapter", "content"]},
    "author":       {"books": ["title", "rating", "readingCount"]},
}


def _filter_fields(item, fields):
    """按字段白名单过滤 dict。fields=None 返回全部。"""
    if fields is None:
        return item
    return {k: v for k, v in item.items() if k in fields}


def _compact_json(data, fields):
    """递归压缩 JSON 输出。
    fields 格式：{"key": ["子字段", ...], "*": ["所有key的子字段"], None表示保留全部}
    """
    if isinstance(data, dict):
        result = {}
        for k, v in data.items():
            if k not in fields:
                continue
            sub_fields = fields[k]
            if sub_fields is None:
                # 保留全部
                result[k] = v
            elif isinstance(sub_fields, list) and isinstance(v, list):
                # 列表字段：压缩每个元素
                result[k] = [_compact_json(item, {s: [] for s in sub_fields}) if isinstance(item, dict) else item for item in v]
            elif isinstance(sub_fields, list) and isinstance(v, dict):
                # 单个对象字段
                result[k] = _compact_json(v, {s: [] for s in sub_fields})
            else:
                result[k] = v
        return result
    return data


def _output(result, args):
    """统一输出处理：支持 --compact 压缩。"""
    if result is None:
        return
    if not isinstance(result, dict):
        return
    compact_fields = _COMPACT_FIELDS.get(args.command)
    if getattr(args, "compact", False) and compact_fields:
        result = _compact_json(result, compact_fields)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _compact_output(data, command, args):
    """快捷函数：在命令内部调用，自动处理 compact 输出。"""
    if not isinstance(data, dict):
        return data
    compact_fields = _COMPACT_FIELDS.get(command)
    if getattr(args, "compact", False) and compact_fields:
        return _compact_json(data, compact_fields)
    return data


def cmd_resolve(api: WereadAPI, args):
    """模糊书名 → 精确 bookId。搜索后按匹配度排序，输出候选列表供选择。"""
    search_result = api.call("/store/search", keyword=args.keyword, scope=args.scope or 0, count=args.count or 10)
    results = search_result.get("results", [])

    # 扁平化所有候选书
    candidates = []
    for group in results:
        for b in group.get("books", []):
            bi = b.get("bookInfo", {})
            if not bi.get("bookId"):
                continue
            candidates.append({
                "bookId": bi.get("bookId", ""),
                "title": bi.get("title", ""),
                "author": bi.get("author", ""),
                "rating": bi.get("newRating", 0),
                "ratingCount": bi.get("newRatingCount", 0),
                "readingCount": b.get("readingCount", 0),
                "scope": group.get("scope", 0),
            })

    if not candidates:
        print(json.dumps({"error": True, "message": f"未找到「{args.keyword}」"}, ensure_ascii=False))
        return

    # 匹配度打分：标题包含关键词 +2，精确匹配 +3，评分高 +1，在读人数多 +1
    keyword = args.keyword.lower()
    for c in candidates:
        title_lower = c["title"].lower()
        score = 0
        if keyword == title_lower:
            score += 3
        elif keyword in title_lower:
            score += 2
        if c["rating"] and c["rating"] >= 900:
            score += 1
        if c["readingCount"] >= 1000:
            score += 1
        c["_score"] = score

    # 按匹配度降序，同分按评分降序
    candidates.sort(key=lambda x: (x["_score"], x["rating"]), reverse=True)

    # 输出
    items = []
    for c in candidates:
        items.append({
            "bookId": c["bookId"],
            "title": c["title"],
            "author": c["author"],
            "rating": rating_to_str(c["rating"]),
            "readingCount": c["readingCount"],
            "matchScore": c["_score"],
        })

    output = {
        "keyword": args.keyword,
        "total": len(items),
        "candidates": items,
    }

    if getattr(args, "json", False):
        return output
    else:
        print(f"「{args.keyword}」找到 {len(items)} 本相关书：\n")
        for i, item in enumerate(items, 1):
            print(f"{i}. {item['title']}  {item['author']}  {item['rating']}  {item['readingCount']}人在读  [匹配度:{item['matchScore']}]  id:{item['bookId']}")
        print(f"\n使用 bookId 继续操作，如：$WR book {items[0]['bookId']}")


def cmd_inspect(api: WereadAPI, args):
    """一键查看：search + book + notes（含划线和想法），1 次 CLI 调用替代 3 轮。"""
    # 1. search
    search_result = api.call("/store/search", keyword=args.keyword, scope=args.scope or 10)
    results = search_result.get("results", [])
    all_books = []
    for group in results:
        for b in group.get("books", []):
            bi = b.get("bookInfo", {})
            if bi.get("bookId"):
                all_books.append(bi)
    if not all_books:
        print(json.dumps({"error": True, "message": f"未找到「{args.keyword}」"}, ensure_ascii=False))
        return

    book = all_books[0]
    book_id = book.get("bookId", "")
    title = book.get("title", "")
    author = book.get("author", "")

    # 2. book info（已在 search 中拿到基础信息，补充详情）
    try:
        info = api.call("/book/info", bookId=book_id)
    except WereadError:
        info = book

    # 3. notes
    try:
        bm = api.call("/book/bookmarklist", bookId=book_id)
    except WereadError:
        bm = {}
    chapters = {c.get("chapterUid"): c.get("title", "") for c in bm.get("chapters", [])}
    highlights = [
        {"chapter": chapters.get(u.get("chapterUid"), ""), "text": u.get("markText", ""),
         "createTime": ts_to_date(u.get("createTime", 0)) if u.get("createTime") else "",
         "range": u.get("range", "")}
        for u in bm.get("updated", [])[:50]
    ]

    try:
        rv = api.call("/review/list/mine", bookid=book_id, count=50, synckey=0)
    except WereadError:
        rv = {}
    thoughts = [
        {"chapter": r.get("review", {}).get("chapterName", ""),
         "content": r.get("review", {}).get("content", ""),
         "createTime": ts_to_date(r.get("review", {}).get("createTime", 0)) if r.get("review", {}).get("createTime") else ""}
        for r in rv.get("reviews", [])[:50]
    ]

    output = {
        "bookId": book_id,
        "title": title,
        "author": author or info.get("author", ""),
        "rating": rating_to_str(info.get("newRating")),
        "publisher": info.get("publisher", ""),
        "category": info.get("category", ""),
        "wordCount": info.get("wordCount", 0),
        "highlights": highlights,
        "thoughts": thoughts,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


def cmd_shelf(api: WereadAPI, args):
    """书架管理"""
    result = api.call("/shelf/sync")

    books = result.get("books", [])
    albums = result.get("albums", [])
    mp = result.get("mp")
    total = len(books) + len(albums) + (1 if mp else 0)
    finished = sum(1 for b in books if b.get("finishReading")) + sum(1 for a in albums if a.get("albumInfo", {}).get("finish"))

    # --summary 模式：纯统计，不输出书单
    if getattr(args, "summary", False):
        cats = {}
        for b in books:
            cat = b.get("category", "未分类") or "未分类"
            cats[cat] = cats.get(cat, 0) + 1
        top_cats = sorted(cats.items(), key=lambda x: x[1], reverse=True)[:5]
        now = int(time.time())
        recent_30d = sum(1 for b in books if b.get("readUpdateTime", 0) > now - 30 * 86400)
        cold = sum(1 for b in books if not b.get("readUpdateTime") and not b.get("finishReading"))

        summary = {
            "total": total,
            "finished": finished,
            "reading": total - finished,
            "completionRate": f"{finished / total * 100:.0f}%" if total else "0%",
            "recent30d": recent_30d,
            "coldUnopened": cold,
            "topCategories": [{"name": c, "count": n} for c, n in top_cats],
        }
        if getattr(args, "json", False):
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        else:
            print(f"📚 书架：{total} 本 | 读完 {finished} ({summary['completionRate']}) | 在读 {total - finished}")
            print(f"   近 30 天活跃：{recent_30d} 本 | 未打开：{cold} 本")
            if top_cats:
                print(f"   分类 TOP5：" + " | ".join(f"{c}({n})" for c, n in top_cats))
        return

    # 解析 --fields
    field_filter = None
    if getattr(args, "fields", None):
        field_filter = set(args.fields.split(","))

    if getattr(args, "json", False) is True:
        # JSON 模式：应用字段过滤
        filtered = {
            "books": [_filter_fields(b, field_filter) for b in books],
            "albums": [_filter_fields(a, field_filter) for a in albums],
            "total": total, "finished": finished,
        }
        return filtered
        return

    # 文本模式
    secret_books = sum(1 for b in books if b.get("secret") == 1)
    public_books = len(books) - secret_books
    secret_albums = sum(1 for a in albums if a.get("albumInfoExtra", {}).get("secret") == 1)
    public_albums = len(albums) - secret_albums

    print(f"书架共 {total} 个条目：{len(books)} 本电子书")
    if albums:
        print(f"  + {len(albums)} 个专辑/有声书")
    if mp:
        print(f"  + 1 个文章收藏")
    print(f"公开 {public_books + public_albums}  |  私密 {secret_books + secret_albums}")
    print()

    all_items = []
    for b in books:
        all_items.append({
            "type": "📖", "id": b.get("bookId", ""), "title": b.get("title", ""),
            "author": b.get("author", ""), "category": b.get("category", ""),
            "readUpdateTime": b.get("readUpdateTime", 0), "finishReading": b.get("finishReading", 0),
            "isTop": b.get("isTop", 0), "secret": b.get("secret", 0),
        })
    for a in albums:
        ai = a.get("albumInfo", {})
        aie = a.get("albumInfoExtra", {})
        all_items.append({
            "type": "🎧", "id": ai.get("albumId", ""), "title": ai.get("name", ""),
            "author": ai.get("authorName", ""), "category": "有声书",
            "readUpdateTime": aie.get("lectureReadUpdateTime", 0),
            "finishReading": 1 if ai.get("finish", 0) else 0,
            "isTop": aie.get("isTop", 0), "secret": aie.get("secret", 0),
        })

    page = getattr(args, "page", 1)
    per_page = getattr(args, "per_page", 10)
    page_items, total_pages, has_prev, has_next = paginate_mark(all_items, page, per_page)

    for i, item in enumerate(page_items, (page - 1) * per_page + 1):
        tags = []
        if item["isTop"]: tags.append("置顶")
        if item["finishReading"]: tags.append("已读完")
        if item["secret"]: tags.append("私密")
        tag_str = " " + " ".join(f"[{t}]" for t in tags) if tags else ""
        time_str = f"  最近: {ts_to_date(item['readUpdateTime'])}" if item["readUpdateTime"] else ""
        print(f"{i}. {item['type']} {item['title']}{tag_str}")
        print(f"   {item['author']}{time_str}")
        if item["id"] and item["type"] == "📖":
            print(f"   [查看]({make_deep_link(item['id'])})")
        print()

    print_pagination(page, total_pages, has_prev, has_next)


def cmd_book(api: WereadAPI, args):
    """书籍信息"""
    book_id = args.bookId
    info = api.call("/book/info", bookId=book_id)

    print(f"《{info.get('title', '')}》")
    print(f"作者: {info.get('author', '')}")
    if info.get("translator"):
        print(f"译者: {info.get('translator', '')}")
    print(f"评分: {rating_to_str(info.get('newRating'))}  ({info.get('newRatingCount', 0)}人评)")
    print(f"分类: {info.get('category', '')}")
    print(f"出版社: {info.get('publisher', '')}")
    if info.get("publishTime"):
        print(f"出版: {info.get('publishTime', '')}")
    if info.get("isbn"):
        print(f"ISBN: {info.get('isbn', '')}")
    if info.get("wordCount"):
        wc = info["wordCount"]
        if wc >= 10000:
            print(f"字数: {wc/10000:.1f}万字")
        else:
            print(f"字数: {wc}字")
    if info.get("intro"):
        print(f"\n简介: {info['intro']}")
    print(f"\n[打开阅读]({make_deep_link(book_id)})")

    # chapters
    if getattr(args, "chapters", False):
        print("\n── 章节目录 ──")
        ch_info = api.call("/book/chapterinfo", bookId=book_id)
        chs = ch_info.get("chapters", [])
        page = getattr(args, "chapters_page", 1)
        per_page = getattr(args, "chapters_per_page", 20)
        page_items, total_pages, has_prev, has_next = paginate_mark(chs, page, per_page)

        for ch in page_items:
            indent = "  " * max(0, ch.get("level", 1) - 1)
            paid = "🔒" if ch.get("paid") == 1 and ch.get("price", 0) > 0 else ""
            mp = " [公众号]" if ch.get("isMPChapter") else ""
            title = ch.get("title", "")
            print(f"{indent}{title}{paid}{mp}")
        if total_pages > 1:
            print(f"\n(第 {page}/{total_pages} 页，--chapters-page N 翻页)")

    # progress
    if getattr(args, "progress", False):
        print("\n── 阅读进度 ──")
        prog = api.call("/book/getprogress", bookId=book_id)
        book = prog.get("book", {})
        pct = book.get("progress", 0)
        rec = book.get("recordReadingTime", 0)
        print(f"进度: {pct}%")
        print(f"累计阅读: {secs_to_hms(rec)}")
        if book.get("updateTime"):
            print(f"最后阅读: {ts_to_date(book['updateTime'])}")
        if book.get("finishTime"):
            print(f"读完: {ts_to_date(book['finishTime'])}")


def cmd_notes(api: WereadAPI, args):
    """笔记划线"""
    book_id = getattr(args, "book", None)

    if book_id:
        # 单本书笔记
        bm = api.call("/book/bookmarklist", bookId=book_id)
        try:
            rv = api.call("/review/list/mine", bookid=book_id, count=50, synckey=0)
        except WereadError:
            rv = {}

        if getattr(args, "json", False) is True:
            output = {"bookmarklist": bm, "reviews": rv}
            return output
            return

        print("── 划线内容 ──")
        updated = bm.get("updated", [])
        chapters_map = {c.get("chapterUid"): c for c in bm.get("chapters", [])}

        page = getattr(args, "page", 1)
        per_page = getattr(args, "per_page", 10)
        page_items, total_pages, has_prev, has_next = paginate_mark(updated, page, per_page)

        if not updated:
            print("暂无划线。")
        else:
            for i, u in enumerate(page_items, (page - 1) * per_page + 1):
                ch = chapters_map.get(u.get("chapterUid"), {})
                ch_title = ch.get("title", f"章节{u.get('chapterUid', '')}")
                print(f"{i}. [{ts_to_date(u.get('createTime', 0))}] {ch_title}")
                print(f"   > {u.get('markText', '')}")
                rng = u.get("range", "")
                if rng and "-" in rng:
                    rs, re = rng.split("-", 1)
                    link = make_deep_link(book_id, str(u.get("chapterUid", "")), rs, re)
                    print(f"   [位置]({link})")
                print()
            if total_pages > 1:
                print(f"(第 {page}/{total_pages} 页)")

        print("\n── 个人想法 ──")
        reviews = rv.get("reviews", [])
        rv_page = getattr(args, "page", 1)
        rv_per_page = getattr(args, "per_page", 10)
        rv_items, rv_tp, _, _ = paginate_mark(reviews, rv_page, rv_per_page)

        if not reviews:
            print("暂无个人想法。")
        else:
            for i, r in enumerate(rv_items, (rv_page - 1) * rv_per_page + 1):
                rev = r.get("review", {})
                star = star_to_str(rev.get("star", -1))
                ch = rev.get("chapterName", "")
                loc = f" [{ch}]" if ch else ""
                print(f"{i}. {star}{loc}  {ts_to_date(rev.get('createTime', 0))}")
                print(f"   {rev.get('content', '')}")
                rng = rev.get("range", "")
                if rng and "-" in rng:
                    rs, re = rng.split("-", 1)
                    link = make_deep_link(book_id, str(rev.get("chapterUid", "")), rs, re)
                    print(f"   [位置]({link})")
                print()
            if rv_tp > 1:
                print(f"(第 {rv_page}/{rv_tp} 页)")

    else:
        # 笔记本概览
        max_pages = getattr(args, "max_pages", 5)
        all_books, pages_fetched = _fetch_all_notebooks(api, max_pages=max_pages)
        all_books.sort(key=lambda x: x["total"], reverse=True)

        if getattr(args, "json", False) is True:
            total_notes = sum(b["total"] for b in all_books)
            output = {
                "totalBookCount": len(all_books),
                "totalNoteCount": total_notes,
                "totalReviewCount": sum(b["reviewCount"] for b in all_books),
                "totalHighlightCount": sum(b["noteCount"] for b in all_books),
                "totalBookmarkCount": sum(b["bookmarkCount"] for b in all_books),
                "books": all_books,
            }
            return output
            return

        if pages_fetched >= max_pages:
            print(f"有笔记的书 (已获取 {pages_fetched} 页，使用 --max-pages N 获取更多)")
        else:
            print(f"有笔记的书共 {len(all_books)} 本")
        total_notes = sum(b["total"] for b in all_books)
        print(f"笔记总数: {total_notes} (想法{sum(b['reviewCount'] for b in all_books)} + 划线{sum(b['noteCount'] for b in all_books)} + 书签{sum(b['bookmarkCount'] for b in all_books)})")
        print()

        page = getattr(args, "page", 1)
        per_page = getattr(args, "per_page", 10)
        page_items, total_pages, has_prev, has_next = paginate_mark(all_books, page, per_page)

        for i, b in enumerate(page_items, (page - 1) * per_page + 1):
            status = "✓读完" if b["markedStatus"] == 1 else f"进度{b['readingProgress']}%"
            print(f"{i}. 《{b['title']}》 {b['author']}  [{status}]")
            print(f"   笔记 {b['total']} 条 (想法{b['reviewCount']} + 划线{b['noteCount']} + 书签{b['bookmarkCount']})")
            print(f"   [查看笔记] weread.py notes --book {b['bookId']}")
            if b["bookId"]:
                print(f"   [打开]({make_deep_link(b['bookId'])})")
            print()

        if total_pages > 1:
            nav = []
            if has_prev:
                nav.append(f"--page {page-1} 上一页")
            if has_next:
                nav.append(f"--page {page+1} 下一页")
            print("  ".join(nav))


def cmd_readdata(api: WereadAPI, args):
    """阅读统计"""
    mode = getattr(args, "mode", "monthly")
    base_time = getattr(args, "time", 0)

    result = api.call("/readdata/detail", mode=mode, baseTime=base_time)

    if getattr(args, "json", False) is True:
        return result
        return

    read_days = result.get("readDays", 0)
    total_secs = result.get("totalReadTime", 0)
    daily_avg = result.get("dayAverageReadTime", 0)
    compare = result.get("compare")

    mode_names = {"weekly": "本周", "monthly": "本月", "annually": "本年", "overall": "总计"}
    print(f"📊 {mode_names.get(mode, mode)}阅读统计")
    print(f"   阅读 {read_days} 天  |  总时长 {secs_to_hms(total_secs)}  |  日均 {secs_to_hms(daily_avg)}")
    if compare is not None:
        direction = "↑" if compare >= 0 else "↓"
        print(f"   较上期: {direction}{abs(compare)*100:.0f}%")

    # 阅读统计摘要
    read_stat = result.get("readStat", [])
    if read_stat:
        parts = []
        for s in read_stat:
            parts.append(f"{s.get('stat', '')}: {s.get('counts', '')}")
        print(f"   " + "  |  ".join(parts))

    print()

    # 读得最多的书
    longest = result.get("readLongest", [])
    if longest:
        print("读得最多:")
        for item in longest[:5]:
            bk = item.get("book", {})
            ai = item.get("albumInfo")
            rt = item.get("readTime", 0)
            name = bk.get("title", "") if bk else (ai.get("name", "") if ai else "未知")
            author = bk.get("author", "") if bk else (ai.get("authorName", "") if ai else "")
            tags = " ".join(f"[{t}]" for t in item.get("tags", []))
            print(f"  · {name}  {author}  {secs_to_hms(rt)}  {tags}")

    # 偏好
    pref_cat = result.get("preferCategory")
    if pref_cat:
        print(f"\n偏好分类: {result.get('preferCategoryWord', '偏好阅读')}")
        for c in pref_cat[:5]:
            print(f"  · {c.get('categoryTitle', '')}  {c.get('readingCount', 0)}本  {secs_to_hms(c.get('readingTime', 0))}")

    pref_time_word = result.get("preferTimeWord")
    if pref_time_word:
        print(f"偏好时段: {pref_time_word}")

    pref_author = result.get("preferAuthor")
    if pref_author:
        print(f"偏好作者:")
        for a in pref_author[:3]:
            print(f"  · {a.get('name', '')}  {a.get('count', 0)}本  {a.get('readTime', '')}")

    # readRate
    rr = result.get("readRate")
    if rr is not None:
        wr = result.get("wrReadTime", 0)
        wl = result.get("wrListenTime", 0)
        print(f"\n阅读/听书: 文字 {secs_to_hms(wr)} ({rr}%)  |  听书 {secs_to_hms(wl)}")

    print()


def cmd_review(api: WereadAPI, args):
    """书籍点评"""
    book_id = args.bookId
    rv_type = getattr(args, "type", 0)
    per_page = getattr(args, "per_page", 10)
    result = api.call("/review/list", bookId=book_id, reviewListType=rv_type,
                       count=per_page, maxIdx=0)

    if getattr(args, "json", False) is True:
        return result
        return

    reviews_cnt = result.get("reviewsCnt", 0)
    print(f"点评共 {reviews_cnt} 条")
    if result.get("deepVRecommendInfo"):
        info = result["deepVRecommendInfo"]
        print(f"{info.get('title', '')}  {info.get('subtitle', '')}")
    print()

    reviews = result.get("reviews", [])
    page = getattr(args, "page", 1)
    per_page = getattr(args, "per_page", 10)
    page_items, total_pages, has_prev, has_next = paginate_mark(reviews, page, per_page)

    for i, r in enumerate(page_items, (page - 1) * per_page + 1):
        rev = r.get("review", {}).get("review", {})
        author = rev.get("author", {})
        name = author.get("name", "匿名")
        star = star_to_str(rev.get("star", 0))
        is_finish = " · 已读完" if rev.get("isFinish") else ""
        ch = rev.get("chapterName", "")
        ch_str = f" · {ch}" if ch else ""
        print(f"{i}. {name}  {star}{is_finish}{ch_str}")
        content = rev.get("content", "")
        print(f"   {truncate(content, 200)}")
        print()

    print_pagination(page, total_pages, has_prev, has_next)


def cmd_discover(api: WereadAPI, args):
    """发现推荐"""
    book_id = getattr(args, "book", None)

    if book_id:
        result = api.call("/book/similar", bookId=book_id, count=getattr(args, "per_page", 10))
    else:
        result = api.call("/book/recommend", count=getattr(args, "per_page", 10))

    if getattr(args, "json", False) is True:
        return result
        return

    if book_id:
        books = result.get("booksimilar", {}).get("books", [])
        print("相似书推荐:")
    else:
        books = result.get("books", [])
        print("为你推荐:")

    if not books:
        print("暂无推荐。")
        return

    page = getattr(args, "page", 1)
    per_page = getattr(args, "per_page", 10)
    page_items, total_pages, has_prev, has_next = paginate_mark(books, page, per_page)

    for i, b in enumerate(page_items, (page - 1) * per_page + 1):
        if book_id:
            bi = b.get("book", {}).get("bookInfo", {})
            reason = ""
        else:
            bi = b
            reason = b.get("reason", "")
        title = bi.get("title", "")
        author = bi.get("author", "")
        rating = rating_to_str(bi.get("newRating"))
        reading = bi.get("readingCount", 0)
        print(f"{i}. 《{title}》 {author}  |  {rating}  |  {reading}人在读")
        if reason:
            print(f"   推荐理由: {reason}")
        if bi.get("intro"):
            print(f"   简介: {truncate(bi['intro'], 100)}")
        print(f"   [打开]({make_deep_link(bi.get('bookId', ''))})")
        print()

    print_pagination(page, total_pages, has_prev, has_next)


# ─── new commands ──────────────────────────────────────────────────────

def cmd_report(api: WereadAPI, args):
    """阅读仪表盘：一年阅读统计 + 书架概览（2 次 API 调用）"""
    # 一次 readdata annually 替代原来的 weekly+monthly+annually 三次调用
    r = api.call("/readdata/detail", mode="annually", baseTime=0)
    rd = r.get("readDays", 0)
    ts = r.get("totalReadTime", 0)
    da = r.get("dayAverageReadTime", 0)
    cmp = r.get("compare")

    print(f"📊 本年阅读：{rd} 天 | {secs_to_hms(ts)} | 日均 {secs_to_hms(da)}")
    if cmp is not None:
        d = "↑" if cmp >= 0 else "↓"
        print(f"   较上期 {d}{abs(cmp)*100:.0f}%")
    stat = r.get("readStat", [])
    if stat:
        parts = [f"{s.get('stat','')}:{s.get('counts','')}" for s in stat]
        print(f"   " + " | ".join(parts))

    # 书架总览
    sh = api.call("/shelf/sync")
    books_list = sh.get("books", [])
    albums = sh.get("albums", [])
    mp = sh.get("mp")
    total = len(books_list) + len(albums) + (1 if mp else 0)
    finished = sum(1 for b in books_list if b.get("finishReading")) + sum(1 for a in albums if a.get("albumInfo", {}).get("finish"))
    print(f"\n📚 书架：{total} 个条目 | 读完 {finished} | 在读 {total - finished}")
    print()


def cmd_export(api: WereadAPI, args):
    """导出划线 + 想法为 Markdown，支持单书和批量。"""
    if not getattr(args, "all", False) and not args.bookId:
        print("错误: 请指定 bookId 或使用 --all 批量导出", file=sys.stderr)
        sys.exit(1)

    fmt = getattr(args, "format", "md") or "md"

    def _export_one(book_id, output_path=None):
        info = api.call("/book/info", bookId=book_id)
        title = info.get("title", book_id)
        author = info.get("author", "")
        publisher = info.get("publisher", "")
        cover = info.get("cover", "")
        word_count = info.get("wordCount", 0)
        rating = info.get("newRating", 0)
        wc_str = f"{word_count/10000:.1f}万字" if word_count >= 10000 else f"{word_count}字" if word_count else ""

        bm = api.call("/book/bookmarklist", bookId=book_id)
        chapters_map = {c.get("chapterUid"): c for c in bm.get("chapters", [])}
        updated = bm.get("updated", [])

        try:
            rv = api.call("/review/list/mine", bookid=book_id, count=200, synckey=0)
        except WereadError:
            rv = {}
        reviews = rv.get("reviews", [])
        reviews_map = {}
        for r in reviews:
            rev = r.get("review", {})
            rng = rev.get("range", "")
            if rng:
                reviews_map[rng] = rev

        # 按章节分组统计
        ch_counts = {}
        for u in updated:
            ch_uid = u.get("chapterUid")
            ch = chapters_map.get(ch_uid, {})
            ch_title = ch.get("title", f"章节{ch_uid}")
            ch_counts[ch_title] = ch_counts.get(ch_title, 0) + 1

        safe_name = title.replace("/", "_").replace(" ", "_")
        ext_map = {"md": ".md", "json": ".json", "csv": ".csv", "card": ".html"}
        ext = ext_map.get(fmt, ".md")
        if not output_path:
            output_path = f"/tmp/weread_export_{safe_name}{ext}"

        # ── JSON ──
        if fmt == "json":
            data = {
                "bookId": book_id, "title": title, "author": author,
                "publisher": publisher, "wordCount": word_count, "rating": rating_to_str(rating),
                "highlights": [{"chapter": chapters_map.get(u.get("chapterUid"), {}).get("title", ""),
                                "text": u.get("markText", ""),
                                "createTime": ts_to_date(u.get("createTime", 0)) if u.get("createTime") else "",
                                "range": u.get("range", ""),
                                "thought": reviews_map.get(u.get("range", ""), {}).get("content", "")}
                               for u in updated],
                "thoughts": [{"chapter": r.get("review", {}).get("chapterName", ""),
                              "content": r.get("review", {}).get("content", ""),
                              "createTime": ts_to_date(r.get("review", {}).get("createTime", 0)) if r.get("review", {}).get("createTime") else ""}
                             for r in reviews],
            }
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return output_path, len(updated), len(reviews)

        # ── CSV ──
        if fmt == "csv":
            import csv as csv_module
            with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
                w = csv_module.writer(f)
                w.writerow(["type", "chapter", "text", "thought", "createTime", "range"])
                for u in updated:
                    ch = chapters_map.get(u.get("chapterUid"), {})
                    ts = ts_to_date(u.get("createTime", 0)) if u.get("createTime") else ""
                    rng = u.get("range", "")
                    thought = reviews_map.get(rng, {}).get("content", "")
                    w.writerow(["highlight", ch.get("title", ""), u.get("markText", ""), thought, ts, rng])
                for r in reviews:
                    rev = r.get("review", {})
                    ts = ts_to_date(rev.get("createTime", 0)) if rev.get("createTime") else ""
                    rng = rev.get("range", "")
                    if rng not in reviews_map or not reviews_map[rng].get("content"):
                        w.writerow(["thought", rev.get("chapterName", ""), "", rev.get("content", ""), ts, rng])
            return output_path, len(updated), len(reviews)

        # ── Card (HTML) ──
        if fmt == "card":
            rating_str = rating_to_str(rating)
            title_safe = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            author_safe = author.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            highlights_html = ""
            last_ch = None
            for u in updated:
                ch_uid = u.get("chapterUid")
                ch = chapters_map.get(ch_uid, {})
                ch_title = ch.get("title", "").replace("&", "&amp;").replace("<", "&lt;")
                if ch_uid != last_ch:
                    if last_ch is not None:
                        highlights_html += "</div>\n"
                    highlights_html += f'<div class="chapter"><h3>{ch_title}</h3>\n'
                    last_ch = ch_uid
                text = u.get("markText", "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                highlights_html += f'<blockquote>{text}</blockquote>\n'
                rng = u.get("range", "")
                if rng in reviews_map:
                    thought = reviews_map[rng].get("content", "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    if thought:
                        highlights_html += f'<p class="thought">💭 {thought}</p>\n'
            if last_ch is not None:
                highlights_html += "</div>\n"

            html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title_safe} · 微信读书笔记</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:"Noto Serif SC",Georgia,serif;background:#fdfcfa;color:#2c2c2c;max-width:720px;margin:0 auto;padding:40px 24px 80px;line-height:1.85}}
h1{{font-size:1.8em;margin-bottom:4px;font-weight:700}}
.meta{{color:#888;font-size:.9em;margin-bottom:32px}}
.meta span{{margin-right:16px}}
.cover{{float:right;width:100px;height:140px;object-fit:cover;border-radius:4px;margin:0 0 16px 16px;box-shadow:0 2px 8px rgba(0,0,0,.12)}}
.stats{{background:#f5f0e8;border-radius:8px;padding:16px 20px;margin-bottom:28px;font-size:.9em}}
.chapter{{margin-bottom:8px}}
.chapter h3{{font-size:1em;color:#9d7a58;margin:24px 0 8px;font-weight:600}}
blockquote{{border-left:3px solid #d4c5b2;padding:6px 0 6px 16px;margin:8px 0;color:#444;font-style:italic}}
.thought{{color:#6b5a4e;font-size:.9em;padding:2px 0 2px 16px;margin:4px 0 12px}}
.footer{{margin-top:48px;padding-top:16px;border-top:1px solid #e8e0d5;color:#aaa;font-size:.8em;text-align:center}}
</style></head><body>
<h1>《{title_safe}》</h1>
<div class="meta"><span>{author_safe}</span><span>{rating_str}</span><span>{len(updated)} 条划线</span></div>
<div class="stats">📊 共 <b>{len(updated)}</b> 条划线 + <b>{len(reviews)}</b> 条想法  |  {len(ch_counts)} 个章节</div>
{highlights_html}
<div class="footer">由微信读书导出 · {time.strftime('%Y-%m-%d', time.localtime())}</div>
</body></html>"""
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(html)
            return output_path, len(updated), len(reviews)

        # ── Markdown (default) ──
        out = []
        out.append(f"# 《{title}》划线笔记")
        meta = [f"**{author}**"]
        if publisher:
            meta.append(f"出版社: {publisher}")
        if wc_str:
            meta.append(f"字数: {wc_str}")
        meta.append(f"共 {len(updated)} 条划线 + {len(reviews)} 条想法")
        out.append("  |  ".join(meta))
        out.append("")

        if ch_counts:
            out.append("## 📊 章节分布\n")
            for ch_title, cnt in sorted(ch_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
                out.append(f"- {ch_title}: {cnt} 条划线")
            out.append("")

        last_ch = None
        for u in updated:
            ch_uid = u.get("chapterUid")
            ch = chapters_map.get(ch_uid, {})
            ch_title = ch.get("title", "")
            if ch_uid != last_ch:
                out.append(f"## {ch_title}\n")
                last_ch = ch_uid
            ts = u.get("createTime", 0)
            ts_str = f" ({ts_to_date(ts)})" if ts else ""
            out.append(f"> {u.get('markText', '')}{ts_str}\n")
            rng = u.get("range", "")
            if rng in reviews_map:
                rev = reviews_map[rng]
                content = rev.get("content", "")
                if content:
                    out.append(f"💭 {content}\n")
            out.append("")

        text = "\n".join(out)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(text)
        return output_path, len(updated), len(reviews)

    # ── 批量导出 ──
    if getattr(args, "all", False):
        print("正在获取笔记本概览...")
        max_pages = getattr(args, "max_pages", 10)
        all_books, _ = _fetch_all_notebooks(api, max_pages=max_pages)
        all_books.sort(key=lambda x: x["total"], reverse=True)
        output_dir = getattr(args, "output", "/tmp/weread_export")
        os.makedirs(output_dir, exist_ok=True)

        total_lines = 0
        total_thoughts = 0
        done = 0
        for b in all_books:
            try:
                safe_name = b["title"].replace("/", "_").replace(" ", "_")
                path, lines, thoughts = _export_one(b["bookId"], os.path.join(output_dir, f"{safe_name}.md"))
                done += 1
                total_lines += lines
                total_thoughts += thoughts
                print(f"  ✓ [{done}/{len(all_books)}] {b['title']} ({lines}划线 + {thoughts}想法)")
            except WereadError:
                print(f"  ✗ [{done+1}/{len(all_books)}] {b['title']} 导出失败")

        print(f"\n批量导出完成: {done}/{len(all_books)} 本成功")
        print(f"划线 {total_lines} + 想法 {total_thoughts}  |  输出目录: {output_dir}")
        return

    # ── 单书导出 ──
    book_id = args.bookId
    output_path = getattr(args, "output", None)
    path, lines, thoughts = _export_one(book_id, output_path)
    print(f"已导出到 {path}")
    print(f"共 {lines} 条划线 + {thoughts} 条想法")


def cmd_organize(api: WereadAPI, args):
    """收集笔记数据，输出结构化 JSON 供 LLM 直接分析整理。"""
    book_id = getattr(args, "book", None)
    max_books = getattr(args, "max_books", 10)
    max_notes = getattr(args, "max_notes", 50)

    def _fetch_book_notes(bid, title, author):
        """获取单本书的划线和想法"""
        try:
            bm = api.call("/book/bookmarklist", bookId=bid)
        except WereadError:
            bm = {}
        chapters = {c.get("chapterUid"): c.get("title", "") for c in bm.get("chapters", [])}

        highlights = []
        for u in bm.get("updated", []):
            if len(highlights) >= max_notes:
                break
            highlights.append({
                "chapter": chapters.get(u.get("chapterUid"), ""),
                "text": u.get("markText", ""),
                "createTime": ts_to_date(u.get("createTime", 0)) if u.get("createTime") else "",
                "range": u.get("range", ""),
            })

        try:
            rv = api.call("/review/list/mine", bookid=bid, count=max_notes, synckey=0)
        except WereadError:
            rv = {}
        thoughts = []
        for r in rv.get("reviews", []):
            if len(thoughts) >= max_notes:
                break
            rev = r.get("review", {})
            thoughts.append({
                "chapter": rev.get("chapterName", ""),
                "content": rev.get("content", ""),
                "createTime": ts_to_date(rev.get("createTime", 0)) if rev.get("createTime") else "",
                "range": rev.get("range", ""),
                "star": rev.get("star", -1),
            })

        return {"bookId": bid, "title": title, "author": author,
                "highlights": highlights, "thoughts": thoughts}

    books_data = []
    total_h = 0
    total_t = 0

    if book_id:
        # 单书模式
        try:
            info = api.call("/book/info", bookId=book_id)
            bd = _fetch_book_notes(book_id, info.get("title", ""), info.get("author", ""))
            books_data.append(bd)
            total_h = len(bd["highlights"])
            total_t = len(bd["thoughts"])
        except WereadError as e:
            print(f"错误: 获取书籍 {book_id} 失败: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # 多书模式：从笔记本概览获取
        all_books, _ = _fetch_all_notebooks(api, max_pages=5)
        all_books.sort(key=lambda x: x["total"], reverse=True)

        done = 0
        for b in all_books[:max_books]:
            try:
                bd = _fetch_book_notes(b["bookId"], b["title"], b["author"])
                books_data.append(bd)
                total_h += len(bd["highlights"])
                total_t += len(bd["thoughts"])
                done += 1
                if not getattr(args, "quiet", False):
                    print(f"[{done}/{min(len(all_books), max_books)}] {b['title']} ({len(bd['highlights'])}划线 + {len(bd['thoughts'])}想法)", file=sys.stderr)
            except (WereadError, SystemExit):
                pass

    output = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
        "books": books_data,
        "summary": {
            "totalBooks": len(books_data),
            "totalHighlights": total_h,
            "totalThoughts": total_t,
        },
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


def cmd_mirror(api: WereadAPI, args):
    """阅读自我画像：收集多维度数据，供 LLM 进行深度自我对话分析。"""
    depth = getattr(args, "depth", "standard")
    max_books = getattr(args, "books", None) or {"quick": 3, "standard": 10, "deep": 20}.get(depth, 10)
    max_notes = {"quick": 15, "standard": 40, "deep": 80}.get(depth, 40)

    def _log(msg):
        if not getattr(args, "quiet", False):
            print(msg, file=sys.stderr)

    # ── 1. 书架全貌 ──
    _log("[1/4] 获取书架数据...")
    shelf = api.call("/shelf/sync")
    books = shelf.get("books", [])
    albums = shelf.get("albums", [])
    mp = shelf.get("mp")
    total = len(books) + len(albums) + (1 if mp else 0)
    finished = sum(1 for b in books if b.get("finishReading"))
    finished += sum(1 for a in albums if a.get("albumInfo", {}).get("finish"))

    cats = {}
    for b in books:
        cat = b.get("category", "未分类") or "未分类"
        cats[cat] = cats.get(cat, 0) + 1
    top_cats = sorted(cats.items(), key=lambda x: x[1], reverse=True)[:8]

    now_ts = int(time.time())
    recent_30d = sum(1 for b in books if b.get("readUpdateTime", 0) > now_ts - 30*86400)
    cold = sum(1 for b in books if not b.get("readUpdateTime") and not b.get("finishReading"))

    # ── 2. 阅读统计 ──
    _log("[2/4] 获取阅读统计...")
    profile_stats = {}
    for mode in (["annually"] if depth == "quick" else ["annually", "overall"]):
        try:
            rd = api.call("/readdata/detail", mode=mode, baseTime=0)
            profile_stats[mode] = {
                "readDays": rd.get("readDays", 0),
                "totalReadTime": secs_to_hms(rd.get("totalReadTime", 0)),
                "totalReadTimeSecs": rd.get("totalReadTime", 0),
                "dayAverage": secs_to_hms(rd.get("dayAverageReadTime", 0)),
            }
            if mode == "annually":
                profile_stats["preferTime"] = rd.get("preferTimeWord", "")
                profile_stats["preferCategory"] = [
                    {"name": c.get("categoryTitle", ""), "count": c.get("readingCount", 0),
                     "time": secs_to_hms(c.get("readingTime", 0))}
                    for c in (rd.get("preferCategory") or [])[:5]
                ]
                profile_stats["preferAuthor"] = [
                    {"name": a.get("name", ""), "count": a.get("count", 0), "time": a.get("readTime", "")}
                    for a in (rd.get("preferAuthor") or [])[:5]
                ]
                read_stat = rd.get("readStat", [])
                profile_stats["readStat"] = {s.get("stat", ""): s.get("counts", "") for s in read_stat}
                rr = rd.get("readRate")
                if rr is not None:
                    profile_stats["readRate"] = f"{rr}%"
        except WereadError:
            pass

    # ── 3. 阅读时间线 ──
    _log("[3/4] 构建阅读时间线...")
    timeline = []
    for b in books:
        ft = b.get("finishTime", 0)
        if ft:
            timeline.append({
                "title": b.get("title", ""),
                "author": b.get("author", ""),
                "category": b.get("category", ""),
                "finished": ts_to_date(ft),
                "isTop": b.get("isTop", 0),
            })
    timeline.sort(key=lambda x: x["finished"], reverse=True)

    # ── 4. 笔记内容 ──
    _log("[4/4] 获取笔记内容...")
    all_notes_books, _ = _fetch_all_notebooks(api, max_pages=5)
    all_notes_books.sort(key=lambda x: x["total"], reverse=True)

    annotations = []
    done = 0
    for nb_book in all_notes_books[:max_books]:
        bid = nb_book["bookId"]
        try:
            bm = api.call("/book/bookmarklist", bookId=bid)
        except WereadError:
            continue
        chapters = {c.get("chapterUid"): c.get("title", "") for c in bm.get("chapters", [])}

        highlights = []
        for u in bm.get("updated", []):
            if len(highlights) >= max_notes:
                break
            highlights.append({
                "chapter": chapters.get(u.get("chapterUid"), ""),
                "text": truncate(u.get("markText", ""), 200),
                "range": u.get("range", ""),
            })

        try:
            rv = api.call("/review/list/mine", bookid=bid, count=max_notes, synckey=0)
        except WereadError:
            rv = {}
        thoughts = []
        for r in rv.get("reviews", []):
            if len(thoughts) >= max_notes:
                break
            rev = r.get("review", {})
            thoughts.append({
                "chapter": rev.get("chapterName", ""),
                "content": truncate(rev.get("content", ""), 200),
                "range": rev.get("range", ""),
            })

        density = "high" if len(highlights) >= 30 else ("medium" if len(highlights) >= 10 else "low")
        annotations.append({
            "bookId": bid,
            "title": nb_book["title"],
            "author": nb_book["author"],
            "category": nb_book.get("category", ""),
            "noteDensity": density,
            "totalNotes": nb_book["total"],
            "highlights": highlights,
            "thoughts": thoughts,
        })
        done += 1
        _log(f"  [{done}/{min(len(all_notes_books), max_books)}] {nb_book['title']}")

    # ── 组装输出 ──
    output = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
        "depth": depth,
        "profile": {
            "totalBooks": total,
            "finishedBooks": finished,
            "readingBooks": total - finished,
            "completionRate": f"{finished/total*100:.0f}%" if total > 0 else "0%",
            "categories": [{"name": c, "count": n} for c, n in top_cats],
            "recent30d": recent_30d,
            "coldUnopened": cold,
            **profile_stats,
        },
        "timeline": timeline[:50],
        "annotations": annotations,
    }

    print(json.dumps(output, ensure_ascii=False, indent=2))


def cmd_author(api: WereadAPI, args):
    """作者全景：搜索作者并列出其所有作品"""
    result = api.call("/store/search", keyword=args.name, scope=6)
    results = result.get("results", [])

    author_books = []
    author_name = args.name
    for group in results:
        if group.get("scope") == 6:  # author group
            author_name = group.get("title", args.name)
        for b in group.get("books", []):
            bi = b.get("bookInfo", {})
            if bi.get("bookId"):
                author_books.append({
                    "bookId": bi.get("bookId"),
                    "title": bi.get("title", ""),
                    "author": bi.get("author", ""),
                    "rating": bi.get("newRating"),
                    "ratingCount": bi.get("newRatingCount", 0),
                    "readingCount": b.get("readingCount", 0),
                    "intro": bi.get("intro", ""),
                    "category": bi.get("category", ""),
                    "price": bi.get("price", 0),
                })

    if not author_books:
        print(f"未找到作者「{args.name}」的作品。")
        return

    author_books.sort(key=lambda x: x["readingCount"], reverse=True)

    if getattr(args, "json", False):
        print(json.dumps({"author": author_name, "totalBooks": len(author_books), "books": author_books},
                         ensure_ascii=False, indent=2))
        return

    print(f"✍️  {author_name}  |  {len(author_books)} 部作品")
    avg_rating = sum(b["rating"] or 0 for b in author_books) / max(len(author_books), 1)
    print(f"平均评分: {avg_rating/10:.1f}%  |  代表作: 《{author_books[0]['title']}》({author_books[0]['readingCount']}人在读)")
    print()

    page = getattr(args, "page", 1)
    per_page = getattr(args, "per_page", 20)
    page_items, total_pages, has_prev, has_next = paginate_mark(author_books, page, per_page)

    for i, b in enumerate(page_items, (page - 1) * per_page + 1):
        rating = rating_to_str(b["rating"])
        price = f"¥{b['price']/100:.2f}" if b["price"] else "免费"
        print(f"{i:2d}. 《{b['title']}》  {rating}  {b['readingCount']}人在读  {price}")
        if b.get("intro"):
            print(f"     {truncate(b['intro'], 80)}")
        print(f"     [打开]({make_deep_link(b['bookId'])})")

    print_pagination(page, total_pages, has_prev, has_next)
    print()


def cmd_bestbookmarks(api: WereadAPI, args):
    """书籍热门划线"""
    book_id = args.bookId
    chapter_uid = getattr(args, "chapter", 0)

    result = api.call("/book/bestbookmarks", bookId=book_id, chapterUid=chapter_uid, synckey=0)

    if getattr(args, "json", False) is True:
        return result
        return

    items = result.get("items", [])
    chapters_map = {c.get("chapterUid"): c for c in result.get("chapters", [])}
    total = result.get("totalCount", len(items))

    print(f"热门划线: 共 {total} 条")
    if chapter_uid:
        print(f"(筛选章节: {chapter_uid})")
    print()

    page = getattr(args, "page", 1)
    per_page = getattr(args, "per_page", 10)
    page_items, total_pages, has_prev, has_next = paginate_mark(items, page, per_page)

    for i, item in enumerate(page_items, (page - 1) * per_page + 1):
        ch = chapters_map.get(item.get("chapterUid"), {})
        ch_title = ch.get("title", f"章节{item.get('chapterUid', '')}")
        count = item.get("totalCount", 0)
        print(f"{i}. [{ch_title}]  {count}人划线")
        print(f"   > {item.get('markText', '')}")
        rng = item.get("range", "")
        if rng and "-" in rng:
            rs, re = rng.split("-", 1)
            link = make_deep_link(book_id, str(item.get("chapterUid", "")), rs, re, str(item.get("userVid", "")))
            print(f"   [位置]({link})")
        print()

    print_pagination(page, total_pages, has_prev, has_next)


def cmd_underlines(api: WereadAPI, args):
    """章节划线热度统计"""
    book_id = args.bookId
    chapter_uid = args.chapter

    result = api.call("/book/underlines", bookId=book_id, chapterUid=chapter_uid, synckey=0)

    if getattr(args, "json", False) is True:
        return result
        return

    underlines = result.get("underlines", [])
    print(f"章节划线热度 (chapterUid={chapter_uid}): 共 {len(underlines)} 条")
    print()

    # 按热度排序
    underlines.sort(key=lambda x: x.get("count", 0), reverse=True)

    page = getattr(args, "page", 1)
    per_page = getattr(args, "per_page", 15)
    page_items, total_pages, has_prev, has_next = paginate_mark(underlines, page, per_page)

    for i, u in enumerate(page_items, (page - 1) * per_page + 1):
        rng = u.get("range", "")
        count = u.get("count", 0)
        score = u.get("score", 0)
        bar = "█" * min(count // 10, 30) if count else ""
        print(f"{i:2d}. range={rng}  {count}人划线 热度:{score}  {bar}")
        if rng and "-" in rng:
            rs, re = rng.split("-", 1)
            link = make_deep_link(book_id, str(chapter_uid), rs, re)
            print(f"    [位置]({link})")

    print_pagination(page, total_pages, has_prev, has_next)
    print()


def cmd_readreviews(api: WereadAPI, args):
    """热门划线下想法"""
    book_id = args.bookId
    chapter_uid = args.chapter
    range_str = args.range

    reviews_param = [{"range": range_str, "maxIdx": 0, "count": getattr(args, "per_page", 20)}]
    result = api.call("/book/readreviews", bookId=book_id, chapterUid=chapter_uid, reviews=reviews_param)

    if getattr(args, "json", False) is True:
        return result
        return

    rv_list = result.get("reviews", [])
    if not rv_list:
        print("暂无想法。")
        return

    for rv_group in rv_list:
        total = rv_group.get("totalCount", 0)
        rng = rv_group.get("range", "")
        page_reviews = rv_group.get("pageReviews", [])
        print(f"划线 range={rng}: 共 {total} 条想法")
        for j, pr in enumerate(page_reviews, 1):
            rev = pr.get("review", {})
            author = rev.get("author", {})
            name = author.get("name", "匿名")
            content = rev.get("content", "")
            abstract = rev.get("abstract", "")
            print(f"  {j}. {name}  {ts_to_date(rev.get('createTime', 0))}")
            if abstract:
                print(f"     原文: {truncate(abstract, 100)}")
            print(f"     想法: {content}")
        print()


def cmd_api_call(api: WereadAPI, args):
    """低层逃生口：直接调用任意接口。"""
    params = {}
    if args.param:
        for p in args.param:
            if "=" not in p:
                print(f"错误: 参数格式应为 key=value，收到: {p}", file=sys.stderr)
                sys.exit(1)
            k, v = p.split("=", 1)
            # 尝试类型转换
            if v.isdigit() or (v.startswith("-") and v[1:].isdigit()):
                v = int(v)
            elif v.lower() == "true":
                v = True
            elif v.lower() == "false":
                v = False
            params[k] = v
    try:
        result = api.call(args.api_name, **params)
        return result
    except WereadError as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_shelf_stats(api: WereadAPI, args):
    """书架分析：读完率、活跃度、TBR 堆积"""
    result = api.call("/shelf/sync")
    books = result.get("books", [])
    albums = result.get("albums", [])
    mp = result.get("mp")

    total = len(books) + len(albums) + (1 if mp else 0)
    finished = sum(1 for b in books if b.get("finishReading"))
    finished += sum(1 for a in albums if a.get("albumInfo", {}).get("finish"))
    unfinished = total - finished

    # 活跃度：最近 30 天内有阅读
    now = int(time.time())
    recent = sum(1 for b in books if b.get("readUpdateTime", 0) > now - 30*86400)

    # 冷宫：有但从未打开（readUpdateTime=0 且 !finishReading）
    cold = sum(1 for b in books if not b.get("readUpdateTime") and not b.get("finishReading"))

    # 私密率
    secret_books = sum(1 for b in books if b.get("secret"))
    secret_albums = sum(1 for a in albums if a.get("albumInfoExtra", {}).get("secret"))
    secret_total = secret_books + secret_albums + (1 if mp else 0)

    rate = finished / total * 100 if total > 0 else 0

    print(f"📊 书架分析")
    print(f"   总条目: {total}  (电子书 {len(books)} + 有声书 {len(albums)}" + (" + 文章收藏" if mp else "") + ")")
    print(f"   已读完: {finished}  ({rate:.0f}%)  |  在读: {unfinished}")
    print(f"   近 30 天活跃: {recent} 本")
    print(f"   未打开过: {cold} 本" + (" ← 该清理了" if cold > 10 else ""))
    print(f"   私密: {secret_total}  |  公开: {total - secret_total}")

    # 分类分布
    cats = {}
    for b in books:
        cat = b.get("category", "未分类")
        cats[cat] = cats.get(cat, 0) + 1
    if cats:
        top_cats = sorted(cats.items(), key=lambda x: x[1], reverse=True)[:5]
        print(f"   分类 TOP5: " + " | ".join(f"{c}({n})" for c, n in top_cats))

    # 置顶
    pinned = sum(1 for b in books if b.get("isTop"))
    if pinned:
        print(f"   置顶: {pinned} 本")
    print()


def cmd_list_apis(api: WereadAPI, args):
    """列出可用接口"""
    result = api.call("/_list")
    apis = result.get("apis", [])
    if not apis:
        print("无可用接口。")
        return
    for a in apis:
        name = a.get("api_name", "")
        desc = a.get("description", "")
        params = a.get("params", [])
        print(f"{name}")
        if desc:
            print(f"  {desc}")
        if params:
            for p in params[:5]:
                print(f"    --{p.get('name', '')} ({p.get('type', '')}): {p.get('desc', '')}")
        print()


# ─── main ─────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="微信读书 CLI")
    sub = parser.add_subparsers(dest="command", help="子命令")

    # search
    p = sub.add_parser("search", help="搜索书籍")
    p.add_argument("keyword", help="搜索关键词")
    p.add_argument("--scope", type=int, help="搜索类型 (0=全部 10=电子书 16=网文 14=有声书 6=作者)")
    p.add_argument("--count", type=int, help="每页数量")
    add_common_args(p)
    p.set_defaults(func=cmd_search)

    # resolve: 模糊书名 → 精确 bookId，按匹配度排序
    p = sub.add_parser("resolve", help="模糊书名搜索，返回候选 bookId 列表（按匹配度排序）")
    p.add_argument("keyword", help="书名关键词")
    p.add_argument("--scope", type=int, default=0, help="搜索 scope（默认 0=全部）")
    p.add_argument("--count", type=int, default=10, help="返回候选数量（默认 10）")
    p.add_argument("--json", action="store_true", help="JSON 输出")
    p.set_defaults(func=cmd_resolve)

    # inspect: search + book + notes 一步到位
    p = sub.add_parser("inspect", help="一键查看：搜索书籍并返回详情+划线+想法")
    p.add_argument("keyword", help="书名关键词")
    p.add_argument("--scope", type=int, default=10, help="搜索 scope（默认 10=电子书）")
    p.add_argument("--json", action="store_true", help="JSON 输出（默认即 JSON）")
    p.set_defaults(func=cmd_inspect)

    # shelf
    p = sub.add_parser("shelf", help="查看书架")
    add_common_args(p)
    p.add_argument("--summary", action="store_true", help="仅输出统计摘要，不输出书单")
    p.add_argument("--fields", type=str, default=None,
                   help="JSON 模式指定输出字段（逗号分隔），如 bookId,title,author,category,finishReading")
    p.set_defaults(func=cmd_shelf)

    # book
    p = sub.add_parser("book", help="书籍详情")
    p.add_argument("bookId", help="书籍 ID")
    p.add_argument("--chapters", action="store_true", help="显示章节目录")
    p.add_argument("--progress", action="store_true", help="显示阅读进度")
    p.add_argument("--chapters-page", type=int, default=1)
    p.add_argument("--chapters-per-page", type=int, default=20)
    p.set_defaults(func=cmd_book)

    # notes
    p = sub.add_parser("notes", help="笔记/划线")
    p.add_argument("--book", dest="bookId", help="单本书 bookId，不传则显示笔记本概览")
    add_common_args(p)
    p.add_argument("--max-pages", type=int, default=5, help="笔记本概览最多拉取页数")
    p.set_defaults(func=cmd_notes)

    # readdata
    p = sub.add_parser("readdata", help="阅读统计")
    p.add_argument("--mode", choices=["weekly", "monthly", "annually", "overall"], default="monthly")
    p.add_argument("--time", type=int, default=0, help="基准时间戳 (0=当前)")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_readdata)

    # review
    p = sub.add_parser("review", help="书籍点评")
    p.add_argument("bookId", help="书籍 ID")
    p.add_argument("--type", type=int, default=0, help="0=全部 1=推荐 2=不行 3=最新 4=一般")
    add_common_args(p)
    p.set_defaults(func=cmd_review)

    # discover
    p = sub.add_parser("discover", help="发现推荐")
    p.add_argument("--book", dest="bookId", help="基于此书推荐相似书")
    add_common_args(p)
    p.set_defaults(func=cmd_discover)

    # report
    p = sub.add_parser("report", help="阅读仪表盘（本周+本月+本年+书架）")
    p.set_defaults(func=cmd_report)

    # mirror
    p = sub.add_parser("mirror", help="阅读自我画像：收集多维度数据供深度自我对话")
    p.add_argument("--depth", choices=["quick", "standard", "deep"], default="standard",
                   help="深度：quick=快速(3本书) standard=标准(10本) deep=深度(20本)")
    p.add_argument("--books", type=int, default=None, help="覆盖深度预设的最大书本数")
    p.add_argument("--json", action="store_true", help="JSON 输出（默认即 JSON，此参数兼容）")
    p.add_argument("--quiet", action="store_true", help="静默模式")
    p.set_defaults(func=cmd_mirror)

    # organize
    p = sub.add_parser("organize", help="收集笔记数据输出 JSON，供 LLM 分析整理")
    p.add_argument("--book", dest="bookId", help="单本书 bookId，不传则获取全部有笔记的书")
    p.add_argument("--max-books", type=int, default=10, help="最多处理几本书（默认 10）")
    p.add_argument("--max-notes", type=int, default=50, help="每本书最多取几条笔记（默认 50）")
    p.add_argument("--json", action="store_true", help="JSON 输出（默认即 JSON，此参数兼容）")
    p.add_argument("--quiet", action="store_true", help="静默模式，不输出进度")
    p.set_defaults(func=cmd_organize)

    # export
    p = sub.add_parser("export", help="导出划线+想法")
    p.add_argument("bookId", nargs="?", default=None, help="书籍 ID（单书导出；与 --all 互斥）")
    p.add_argument("--all", action="store_true", help="批量导出所有有笔记的书")
    p.add_argument("--format", "-f", choices=["md", "json", "csv", "card"], default="md",
                   help="输出格式：md=Markdown, json=JSON, csv=表格, card=HTML卡片")
    p.add_argument("--output", help="输出路径（单书：文件路径；--all：目录路径）")
    p.add_argument("--max-pages", type=int, default=10, help="批量导出最多拉取页数")
    p.set_defaults(func=cmd_export)

    # author
    p = sub.add_parser("author", help="作者全景：搜索作者并列出所有作品")
    p.add_argument("name", help="作者名")
    add_common_args(p, json_default=True)
    p.set_defaults(func=cmd_author)

    # bestbookmarks
    p = sub.add_parser("bestbookmarks", help="书籍热门划线（含原文和人数）")
    p.add_argument("bookId", help="书籍 ID")
    p.add_argument("--chapter", type=int, default=0, help="章节 UID（0=全书）")
    add_common_args(p)
    p.set_defaults(func=cmd_bestbookmarks)

    # underlines
    p = sub.add_parser("underlines", help="章节划线热度统计")
    p.add_argument("bookId", help="书籍 ID")
    p.add_argument("--chapter", type=int, required=True, help="章节 UID")
    add_common_args(p)
    p.set_defaults(func=cmd_underlines)

    # readreviews
    p = sub.add_parser("readreviews", help="查看热门划线下方的想法/评论")
    p.add_argument("bookId", help="书籍 ID")
    p.add_argument("--chapter", type=int, required=True, help="章节 UID")
    p.add_argument("--range", required=True, help="划线范围（如 '393-401'，从 bestbookmarks 获取）")
    p.add_argument("--per-page", type=int, default=20)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_readreviews)

    # shelf-stats
    p = sub.add_parser("shelf-stats", help="书架分析：读完率、活跃度、TBR")
    p.set_defaults(func=cmd_shelf_stats)

    # list-apis
    p = sub.add_parser("list-apis", help="列出可用 API")
    p.set_defaults(func=cmd_list_apis)

    # api: 低层逃生口，直接调任意接口
    p = sub.add_parser("api", help="低层逃生口：直接调用任意微信读书接口")
    p.add_argument("api_name", help="接口路径，如 /store/search")
    p.add_argument("--param", action="append", help="接口参数，格式 key=value，可重复")
    p.set_defaults(func=cmd_api_call)

    # 为每个子命令添加 --compact 参数
    for _name, _sub in sub.choices.items():
        _sub.add_argument("--compact", action="store_true", dest="compact", help="压缩 JSON 输出，只保留核心字段")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    api = WereadAPI()
    try:
        result = args.func(api, args)
        _output(result, args)
    except WereadError as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
