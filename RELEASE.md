# taxue-weread v1.5.0

> 基于微信读书官方 Skill 的 Agent 优化版——CLI + 缓存 + 合并命令，为 Agent 环境量身打造。

## 它是什么

微信读书官方提供了 API 规范和基础 SKILL.md（v1.0.3），设计目标是让 Agent 直接调 HTTP API。

本版本在官方规范基础上，封装了一个完整的 CLI 工具 + Agent 指令系统，让 Agent 能以最少的 token、最少的轮次、最高的可靠性完成微信读书的所有操作。

## 和官方版本 v1.0.3 的对比

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

## 实测数据

670 本书架，相同网络环境：

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

## 独有功能

### 1. resolve — 模糊书名 → 精确 bookId

用户说「帮我看看三体」，传统方式需要 search → book → notes 三轮串行调用。

`resolve` 一个命令搞定模糊匹配，按匹配度打分排序：

```bash
$WR resolve 三体
# 「三体」找到 10 本相关书：
# 1. 三体全集（全三册）  刘慈欣  神作 93%  9698人在读  [匹配度:4]  id:695233
# 2. 三体2·黑暗森林  刘慈欣  神作 93%  264人在读  [匹配度:3]  id:183526
# ...

$WR inspect 三体   # 直接用，内部自动 resolve
```

匹配度算法：标题精确匹配 +3，包含关键词 +2，高评分 +1，在读人数多 +1。

### 2. inspect — 一键查书

```bash
$WR inspect 三体
# 返回：书名 + 作者 + 评分 + 划线 + 想法，一次到位
```

### 3. api — 低层逃生口

当现有命令不满足需求时，直接调任意接口：

```bash
$WR api /store/search --param keyword=三体 --param scope=10 --param count=5
```

### 4. shelf --summary / --fields — 按需输出

```bash
$WR shelf --summary
# 429 chars：总本数、读完、在读、活跃、冷宫、分类 TOP5

$WR shelf --json --fields bookId,title,author,category,finishReading
# 去掉 cover 等冗余字段，省 58% tokens
```

### 5. 自动缓存 + 重试

```bash
# 第一次调用（网络请求）
$ time $WR shelf --json    # ~0.9s

# 第二次调用（缓存命中）
$ time $WR shelf --json    # ~0.07s  ← 13x 快

# 网络波动时自动重试 3 次，指数退避 + 随机抖动
```

### 6. 装饰性素材检测

整理笔记时，Agent 会检查每条内容是否真的在支撑论点：

> 「去掉它，论点还成立吗？成立 → 这是装饰，删掉。」

防止输出「看起来很多但没用的笔记整理」。

### 7. 素材 A/B/C 分级

从划线中提取写作素材时，自动分级：

- **A 级**：有具体人名/时间/数字，可直接引用
- **B 级**：有观点但缺细节，加工后可用
- **C 级**：太抽象，仅作思路参考

### 8. 沉睡划线诊断

划了但从未用过的内容 = 沉睡划线。Agent 会识别并提示：「你划了 X 条线但从未用过，这些是你的潜在资产。」

## 文件结构

```
taxue-weread/
├── SKILL.md                    # 59 行，意图路由 + 关键规则
├── scripts/
│   ├── weread.py                # CLI + 缓存 + 重试
│   └── test_weread.py           # 测试套件
└── references/                  # 按需加载，不浪费 context
    ├── troubleshooting.md       # 16 条 API 陷阱 + 条件返回字段表
    ├── mirror-guide.md          # 阅读画像分析 + 沉睡划线 + 感想词频
    ├── organize-guide.md        # 笔记整理框架 + 装饰性检测
    ├── material-grading.md      # 素材 A/B/C 分级 + 写作适用性判断
    ├── readdata.md              # 跨周期统计组合
    └── scope.md                 # scope 选择表
```

## SKILL.md 设计

官方 SKILL.md 是「全量加载」——每次触发都把 ~170 行塞进 context。

本版本改为「核心指令 + 按需加载」：

- SKILL.md 只保留 59 行核心内容（意图路由 + 关键规则 + 参考文档索引）
- 6 个 reference 文件按需读取，不浪费 context

实测：SKILL.md 加载从 ~1.1K tokens 降到 ~700 tokens（-36%）。

## 安装

### 方式一：npm 安装（推荐）

```bash
npm install -g taxue-weread

# 设置 API Key
export WEREAD_API_KEY=wrk-xxxxxxxx

# 使用
taxue-weread shelf --summary
twr resolve 三体 --count 5 --compact
```

### 方式二：手动复制

```bash
cp -r taxue-weread ~/.agents/skills/weread-skills
export WEREAD_API_KEY=wrk-xxxxxxxx
cd ~/.agents/skills/weread-skills/scripts
python3 weread.py shelf --summary
```

## 兼容性

- 完全兼容官方 API 规范（`https://i.weread.qq.com/api/agent/gateway`）
- 所有官方接口均可通过 `$WR list-apis` 或 `$WR api <path>` 调用
- API Key 格式：`wrk-xxxxxxxx`（与官方一致）
