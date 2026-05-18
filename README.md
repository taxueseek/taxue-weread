# taxue-weread

微信读书官方 Skill 的 Agent 优化版——用一个 CLI 把 API 调用、缓存、重试、分析全包了。

## 它能做什么

taxue-weread 帮你管理微信读书上的所有数据：查书架、搜书、看阅读进度、导出笔记、做阅读分析。它把微信读书的官方 API 包成了一个命令行工具，Agent 和人类都能用。

**核心能力：**
- 书架管理（支持精简输出，670 本书只显示一行摘要）
- 搜书 + 模糊书名匹配（说"三体"就能找到对应的书）
- 阅读统计（本周/本月/今年/全部历史）
- 笔记/划线/想法查看和导出（md/json/csv/html）
- 阅读画像分析（你的阅读习惯、偏好、盲区）
- 笔记智能整理（帮你从划线里提炼可用的写作素材）

## 和官方版本的区别

微信读书官方提供了一套 API 接口，但用起来比较原始：
- 查一次书架，几百本书全量返回，Agent context 直接爆炸
- 想看某本书的笔记，要先搜索获取 bookId，再调书籍接口，再调笔记接口，串行三轮
- 没有缓存，同一个命令反复调用每次都要等网络
- API 的语义陷阱很多（比如时长单位是秒、progress=1 表示 1% 不是 100%）

taxue-weread 解决这些问题：
- **精简输出**：`shelf --summary` 只输出 400 多字符，省 99% 的 token
- **合并命令**：`inspect 三体` 一步到位，不用串行调三轮
- **自动缓存**：5 分钟 TTL，重复调用快 13 倍
- **自动重试**：网络波动时自动重试 3 次，指数退避
- **语义处理**：CLI 自动转换时长单位、进度百分比、书架计数口径，Agent 不用记
- **智能分析**：`mirror` 做阅读画像，`organize` 做笔记整理，不是罗列数据，而是给洞察

## 安装

**需要：Node.js >= 18，Python 3**

**Claude Code / Codex 用户（推荐）：**

```bash
npx skills add taxueseek/taxue-weread
```

**npm 全局安装：**

```bash
npm install -g taxue-weread
```

**配置 API Key：**

```bash
export WEREAD_API_KEY=wrk-xxxxxxxx
```

API Key 获取方式：访问 [微信读书 Skill 官方页面](https://weread.qq.com/r/weread-skills)，登录后复制。

## 快速上手

```bash
# 书架一览（精简模式）
twr shelf --summary

# 搜书
twr resolve 三体

# 查看某本书详情 + 笔记
twr inspect 三体

# 本月阅读统计
twr readdata --mode monthly

# 年度阅读统计
twr readdata --mode annually

# 阅读画像
twr mirror --depth quick

# 整理读书笔记
twr organize --max-books 5

# 导出笔记为 markdown
twr export 695233 --format markdown --output 笔记.md
```

## 几个好用的独家功能

### 1. 书架精简输出

书架书多的时候，全量输出会让 Agent 的 context 窗口爆满。`--summary` 只输出最关键的数字：

```bash
$ twr shelf --summary
书架：670 本 | 读完 68 | 在读 12 | 活跃 45 | 冷宫 545
分类 TOP5：男生小说(185) 经济理财(37) 影视原著(5) 个人成长(5) 医学健康(4)
```

### 2. 一键查书

传统流程：search 获取 bookId -> book 查详情 -> notes 查笔记，三轮串行。

`inspect` 一步到位：

```bash
$ twr inspect 三体
书名：三体全集（全三册）
作者：刘慈欣  评分：93%
划线：47 条  想法：12 条  进度：100%
```

### 3. 阅读画像

不是展示原始数据，而是分析你的阅读习惯：

```bash
$ twr mirror --depth quick
阅读人格：夜猫子型（90% 阅读发生在 22:00 之后）
完成率：23%（收藏多、读完少，选书可以更聚焦）
笔记密度：4.3 条/本（轻量型读者，划线为主、想法偏少）
```

深度模式还会分析「沉睡划线」（划了但从来没用过的内容）、感想词频、阅读盲区等。

### 4. 笔记智能整理

把划线整理成可复用的写作素材，分三层：

1. 作者说了什么（提炼核心论点）
2. 你怎么看（你的判断和保留意见）
3. 能用来做什么（写作方向、可引用的案例）

自动检测「装饰性素材」——去掉它论点还成立的内容，建议删掉。

### 5. 缓存 + 自动重试

```bash
# 第一次
$ time twr shelf --json
0.92s

# 第二次（缓存命中）
$ time twr shelf --json
0.07s   # 13 倍快
```

网络不好的时候自动重试 3 次，不用手动处理。

## 命令速查

| 命令 | 作用 |
|------|------|
| `twr resolve <书名>` | 模糊书名解析 |
| `twr inspect <书名>` | 一键查书详情+笔记 |
| `twr book <bookId>` | 书籍详情/进度/章节 |
| `twr shelf` | 书架列表 |
| `twr shelf --summary` | 书架精简统计 |
| `twr readdata --mode monthly` | 阅读统计 |
| `twr notes --book <bookId>` | 笔记/划线/想法 |
| `twr mirror --depth quick` | 阅读画像 |
| `twr organize` | 整理读书笔记 |
| `twr export <bookId>` | 导出笔记 |
| `twr api <path>` | 直接调任意 API |

## 项目结构

```
taxue-weread/
├── SKILL.md              # Agent 意图路由（59 行，按需加载）
├── README.md             # 本文件
├── bin/
│   ├── taxue-weread.js   # CLI 入口（别名 twr）
│   └── check-python.js   # 安装环境检查
├── scripts/
│   ├── weread.py         # 核心 CLI（缓存/重试/并发）
│   └── test_weread.py    # 测试
└── references/           # 按需加载的参考文档
    ├── troubleshooting.md    # API 陷阱手册
    ├── mirror-guide.md       # 阅读画像分析指南
    ├── organize-guide.md     # 笔记整理框架
    ├── material-grading.md   # 素材分级标准
    ├── readdata.md           # 跨周期统计组合
    └── scope.md              # 搜索类型选择
```

SKILL.md 采用「核心指令 + 按需加载」的设计：主文件只有 59 行，6 个 reference 文件在 Agent 需要时才加载。实测比全量加载省 36% 的 token。

## 致谢

基于微信读书官方 [WeRead Skill](https://weread.qq.com/r/weread-skills) 开发。API 接口和数据归微信读书所有。

## License

MIT
