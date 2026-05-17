# 故障排查 & API 陷阱手册

## 运行时故障

| 问题 | 处理 |
|------|------|
| `WEREAD_API_KEY` 未设置 | `export WEREAD_API_KEY=<你的key>` |
| `errcode != 0` | CLI 自动输出中文错误信息 |
| `upgrade_info` | CLI 检测并暂停（exit code 2），按指引升级后重试 |
| 网络波动 | CLI 自动重试 3 次（2s/4s/8s 指数退避 + 抖动） |

## API 语义陷阱（不可推断，必须记住）

调用任何命令前确认：

1. **时长单位**：所有时长字段单位是**秒**。展示转「X 小时 Y 分钟」。
2. **阅读进度**：`progress` 是 0-100 整数，1=1%（非 100%）。仅 progress=100 且 `finishTime` 存在才算读完。
3. **时段偏移**：`preferTime` 数组从 **06:00** 开始到次日 05:00（24 个值），不是 00:00。
4. **日均分母**：`dayAverageReadTime` 分母 = 周期已过去的自然日数，不是 `readDays`。阅读日均 = `totalReadTime / readDays`。
5. **评分转换**：`newRating` 是 0-1000 刻度，展示时除以 10（如 930 → 93%）。
6. **作者时长格式**：`preferAuthor[].readTime` 是格式化字符串（如「5 小时 30 分钟」），不是秒数。
7. **书架计数**：总数 = `books.length + albums.length + (mp 非空 ? 1 : 0)`。**禁用服务端 `bookCount` 字段**。
8. **mode 必传**：`readdata` 的 `mode` 必须显式传（weekly/monthly/annually/overall），不传报错。
9. **annually 限制**：只返回 `baseTime` 所在自然年。当前年份数据为年初至今，不得标为全年。
10. **文字阅读占比**：`readRate` 仅当总时长满 1 小时且文字占比未过高时返回，否则为 null。
11. **compare 条件**：仅当「当前周期 + 上一周期数据足够」时返回，缺失属正常。
12. **搜索 → bookId**：用户输入书名时，先 `search` 获取 `bookId`，再执行后续操作。记住 bookId 避免重复查询。
13. **时间戳展示**：Unix 时间戳展示为 `YYYY-MM-DD` 格式，不得直接展示原始数字。
14. **my-reviews 参数**：参数名是 `bookid`（小写 i），不是 `bookId`。
15. **preferPublisher 条件**：至少 3 个出版社且最高本数达阈值才返回，缺失属正常。
16. **preferTimeWord 条件**：总偏好时段数据满 10h 才返回，缺失属正常。

## 条件返回字段（缺失属正常）

| 字段 | 返回条件 |
|------|---------|
| compare | 当前周期且上一周期数据足够 |
| preferAuthor | 作者数据达到展示阈值 |
| preferPublisher | 至少 3 个出版社且最高本数达阈值 |
| readRate/wrReadTime/wrListenTime | 总时长满 1h 且文字占比未过高 |
| rank | 仅当前周且未隐藏排行 |
| preferTimeWord | 总偏好时段数据满 10h |
| dailyReadTimes | annually 模式可能返回 |

## 跨周期查询算法

接口只支持固定自然周期：
1. 整年用 annually，整月用 monthly，减少调用次数
2. 跨年按自然年逐年查询累加
3. 完整周期取 `totalReadTime`；不完整边界用 `dailyReadTimes` 日级扣减
4. 无日级明细时用月级近似，回答中标注口径

## baseTime 归一化

weekly → 周一 00:00 | monthly → 1日 00:00 | annually → 1月1日 00:00 | overall → 0

## 笔记接口层级

| 粒度 | 命令 | 说明 |
|------|------|------|
| 书籍级（概览） | `notebooks` | 有笔记的书列表 + 各书笔记数 |
| 书籍级（全部划线） | `bookmarks` | 单本书所有划线 |
| 书籍级（热门划线） | `best-bookmarks` | 热门划线 TOP20，**固定返回不支持分页** |
| 章节级（划线热度） | `underlines` | 某章节各位置的划线人数统计 |
| 章节级（划线下想法） | `read-reviews` | 某章节特定划线位置下的用户想法 |
| 个人级（我的想法） | `my-reviews` | 单本书我的所有想法与点评 |

- `read-reviews` 入参 `reviews` 格式：`[{"range":"900-2004","count":10}]`，从 `underlines` 获取 range

## 临时脚本（不覆盖 CLI 时）

```bash
cd scripts && python3 -c "
import json, os
os.environ['WEREAD_API_KEY'] = 'your-key'
from weread import WereadAPI
api = WereadAPI()
result = api.call('/some/api', param='value')
print(json.dumps(result, indent=2, ensure_ascii=False))
"
```
