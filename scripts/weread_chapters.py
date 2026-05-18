#!/usr/bin/env python3
"""
微信读书章节推荐 — 数据拉取 + 模型语义匹配

用法:
  python3 weread_chapters.py <bookId> "用户查询"

输出 JSON，包含：
- chapters: 章节目录（含层级）
- bookmarks_by_chapter: 按章节聚合的热门划线
- prompt: 直接喂给模型做语义匹配的提示词

模型拿到这个数据后，根据用户查询返回最相关的章节。

示例:
  python3 weread_chapters.py 44026191 "关于财富积累的章节"
"""
import sys, json, subprocess, os
from collections import defaultdict

WR = os.path.join(os.path.dirname(__file__), "weread.py")


def get_chapters(book_id):
    """获取章节目录"""
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
        # 判断层级：3个空格=二级章节
        if line.startswith("   "):
            level = 2
            title = line.strip()
        else:
            level = 1
            title = line.strip()
        if title:
            chapters.append({"idx": len(chapters), "title": title, "level": level})
    return chapters


def get_bookmarks(book_id, count=50):
    """获取热门划线，按 chapterUid 聚合"""
    r = subprocess.run([WR, "bestbookmarks", str(book_id), "--json"],
                      capture_output=True, text=True, timeout=15)
    if not r.stdout.strip():
        return {}
    d = json.loads(r.stdout)
    items = d.get("items", []) or d.get("bookmarks", [])[:count]

    by_chapter = defaultdict(list)
    for bm in items:
        uid = bm.get("chapterUid", 0)
        text = bm.get("markText", "")
        if uid and text:
            by_chapter[uid].append(text)
    return dict(by_chapter)


def get_book_meta(book_id):
    """获取书名和简介"""
    r = subprocess.run([WR, "book", str(book_id)],
                      capture_output=True, text=True, timeout=15)
    meta = {"book_id": str(book_id)}
    for line in r.stdout.split("\n"):
        line = line.strip()
        if line.startswith("《") and line.endswith("》"):
            meta["title"] = line.strip("《》")
        elif line.startswith("作者:"):
            meta["author"] = line.split(":", 1)[1].strip()
        elif line.startswith("评分:"):
            meta["rating"] = line.split(":", 1)[1].strip()
        elif line.startswith("分类:"):
            meta["category"] = line.split(":", 1)[1].strip()
        elif line.startswith("简介:"):
            meta["intro"] = line.split(":", 1)[1].strip()[:300]
    return meta


def build_prompt(meta, chapters, bookmarks_by_chapter, query):
    """构建给模型的提示词"""
    # 构建目录文本
    toc_lines = []
    for ch in chapters:
        indent = "  " if ch["level"] == 2 else ""
        # 找到该章节的划线数
        uid = ch["idx"] + 1  # chapterUid 通常从 1 开始
        bm_count = len(bookmarks_by_chapter.get(uid, []))
        bm_hint = f" [{bm_count}条划线]" if bm_count > 0 else ""
        toc_lines.append(f"{indent}{ch['title']}{bm_hint}")
    toc_text = "\n".join(toc_lines)

    # 构建划线摘要（每个章节最多3条）
    bm_lines = []
    for ch in chapters:
        uid = ch["idx"] + 1
        texts = bookmarks_by_chapter.get(uid, [])
        if texts:
            bm_lines.append(f"\n【{ch['title']}】")
            for t in texts[:3]:
                bm_lines.append(f"  · {t[:100]}")
    bm_text = "\n".join(bm_lines) if bm_lines else "（暂无热门划线）"

    return f"""你是一个阅读助手。用户正在阅读一本书，需要你推荐最相关的章节。

## 书籍信息
- 书名：{meta.get('title', '未知')}
- 作者：{meta.get('author', '未知')}
- 评分：{meta.get('rating', '未知')}
- 简介：{meta.get('intro', '无')[:200]}

## 章节目录（[数字] = 该章节的热门划线数）
{toc_text}

## 各章节热门划线摘要
{bm_text}

## 用户查询
"{query}"

## 你的任务
根据用户查询，从目录中选出最相关的章节（最多5个）。

判断依据：
1. 章节标题与查询的语义匹配度
2. 该章节的热门划线内容是否涉及查询主题
3. 对于投资/理财类书，"财富""收入""投资""复利"等是强信号
4. 对于人生/哲学类书，"幸福""心态""选择""价值观"是强信号

请用 JSON 输出：
{{
  "query": "用户查询",
  "recommendations": [
    {{
      "chapter": "章节名",
      "level": 1或2,
      "reason": "为什么推荐这章（结合划线内容说明）",
      "key_highlights": ["划线摘要1", "划线摘要2"],
      "relevance": "high|medium|low"
    }}
  ],
  "summary": "一句话总结推荐逻辑"
}}

只输出 JSON，不要其他内容。"""


def main():
    if len(sys.argv) < 3:
        print("用法: weread_chapters.py <bookId> \"用户查询\"")
        print("输出 JSON，包含目录、划线和给模型的 prompt")
        sys.exit(1)

    book_id = sys.argv[1]
    query = " ".join(sys.argv[2:])

    # 拉取数据
    meta = get_book_meta(book_id)
    chapters = get_chapters(book_id)
    bookmarks = get_bookmarks(book_id)

    # 构建 prompt
    prompt = build_prompt(meta, chapters, bookmarks, query)

    # 输出
    output = {
        "book": meta,
        "chapters": chapters,
        "bookmarks_by_chapter": {str(k): v for k, v in bookmarks.items()},
        "query": query,
        "prompt": prompt,
        "stats": {
            "total_chapters": len(chapters),
            "chapters_with_highlights": len(bookmarks),
            "total_highlights": sum(len(v) for v in bookmarks.values())
        }
    }

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
