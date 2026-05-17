---
name: 微信读书
description: 微信读书助手 — 搜索书籍、管理书架、查看笔记划线、浏览书评、阅读统计、发现推荐好书、导出笔记、整理读书笔记、阅读数据分析。当用户提到"微信读书"、"读书笔记"、"书架"、"划线"、"阅读统计"、"读了多久"、"导出笔记"时触发。
version: 1.5.0
---

# WeRead — 微信读书助手

**CLI：`scripts/weread.py`（别名 `WR`）。内置鉴权、缓存（TTL=5min）、重试、分页、深度链接。**

需要 `WEREAD_API_KEY`。LLM 调用一律加 `--json`。详细参数用 `$WR <cmd> --help`。

## 意图路由

| 用户意图 | 命令 | 需读取 |
|----------|------|--------|
| 搜书/找书 | `WR inspect <书名>` 或 `WR search <关键词> [--scope N]` | — |
| 书籍详情/进度 | `WR book <bookId> [--progress] [--chapters]` | — |
| 书架一览 | `WR shelf [--summary] [--fields bookId,title,author]` | — |
| 阅读统计/时长 | `WR readdata --mode=monthly\|annually\|overall` | `references/troubleshooting.md` |
| 笔记/划线/想法 | `WR notes --book <bookId>` | — |
| 热门划线/书评 | `WR bestbookmarks <bookId>` / `WR review <bookId>` | — |
| 推荐/相似书 | `WR discover [--book <bookId>]` | — |
| 阅读画像 | `WR mirror [--depth quick\|standard\|deep] [--books N]` | `references/mirror-guide.md` |
| 整理读书笔记/读后感 | `WR organize [--max-books 10] [--max-notes 50]` | `references/organize-guide.md` |
| 年度报告/可视化 | `WR mirror --depth deep` + `WR readdata --mode annually` | `references/data.md` |
| 导出笔记 | `WR export <bookId>\|--all --output <路径>` | — |
| 书架分析 | `WR shelf-stats` | — |

## 关键规则

1. **inspect 优先**：用户给书名想看书/笔记时，优先 `WR inspect <书名>` 一步到位。
2. **scope 默认**：默认 scope=0（泛搜）；用户明确说"找书"/"搜书"用 scope=10。
3. **shelf 精简**：统计用 `--summary`（省 80% tokens）；书单用 `--fields bookId,title,author,category,finishReading`。
4. **mirror 控制**：用 `--books N` 控制拉取量，避免 context 溢出。
5. **缓存**：CLI 内置 5 分钟文件缓存。需要刷新时用环境变量 `WEREAD_NO_CACHE=1`。
6. **API 陷阱**：展示数据前必须确认语义（时长单位秒、newRating 0-1000 刻度、progress 0-100 整数等）。详见 `references/troubleshooting.md`。

## 工作流

| 用户说 | 做法 |
|--------|------|
| "查三体" / "三体的笔记" | `WR inspect 三体` |
| "书架统计" | `WR shelf --summary` |
| "本月读了多久" | `WR readdata --mode monthly` |
| "帮我看看阅读" | `WR mirror --depth quick --json`（追问再加深） |
| "整理读书笔记" | `WR organize --quiet` → 分析 JSON |
| "年度报告" | `WR mirror --depth deep --quiet` + `WR readdata --mode annually --json` → `weread-insight` |

## 参考文档（按需读取）

| 文档 | 何时读取 |
|------|---------|
| `references/troubleshooting.md` | **必读**：16 条 API 陷阱 + 条件返回字段表 + 跨周期算法 + 笔记接口层级 |
| `references/mirror-guide.md` | 做阅读画像分析时：分析维度 + 沉睡划线 + 感想词频 + 阅读人格类型 + 盲区识别 |
| `references/organize-guide.md` | 整理笔记时：三层蒸馏结构 + 跨书关联 + 装饰性检测 |
| `references/material-grading.md` | 提取写作素材时：A/B/C 分级 + 装饰性检测 + 感想特殊价值 |
| `references/readdata.md` | 跨周期统计组合时：字段单位 + 周期组合 |
| `references/scope.md` | 不确定 scope 值时：完整 scope 列表 |
