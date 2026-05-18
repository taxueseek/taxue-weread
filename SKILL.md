---
name: taxue-weread
description: 微信读书助手 — 搜索书籍、管理书架、查看笔记划线、浏览书评、阅读统计、发现推荐好书、导出笔记、整理读书笔记、阅读数据分析、精细化推荐（书/作者/章节/版本）、阅读画像分析。当用户提到"微信读书"、"读书笔记"、"书架"、"划线"、"阅读统计"、"读了多久"、"导出笔记"、"推荐书"、"书单"、"阅读画像"、"分析一下我的阅读"、"帮我选书"、"推荐几本书"、"推荐作者"、"哪个版本好"、"重点看哪章"时触发。
version: 1.5.1
---

# WeRead — 微信读书助手

**CLI：`scripts/weread.py`（别名 `WR`）。内置鉴权、缓存（TTL=5min）、重试、分页、深度链接。**

需要 `WEREAD_API_KEY`。LLM 调用一律加 `--json`。详细参数用 `$WR <cmd> --help`。

## 性能基准与效率策略

| 操作 | 耗时 | 说明 |
|------|------|------|
| 进程启动 | ~85ms | 每次调用固定开销，**能合并就合并** |
| search（缓存命中） | ~0.1s | 5分钟TTL |
| search（网络） | ~1s | 实际API请求 |
| 批量查询5本 | ~0.5s | `scripts/weread_batch.py info`，一次进程 |
| 批量搜索多关键词 | ~0.2s | `scripts/weread_batch.py search`，并行 |
| 推荐书（含多关键词） | ~1.3s | `scripts/weread_recommend.py books` |
| 推荐作者 | ~0.6s | `scripts/weread_recommend.py authors` |
| 版本对比 | ~0.8s | `scripts/weread_recommend.py versions` |
| 章节推荐 | ~1s | `scripts/weread_recommend.py chapters` |
| mirror deep | ~2.7s | 最慢，按需使用 |

**核心效率原则：**
1. **能合并就合并**：多本书信息查询用 `weread_batch.py`，一次进程替代多次
2. **能并行就并行**：推荐引擎内部全部并行，不串行调 API
3. **能缓存就缓存**：5分钟 TTL，重复请求自动命中
4. **能推断就不搜**：根据用户已有数据（书架、笔记、阅读历史）直接推断，不重复拉取

## 意图路由

| 用户意图 | 命令 | 备注 |
|----------|------|------|
| 搜书（单本） | `WR search <书名> --json` | 精确匹配 |
| 搜书（批量） | `scripts/weread_search.py 书名1 书名2 ...` | 并行，0.6秒/20本 |
| 书籍详情 | `WR book <bookId>` | 文本输出，含简介 |
| 批量查详情 | `scripts/weread_batch.py info <id1> <id2> ...` | 一次进程 |
| 书架一览 | `WR shelf [--summary]` | 统计用 `--summary` |
| 阅读统计 | `WR readdata --mode monthly\|annually\|overall` | 时长单位：秒 |
| 笔记/划线 | `WR notes --book <bookId>` | |
| 热门划线 | `WR bestbookmarks <bookId>` | TOP20，按热度 |
| 章节目录 | `WR book <bookId> --chapters` | 文本输出 |
| 阅读画像 | `WR mirror [--depth quick\|standard\|deep]` | |
| 导出笔记 | `WR export <bookId>\|--all --output <路径>` | |

## 精细化推荐路由

| 推荐类型 | 命令 | 输出 |
|----------|------|------|
| **推荐书** | `scripts/weread_recommend.py books "关键词"` | 书列表，含评分/分类 |
| **推荐作者** | `scripts/weread_recommend.py authors "关键词"` | 作者列表，含代表作/均分 |
| **版本对比** | `scripts/weread_recommend.py versions "书名"` | 多版本对比，标注推荐 |
| **相似书** | `scripts/weread_recommend.py similar <bookId>` | 相似书列表 |
| **综合画像** | `scripts/weread_recommend.py profile --data <用户数据JSON>` | 多维度推荐 |
| **章节推荐（关键词）** | `scripts/weread_recommend.py chapters <bookId> "关键词"` | 关键词硬匹配 |
| **章节推荐（模型）** | `scripts/weread_chapters.py <bookId> "查询"` → 模型推理 | 语义匹配，更准确 |

## 关键规则

1. **search 优先**：`WR search` 精确匹配。`resolve` 精度低，仅在不确定书名时用。
2. **批量必须并行**：超过3本书或关键词，一律用脚本并行，禁止串行循环。
3. **合并进程**：需要多本书的信息时，用 `weread_batch.py info` 一次查完，不要逐本调 `WR book`。
4. **缓存策略**：5分钟 TTL（`/tmp/weread_cache/`，458文件/3.4MB）。需要刷新时 `WEREAD_NO_CACHE=1`。
5. **API 陷阱**：时长单位秒、newRating 0-1000（除以10得百分比）、progress 0-100 整数。

## 工作流

### 精细化推荐（核心场景）

```
1. 获取用户数据（已有缓存则跳过）
   - WR mirror --depth quick → 书架概览 + 笔记分布
   - WR readdata --mode overall → 核心统计

2. 根据用户需求选择推荐类型
   - "推荐书" → weread_recommend.py books
   - "推荐作者" → weread_recommend.py authors
   - "哪个版本好" → weread_recommend.py versions
   - "重点看哪章" → weread_recommend.py chapters
   - "推荐画像" → weread_recommend.py profile

3. 输出推荐结果
   - 书名/作者/章节名
   - 评分 + 评价人数
   - 推荐理由（结合用户数据）
   - 深度链接（weread://reading?bId=xxx）
```

### 推荐输出格式

**推荐书：**
```
📚 《书名》
   作者 | 评分% (N人评) | 分类
   推荐理由：xxx
   🔗 weread://reading?bId=xxx
```

**版本对比：**
```
📚 书名 (N个版本)
   ✅ 推荐：版本名 | 评分% | N人评
      理由：评分最高，评价人数最多
   ❌ 版本名 | 评分% | N人评
```

**章节推荐（模型驱动）：**
```
步骤：
1. python3 scripts/weread_chapters.py <bookId> "用户查询"
   → 获取目录 + 划线 + prompt
2. 将 prompt 喂给模型做语义匹配
   → 模型返回 JSON（章节名、推荐理由、相关度）
3. 格式化输出给用户

输出示例：
📖 纳瓦尔宝典 — "关于财富积累"
   1. 第一部分 财富 ⭐⭐⭐⭐⭐
      理由：12条热门划线，核心讲的是财富积累方法
      💬 "获得财富的一个途径，就是为社会提供其有需求但无从获得的东西"
   2. 第一章 积累财富 ⭐⭐⭐⭐
      理由：专讲财富积累的具体方法
```

### 阅读画像分析

```
1. WR mirror --depth deep --json → 全量数据
2. WR readdata --mode overall --json → 核心统计
3. 分析：思维结构、阅读人格、年度趋势、盲区识别
4. 生成推荐：基于盲区 → weread_recommend.py profile
```

### 年度报告

```
1. WR mirror --depth deep --json
2. WR readdata --mode annually --json
3. 两个命令可并行
4. 注入 weread-insight 模板 → HTML 报告
```

## 脚本清单

| 脚本 | 用途 |
|------|------|
| `scripts/weread.py` | 核心 CLI，所有 API 调用 |
| `scripts/weread_search.py` | 批量并行搜索（多本书名） |
| `scripts/weread_batch.py` | 批量查询（多本书详情/搜索/笔记/划线） |
| `scripts/weread_recommend.py` | 精细化推荐引擎（书/作者/版本/相似/画像） |
| `scripts/weread_chapters.py` | 章节推荐数据拉取 + 模型 prompt 生成 |

## 参考文档

| 文档 | 何时读取 |
|------|---------|
| `references/troubleshooting.md` | **必读**：API 陷阱 + 字段语义 |
| `references/mirror-guide.md` | 阅读画像分析时 |
| `references/organize-guide.md` | 整理笔记时 |
| `references/material-grading.md` | 提取写作素材时 |
| `references/readdata.md` | 跨周期统计时 |
