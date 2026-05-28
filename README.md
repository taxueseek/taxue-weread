# taxue-weread

微信读书的 Agent 优化版。一个 CLI，把书架、搜书、笔记、统计、导出、推荐全干了。

## 安装

**Claude Code / Codex（推荐）：**

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

> API Key 获取：先登录[微信读书网页版](https://weread.qq.com)，然后访问 [WeRead Skill 官方页面](https://weread.qq.com/r/weread-skills) 复制。没登录网页版经常拿不到 key。

## 快速上手

```bash
# 书架一览（精简模式，670本也能一行看完）
WR shelf --summary

# 搜书 → 一键查书（书名+作者+评分+划线+想法，一步到位）
WR inspect 三体

# 阅读统计
WR readdata --mode monthly      # 本月
WR readdata --mode annually     # 今年

# 阅读画像（分析你的阅读习惯和偏好）
WR mirror --depth quick         # 快速版
WR mirror --depth deep          # 深度版

# 导出笔记（支持 md / json / csv / 精美HTML卡片）
WR export 695233 --format md --output 笔记.md
WR export 695233 --format card --output 笔记.html
WR export --all --output ~/笔记/   # 批量导出全部

# 精细化推荐
python3 scripts/weread_recommend.py books "投资 心理学"   # 推荐书
python3 scripts/weread_recommend.py authors "投资 思维"    # 推荐作者
python3 scripts/weread_recommend.py versions "思考快与慢"  # 版本对比
python3 scripts/weread_chapters.py 44026191 "财富积累"     # 推荐章节
```

## 几个好用的功能

### 🔍 一键查书

说「帮我看看三体」，不用先搜再查再翻笔记，`inspect` 一步到位：

```
书名：三体全集（全三册）
作者：刘慈欣  评分：93%
划线：47 条  想法：12 条  进度：100%
```

### 📊 书架精简输出

书架几百本书，全量输出太占 token。`--summary` 只看关键数字：

```
书架：670 本 | 读完 68 | 在读 12 | 活跃 45 | 冷宫 545
分类 TOP5：男生小说(185) 经济理财(37) 影视原著(5) 个人成长(5) 医学健康(4)
```

### 🪞 阅读画像

不只是列数据，会分析你的阅读习惯：

```
阅读人格：夜猫子型（90% 阅读发生在 22:00 之后）
完成率：23%（收藏多、读完少，选书可以更聚焦）
笔记密度：4.3 条/本（轻量型读者，划线为主、想法偏少）
```

深度模式还会找出「沉睡划线」——划了但从没用过的内容，提醒你别浪费。

### 📚 精细化推荐

不只是搜书，还能：
- **推荐书**：多关键词并行搜索，按评分×评价人数排序
- **推荐作者**：找跟你口味相近的作者
- **版本对比**：同一本书哪个译本/出版社更好
- **推荐章节**：语义匹配，找出最相关的章节

### 📤 多格式导出

支持 4 种格式：

| 格式 | 用途 |
|------|------|
| `md` | Markdown，适合阅读和编辑 |
| `json` | 结构化数据，适合程序处理 |
| `csv` | 表格，适合导入 Excel |
| `card` | 精美 HTML 卡片，适合分享 |

还能批量导出所有书的笔记：`WR export --all --output ~/笔记/`

### ⚡ 缓存 + 重试

重复查询自动走缓存，快 13 倍。网络波动自动重试 3 次，不用手动重试。

## 命令速查

| 命令 | 作用 |
|------|------|
| `WR inspect <书名>` | 一键查书 |
| `WR shelf --summary` | 书架精简统计 |
| `WR readdata --mode monthly` | 阅读统计 |
| `WR mirror --depth quick` | 阅读画像 |
| `WR export <id> --format md` | 导出笔记 |
| `WR export --all` | 批量导出全部 |
| `WR resolve <书名>` | 模糊书名匹配 |
| `WR book <id>` | 书籍详情 |
| `WR notes --book <id>` | 笔记/划线 |
| `WR organize` | 整理读书笔记 |
| `WR api <path>` | 直接调任意 API |

## 和官方版本的区别

| | taxue-weread | 官方版本 |
|---|---|---|
| 缓存 | ✅ 5min TTL，重复查询快 13x | 无 |
| 自动重试 | ✅ 3 次指数退避 | 无 |
| 模糊书名匹配 | ✅ 按匹配度打分 | 无 |
| 一键查书 | ✅ `inspect` 一步到位 | 需 3 轮调用 |
| 精细化推荐 | ✅ 书/作者/版本/章节 | 无 |
| 导出格式 | ✅ md/json/csv/card | 仅 md |
| 批量导出 | ✅ 一次导出全部 | 无 |
| 阅读画像 | ✅ 三档深度分析 | 无 |

## 致谢

基于微信读书官方 [WeRead Skill](https://weread.qq.com/r/weread-skills) 开发。API 接口和数据归微信读书所有。

## License

MIT
