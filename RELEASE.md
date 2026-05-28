# taxue-weread Release Notes

## v1.7.0

> 同步上游 taxueseek/taxue-weread 仓库，版本从 v1.0.3 升至 v1.7.0。

### 架构调整

- **脚本结构扁平化**：移除 `core/`、`commands/`、`report/` 子目录，改为单文件 `weread.py`（1950 行），减少模块间依赖，降低维护成本
- **SKILL.md 重写**：版本号更新为 1.7.0，补全新增命令的路由信息

### 新增能力

| 能力 | 命令 | 说明 |
|------|------|------|
| 精细化推荐（书） | `weread_recommend.py books` | 多关键词并行搜索，按评分×评价人数排序 |
| 精细化推荐（作者） | `weread_recommend.py authors` | 推荐与用户口味相近的作者 |
| 精细化推荐（版本） | `weread_recommend.py versions` | 同一本书多版本对比，标注推荐 |
| 精细化推荐（相似书） | `weread_recommend.py similar` | 找相似书籍 |
| 精细化推荐（画像） | `weread_recommend.py profile` | 基于用户数据多维度推荐 |
| 章节推荐（关键词） | `weread_recommend.py chapters` | 关键词硬匹配章节 |
| 章节推荐（语义） | `weread_chapters.py` | 拉取目录+划线，生成 prompt 喂模型做语义匹配 |
| 批量并行搜索 | `weread_search.py` | 多本书名并行搜索，0.6秒/20本 |
| 模糊书名解析 | `WR resolve` | 按匹配度打分排序，替代裸 search |
| 一键查书 | `WR inspect` | 书名+作者+评分+划线+想法，一步到位 |
| 书架精简输出 | `WR shelf --summary` | 670本→一行摘要，省 99.8% tokens |
| 字段过滤 | `WR shelf --fields` | 指定输出字段，省 58% tokens |
| 书架分析 | `WR shelf-stats` | 读完率、活跃度、TBR |
| 阅读画像三档 | `WR mirror --depth quick/standard/deep` | 按需选择深度 |
| 批量导出 | `WR export --all` | 一次导出全部书籍笔记 |
| HTML卡片导出 | `WR export --format card` | 精美 HTML 卡片格式 |
| CSV/JSON导出 | `WR export --format csv/json` | 多格式支持 |
| 低层逃生口 | `WR api <path>` | 直接调任意接口 |
| 列出可用API | `WR list-apis` | 查看所有接口 |

### 性能优化

- **缓存**：5min TTL 文件级缓存，重复查询快 13x（~0.07s vs ~1s）
- **自动重试**：3 次指数退避 + 随机抖动
- **并发调用**：ThreadPoolExecutor 替代串行，5-6x 提速
- **线程安全**：缓存写入加锁（threading.Lock）

### 和官方 v1.0.3 的对比

| 维度 | 官方 v1.0.3 | taxue-weread v1.7.0 |
|------|------------|-------------------|
| 交互方式 | Agent 直接调 HTTP API | CLI 封装 |
| 缓存 | 无 | ✅ 5min TTL，快 13x |
| 自动重试 | 无 | ✅ 3 次指数退避 |
| 模糊书名解析 | 无 | ✅ `resolve` + `inspect` |
| 精细化推荐 | 无 | ✅ 书/作者/版本/章节/画像 |
| 导出格式 | 无 | ✅ md/json/csv/card |
| 批量导出 | 无 | ✅ `export --all` |
| 阅读画像 | 无 | ✅ 三档深度 |
| 低层逃生口 | 无 | ✅ `api` 命令 |
| 并发调用 | 串行 | ✅ ThreadPoolExecutor |
| 命令数 | 11 | 20+ |

---

## v1.5.0（历史版本）

> 基于微信读书官方 Skill 的 Agent 优化版——CLI + 缓存 + 合并命令，为 Agent 环境量身打造。

### 和官方 v1.0.3 的主要差异

| 维度 | 官方 v1.0.3 | taxue-weread v1.5.0 |
|------|------------|-------------------|
| 交互方式 | Agent 直接调 HTTP API | CLI 封装，Agent 调命令 |
| 缓存 | 无 | ✅ 文件级 TTL=5min，重复调用快 13x |
| 自动重试 | 无 | ✅ 3 次指数退避 + 随机抖动 |
| API 陷阱 | 散落在各 reference | ✅ 集中 16 条 + 条件返回字段表 |
| 模糊书名解析 | 无 | ✅ `resolve` 命令，按匹配度打分排序 |
| 低层逃生口 | 无 | ✅ `api` 命令，直接调任意接口 |
| 命令数 | 11 个原子命令 | 20 个（含合并命令） |
| "查三体笔记" | 3 轮 API 调用 | ✅ 1 轮 `inspect` |
| 书架统计 | 全量返回 | ✅ `--summary` 省 99.8% tokens |
| SKILL.md | ~170 行全量加载 | ✅ 59 行 + 按需加载 references |
| 字段过滤 | 无 | ✅ `--fields` 指定输出字段 |
| 导出功能 | 无 | ✅ md/json/csv/html 四种格式 |

### 实测数据（670 本书架）

| 场景 | 官方方式 | taxue-weread | 提升 |
|------|---------|-------------|------|
| shelf 统计 | 全量 239K chars | --summary **429 chars** | token -99.8% |
| 重复调用 | 每次 ~1s | 缓存命中 **0.07s** | 13x |
| "看三体笔记" | 3 轮 API | **1 轮** | 轮次 -67% |
| mirror quick | 3.5s | **0.62s** | **5.6x** |
| mirror standard | 4.6s | **1.46s** | **3.1x** |
| inspect（任意书） | ~1.5s | **1.3-1.6s** | 持平 |
| 并发 API 调用 | ❌ 串行 | ✅ ThreadPoolExecutor | **5-6x** |
| 缓存安全 | ❌ 无锁 | ✅ threading.Lock | 线程安全 |

### 独有功能（v1.5.0）

1. **resolve** — 模糊书名 → 精确 bookId，按匹配度打分
2. **inspect** — 一键查书，书名+作者+评分+划线+想法
3. **api** — 低层逃生口，直接调任意接口
4. **shelf --summary / --fields** — 按需输出
5. **自动缓存 + 重试** — 5min TTL + 3 次重试
6. **装饰性素材检测** — 去掉论点成立的多余内容
7. **素材 A/B/C 分级** — 按可引用性自动分级
8. **沉睡划线诊断** — 找出划了但从没用过的内容

### 兼容性

- 完全兼容官方 API 规范（`https://i.weread.qq.com/api/agent/gateway`）
- 所有官方接口均可通过 `$WR list-apis` 或 `$WR api <path>` 调用
- API Key 格式：`wrk-xxxxxxxx`（与官方一致）
