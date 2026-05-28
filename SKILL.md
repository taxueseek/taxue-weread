---
name: taxue-weread
description: |
  微信读书原子操作层。搜索书籍、管理书架、查看笔记划线、阅读统计、导出笔记、每日回顾、精细化推荐、阅读画像、笔记整理。
  当用户需要直接操作微信读书数据（搜书、查书架、看笔记、统计、导出、回顾、推荐、画像）时触发。
  触发：搜书、查书架、看笔记、导出划线、阅读统计、读了多少、书架有几本、
        这本书划线、我的笔记、读书报告、推荐书、微信读书、weread、
        今日笔记、推一条划线、读书回顾、每日回顾、推荐几本书、推荐作者、
        哪个版本好、重点看哪章、阅读画像、分析一下我的阅读、帮我选书
version: 1.7.0
---

# taxue-weread：微信读书原子操作层

> 数据不流动就是死数据。让 LLM 直接读写微信读书，不绕弯。

---

## 核心哲学

### 原则 1：Python 直调，不套壳
LLM 直接调 Python 脚本，少一层进程开销，少一个依赖检查。

### 原则 2：能合并就合并，能并行就并行
每次进程启动 ~85ms 固定开销。多本书信息用 `weread_batch.py` 一次搞定，推荐引擎内部全部并行，5 分钟内的重复查询走缓存。

### 原则 3：错误必须可行动
API 返回的 `errcode` 不是给人看的，是给 LLM 看的。每个错误码对应一个明确动作，LLM 看到错误就知道下一步做什么。

---

## Phase 0：意图验证

收到请求后，先判断用户真正要什么：

```
用户说了什么？
├── 搜书 / 找书 / 有没有这本书          → search / resolve
├── 书架 / 在读 / 读了几本               → shelf / shelf-stats
├── 笔记 / 划线 / 摘抄 / 想法           → notes / bestbookmarks
├── 这本书的详情 / 章节 / 进度           → book / inspect
├── 读了多久 / 统计 / 报告              → readdata / report
├── 导出 / 下载 / 备份                  → export（支持 md/json/csv/card）
├── 今日笔记 / 推一条划线 / 回顾         → daily-review
├── 推荐书 / 推荐作者 / 哪个版本好       → weread_recommend.py
├── 重点看哪章 / 章节推荐                → weread_chapters.py
├── 阅读画像 / 分析我的阅读              → mirror
├── 笔记整理 / 提炼写作素材              → organize
└── 想搞懂 X / 系统学习 X                → 路由到 advisor/path
```

**验证点**：用户给的是书名还是 bookId？书名必须先 `search` 或 `resolve` 拿 bookId，禁止裸传书名给需要 bookId 的接口。

---

## Phase 1：执行

**CLI 路径**：`python3 ~/.agents/skills/taxue-weread/scripts/weread.py`（别名 `WR`）

**所有命令加 `--json`**，让 LLM 能解析结构化输出。

### 意图路由表

| 用户意图 | 命令 | 缓存 |
|---------|------|------|
| 搜书 | `WR search <keyword> --json` | 5min |
| 模糊书名→bookId | `WR resolve <书名> --json` | 5min |
| 一键查详情+划线 | `WR inspect <书名> --json` | 5min |
| 查书架 | `WR shelf --json` | 5min |
| 书架精简统计 | `WR shelf --summary` | 5min |
| 书架分析 | `WR shelf-stats` | 5min |
| 书籍详情 | `WR book <id> --json` | 5min |
| 章节目录 | `WR book <id> --chapters` | 5min |
| 笔记/划线 | `WR notes --book <id> --json` | 5min |
| 热门划线 | `WR bestbookmarks <id> --json` | 5min |
| 划线热度统计 | `WR underlines <id> --chapter <uid> --json` | 5min |
| 划线下想法 | `WR readreviews <id> --chapter <uid> --range "x-y" --json` | 5min |
| 阅读统计 | `WR readdata --mode overall --json` | 5min |
| 阅读仪表盘 | `WR report` | 实时 |
| 阅读画像 | `WR mirror [--depth quick\|standard\|deep]` | 5min |
| 书籍点评 | `WR review --book <id> --json` | 5min |
| 发现推荐 | `WR discover --json` | 5min |
| 导出划线+想法 | `WR export <id> --format md\|json\|csv\|card` | 实时 |
| 批量导出全部 | `WR export --all --output <目录>` | 实时 |
| 收集笔记数据 | `WR organize --json` | 实时 |
| 作者全景 | `WR author <name> --json` | 5min |
| 低层逃生口 | `WR api <api_name> --json` | 按接口 |
| 列出可用API | `WR list-apis` | 无 |

### 批量操作

| 场景 | 命令 | 为什么更快 |
|------|------|----------|
| 多本书详情 | `python3 scripts/weread_batch.py info <id1> <id2> ...` | 一次进程替代 N 次 |
| 多关键词搜索 | `python3 scripts/weread_batch.py search <kw1> <kw2> ...` | 一次进程替代 N 次 |
| 批量并行搜索 | `python3 scripts/weread_search.py <书名1> <书名2> ...` | 并行，0.6秒/20本 |

### 精细化推荐引擎

| 场景 | 命令 | 耗时 |
|------|------|------|
| 推荐书 | `python3 scripts/weread_recommend.py books "关键词" [--limit 10]` | ~1.3s |
| 推荐作者 | `python3 scripts/weread_recommend.py authors "关键词" [--limit 5]` | ~0.6s |
| 版本对比 | `python3 scripts/weread_recommend.py versions "书名"` | ~0.8s |
| 相似书 | `python3 scripts/weread_recommend.py similar <bookId>` | ~1s |
| 综合画像推荐 | `python3 scripts/weread_recommend.py profile --data <用户数据JSON>` | ~1s |
| 章节推荐（关键词） | `python3 scripts/weread_recommend.py chapters <bookId> "关键词"` | ~1s |
| 章节推荐（语义） | `python3 scripts/weread_chapters.py <bookId> "查询"` → 喂模型 | ~1s |

---

## Phase 2：输出格式化

### 数据展示规范

| 字段类型 | 规则 | 示例 |
|---------|------|------|
| Unix 时间戳 | → `YYYY-MM-DD` | `1748563200` → `2025-05-30` |
| 阅读时长（秒） | → `X小时Y分钟` | `3661` → `1小时1分钟` |
| 进度 | → `X%` | `75` → `75%` |
| bookId | 不裸出现 | 转 `weread://reading?bId=xxx` 链接 |
| 搜索结果 | 编号展示方便选择 | 1. 《三体》刘慈欣 ⭐8.8 |
| 评分（newRating） | 除以10转百分制 | `930` → `93%` |

### 深度链接格式

```
书籍：weread://reading?bId={bookId}
章节：weread://reading?bId={bookId}&chapterUid={chapterUid}
划线：weread://bestbookmark?bookId={bookId}&chapterUid={chapterUid}&rangeStart={start}&rangeEnd={end}
```

---

## 错误处理

| 错误 | 含义 | LLM 应该做什么 |
|------|------|---------------|
| `WEREAD_API_KEY 未设置` | 环境变量缺失 | 提示用户 `export WEREAD_API_KEY=wrk-xxx` |
| `API 错误 (errcode=401)` | Key 失效 | 提示用户重新获取 API Key |
| `API 错误 (errcode=404)` | 资源不存在 | 告诉用户这本书/笔记不存在 |
| `⚠️ upgrade_info` | 技能版本需升级 | 立即暂停，按提示升级后重试 |
| `HTTP 5xx` | 服务端错误 | 已自动重试 3 次，仍失败则告知用户稍后再试 |
| 书名搜不到 | 多候选或零结果 | 展示候选列表让用户选，或建议换关键词 |

---

## 边界

- **不做**：裸传书名给需要 bookId 的接口（必须先 search/resolve）
- **不做**：串行循环查询多本书（必须用批量脚本）
- **不做**：猜测字段含义（以 `weread-skills` 的说明文件为准）
- **做**：缓存命中时直接返回（5min TTL）
- **做**：批量查询时合并进程
- **做**：错误码映射到可行动作
- **做**：网络波动时自动重试（3次指数退避+随机抖动）

---

## 性能基准

| 操作 | 耗时 | 说明 |
|------|------|------|
| 进程启动 | ~85ms | 每次调用固定开销 |
| search（缓存命中） | ~0.07s | 5min TTL |
| search（网络） | ~1s | 实际 API 请求 |
| 批量查询 5 本 | ~0.5s | `weread_batch.py info` |
| 批量搜索多关键词 | ~0.2s | `weread_batch.py search` |
| mirror quick | ~0.6s | 精简画像 |
| mirror standard | ~1.5s | 标准画像 |
| mirror deep | ~2.7s | 深度画像 |
| 推荐书 | ~1.3s | 含多关键词并行 |
| 推荐作者 | ~0.6s | 并行搜索 |

---

## 参考文档

| 文档 | 何时读取 |
|------|---------|
| `references/troubleshooting.md` | API 报错、字段语义 |
| `references/mirror-guide.md` | 阅读画像分析 |
| `references/readdata.md` | 跨周期统计 |
| `references/material-grading.md` | 提取写作素材 |
| `references/organize-guide.md` | 笔记数据收集 |
| `references/scope.md` | search scope 参数 |

---

## 下游路由

| 场景 | 路由 |
|------|------|
| 推荐/书单/笔记炼金/分析/教练/导出/复盘 | `advisor/SKILL.md` |
| 个人知识库生成（选题库/观点库/知识图谱） | `mine/SKILL.md` |

---

## 每日回顾

从已有缓存中随机挑一条划线推送，自动去重。**不发新 API 请求**，复用 `/tmp/weread_cache/` 中的数据。

### 命令

```bash
python3 ~/.agents/skills/taxue-weread/scripts/weread.py daily-review
python3 ~/.agents/skills/taxue-weread/scripts/weread.py daily-review --json
python3 ~/.agents/skills/taxue-weread/scripts/weread.py daily-review --notify
python3 ~/.agents/skills/taxue-weread/scripts/weread.py daily-review --reset
```

### 参数

| 参数 | 说明 |
|------|------|
| `--json` | 输出 JSON（LLM 解析用） |
| `--notify` | 同时发 macOS 系统通知 |
| `--reset` | 清空推送历史，重新开始 |

### 机制

- 从 `/tmp/weread_cache/` 中读取所有 `bookmarklist` 格式的缓存文件
- 按时间反向加权：越老的划线越可能被选中（激活遗忘内容）
- 推送历史存在 `~/.agents/skills/taxue-weread/state/review_history.jsonl`
- 全部划线推送完一轮后自动归档历史，开始新一轮

### 定时推送

```bash
# cron（每天早 8 点）
0 8 * * * python3 ~/.agents/skills/taxue-weread/scripts/weread.py daily-review --notify
```

---

*taxue-weread v1.7.0 · 原子操作层 · 直接、稳定、不绕弯*
