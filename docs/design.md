# SuumoViz 设计文档

> 基线日期：2026-11-07。第 2 节的来源事实均为当日实测结果。
> 仓库：2026-11-19 起采集与网页合并为一个公开仓库 `Imanity/suumoviz`（第 5.2、9、10 节）；
> 此前的私有仓库 `Imanity/suumoviz-data` 停止使用。

## 1. 总体结构

```text
公开仓库 Imanity/suumoviz
  main 分支：代码（Python 包 + web/）       data 分支：编码后的 CSV 表（只由 workflow 写入）

GitHub Actions「Daily crawl」（每天日本时间 03:17）
  └─ suumoviz daily
       1. 检查冷却标记，冷却中直接退出
       2. 读取 robots.txt，确认目标路径仍被允许
       3. 抓 4 个区汇总页 → 各“区 × 类别”件数 → 页数
       4. 按 7 天轮转选出今天的约 100 个列表页，每 5 秒抓 1 页
       5. 解析 → 质量检查 → 合并到状态表、生成事件和统计（写出时逐行编码）
  └─ 把 data/ 提交到 data 分支
  └─ 调用「Pages」：suumoviz build（按日期、按区域的统计 data/*.dat）→ vite build → 发布 GitHub Pages
浏览器
  └─ 读取同站点的 geo/areas.json（区域边界）和 data/*.dat（解码），画分区着色地图、时间轴和走势
```

代码包结构（随步骤增加）：

```text
src/suumoviz/
  categories.py      类别配置与 URL 生成
  models.py          Area / Listing / ListPage 数据类
  parse/normalize.py 文本规范化（价格、面积、交通、年月）
  parse/city.py      区汇总页解析
  parse/listing.py   列表页解析
  robots.py          robots.txt 匹配（支持通配符）（步骤 2）
  fetch.py           限速 HTTP 客户端与停机规则（步骤 2）
  rotation.py        轮转分配（步骤 2）
  state.py           state.json：偏移量、冷却、robots 摘要（步骤 2）
  crawl.py           一次运行的编排与当天快照（步骤 2）
  cli.py             命令行入口（步骤 2）
  codec.py           数据文件的编码混淆（步骤 8）
  store.py           data/ 下各 CSV 表的读写（步骤 3）
  quality.py         质量门槛（步骤 3）
  merge.py           合并、事件、下架判定、统计（步骤 3）
  geocode.py         地址 → 町丁目代表点（步骤 5）
  geodata/           国交省位置参照情報（东京都町丁目，精简 CSV，附 e-Stat 区域代码）（步骤 5、9）
  build.py           给 Web 的按日期、按区域统计（步骤 5；步骤 8 改为区域汇总；步骤 9 改为三级区域 + 时间轴）
tools/make_boundaries.py  e-Stat 小地域边界 → web/public/geo/areas.json（步骤 9）
web/                 网页（步骤 6；步骤 8 简化；步骤 9 改为分区着色、时间轴、走势）
```

## 2. 来源事实（2026-11-07 实测）

### 2.1 类别与 URL

| 类别键 | 名称 | 路径 | 东京总数 | 有房源的区市町村 | 全量页数 |
|---|---|---|---|---|---|
| `used_condo` | 中古マンション | `ms/chuko` | 36,894 | 49 | 394 |
| `new_condo` | 新築マンション | `ms/shinchiku` | 880 | 43 | 45 |
| `new_house` | 新築一戸建て | `ikkodate` | 12,023 | 50 | 144 |
| `used_house` | 中古一戸建て | `chukoikkodate` | 8,518 | 51 | 115 |
| 合计 | | | 58,315 | 193 个组合 | 698 |

- 区汇总页：`https://suumo.jp/{路径}/tokyo/city/`，列出每个区市町村的代码（如 `13112`）和件数；
- 区列表页：`https://suumo.jp/{路径}/tokyo/{区URL名}/?page={n}&pc=100&po=3&pj=1`，第 1 页省略 `page`；
- 区 URL 名（如 `sc_setagaya`）从汇总页链接取得：二手/一户建页面里是 `<a href=".../sc_setagaya/" id="js-linkSc112">`，新築マンション页面里是复选框标签内的链接；
- 每页最多 100 件（`pc=200` 被忽略，退回默认 20 件）；
- 排序参数：地址升序 `po=3&pj=1`，新着・更新順 `po=1&pj=2`（不使用，组内并非按时间排序）；
- 新築マンション没有地址排序选项，使用默认排序。

### 2.2 robots.txt 约束（`User-agent: *`）

- 禁止：`/jj/bukken/ichiran/JJ010FJ001/`（全东京列表）、`/jj/bukken/ichiran/JJ012FC001/`、`/jj/bukken/ichiran/JJ012FC003/`、`/jj/bukken/shiryou/...` 等；
- 禁止含 `sort=` 的查询；本项目使用的 `page`、`pc`、`po`、`pj` 均不受影响；
- `/ms/chuko/`、`/ms/shinchiku/{区}/`、`/ikkodate/tokyo/`、`/chukoikkodate/` 下的区列表与汇总页均未被禁止；
- 无 `Crawl-delay`（仅 bingbot 有 30 秒）。

每次运行前重新读取 robots.txt，用标准解析器确认本次要访问的 URL 全部允许，否则停止。

### 2.3 页面结构

| 页面 | 关键结构 |
|---|---|
| 二手/一户建列表 | 每条为 `div.property_unit`；字段为 `dt`/`dd` 对；标题链接 `h2.property_unit-title a` 含 `nc_{ID}`；标记 `span.ui-label--cta4`（新着、価格更新）；总件数 `div.pagination_set-hit` |
| 新築マンション列表 | 每条为 `div.cassette`（`li.cassette_list-item` 内）；标题 `a.cassette_header-title`；`p.cassette_basic-title`/`p.cassette_basic-value` 对（所在地、交通、引渡時期）；价格 `div.cassette_price-value`；户型与面积 `p.cassette_price-description`；总件数 `div.hitbox-number` |
| 区汇总页 | `input[name=sc]` 的 `value` 为区代码，紧随的 `label` 文本为“名称(件数)” |

各类别列表页的字段：

| 字段 | 中古マンション | 新築マンション | 新築一戸建て | 中古一戸建て |
|---|---|---|---|---|
| 名称 | 物件名 | 标题 | 物件名（约一半有） | 物件名（少数有） |
| 价格 | 販売価格 | 价格区间/未定 | 販売価格（可为区间） | 販売価格 |
| 地址 | 所在地 | 所在地 | 所在地 | 所在地 |
| 交通 | 沿線・駅 | 交通 | 沿線・駅 | 沿線・駅 |
| 面积 | 専有面積 | 专有面积区间 | 建物面積（可为区间） | 建物面積 |
| 土地 | — | — | 土地面積 | 土地面積 |
| 间取 | 間取り | 间取区间 | 間取り | 間取り |
| 其他 | バルコニー、築年月 | 引渡時期 | — | 築年月 |

解析约定与实测观察（以 2026-11-07 的完整页面为准）：

- 值为 `-` 的单元格视为空值（如阳台、土地类房源的建物面積和間取り）；
- 面积只取 `、` 之前的部分，`、うち1階車庫12.11m2`、`、路地状部分:20.75m2含` 之类的附注忽略；`~` 和 `・` 分隔的是区间或多个户型，取最小值和最大值；
- 价格 `円台` 取下限，`未定`/`価格未定` 为空；
- 新築一戸建て中混有土地类房源（如“○○ 土地”“更地”），建物面積和間取り为 `-`：世田谷样本中占 24%。统计单价时要排除这类房源；
- 实测解析率：中古マンション价格/面积/地址 100%；新築マンション价格 97%（其余为“価格未定”）；新築一戸建て价格 96%（其余为“未定”）、建物面積 76%（其余为土地类）；中古一戸建て价格/面积/土地 100%。

## 3. 抓取规则（步骤 2）

- 单连接，相邻两次请求开始时间至少间隔 5 秒（命令行不允许设得更短）；
- User-Agent：`Mozilla/5.0 (compatible; SuumoViz/0.1.0)`，表明爬虫身份，不含联系方式（用户决定）；
- 不带 Cookie，不执行 JavaScript，不跟随重定向，接受 gzip；不访问详情页、资料请求、登录、地图、API；
- 超时 30 秒；5xx 和网络错误最多重试 2 次（间隔 30 秒、60 秒），其他 4xx 不重试；
- robots.txt 用自带的匹配器解析（支持 `*`、`$` 和最长匹配优先）；标准库 `urllib.robotparser` 不支持通配符，会漏掉 `/*?*sort=` 这类规则；
- 遇到以下情况立即停止整轮，并写入冷却标记：
  - HTTP 401、403、429（有 `Retry-After` 时取较长者）；
  - 页面含验证码或挑战特征（`captcha`、`recaptcha`、`access denied`、`unusual traffic`、`ロボットではない`、`アクセスが集中`）；
  - robots.txt 不允许汇总页或今天计划中的任一列表页；
- 冷却时长：首次 24 小时，7 天内再次触发 72 小时；冷却中的运行直接退出、不发请求；冷却需要提前解除时，手动删除 `state.json` 中的 `cooldown_until`；
- 单页失败（重试后仍失败、非 200、页面结构无法识别）记为该页错误并继续；连续 3 页失败则停止本轮；
- 一次运行的请求上限 150 个，运行时长上限 30 分钟。

### 3.1 命令

```text
suumoviz crawl                         抓今天（日本时间）槽位的全部页面
suumoviz crawl --max-pages 5           只抓前 5 个列表页（试运行）
suumoviz crawl --dry-run               只抓 robots.txt 和 4 个汇总页（5 个请求），打印今天的计划
suumoviz crawl --dry-run --city-html DIR   用本地保存的汇总页，完全不联网
suumoviz merge [--date D]              把 work/D/ 合并进 data/（步骤 3）
suumoviz daily                         crawl + merge，GitHub Actions 每天调用这一条
其他参数：--date YYYY-MM-DD  --categories a,b  --data-dir data  --work-dir work  --interval 秒(≥5)
```

退出码：`0` 完成 / 按 `--max-pages` 截断 / 冷却中跳过 / dry-run；`1` 部分页面失败或无法生成计划；`2` 被拦截（已进入冷却）。`merge` 在质量门槛不通过或日期倒序时返回 `1`；`daily` 取两者中较大的值。GitHub Actions 中非 0 即发失败通知。

### 3.2 当天快照

每次运行把结果写到 `work/{日期}/`（不提交，供步骤 3 合并；在 Actions 中作为 artifact 保留 7 天）。
三个 CSV 和 `data/` 一样逐行编码（见 5.2），`run.json` 为明文：

| 文件 | 内容 |
|---|---|
| `counts.csv` | 全部区市町村 × 类别的件数（含 0 件），来自汇总页 |
| `pages.csv` | 每个计划页：URL、状态（ok/error/blocked）、错误原因、汇总页件数、页头件数、解析条数、时间 |
| `listings.csv` | 当天解析出的全部房源（带区代码、页号） |
| `run.json` | 槽位、状态、停止原因、请求数、计划/成功/失败页数、房源条数、robots.txt 摘要 |

日志只输出“类别 区代码 页号：条数”，不输出房源内容。

## 4. 7 天轮转（步骤 2）

### 4.1 定义

- **组合**：一个“区 × 类别”，如 `(used_condo, 13112)`；
- **页数** `p = ceil(件数 / 100)`，件数来自当天的区汇总页；
- **今天的槽位** `slot = (日本时间日期 − 2026-11-02).days mod 7`（周一为 0）；
- **偏移量** `offset ∈ 0..6`，每个组合一个，首次出现时分配给当前负载最低的槽位，之后固定不变，保存在 `state.json`；
- **页的归属**：第 `i` 页（从 1 开始）在 `(i − 1 + offset) mod 7 == slot` 的那天抓取；
- **例外**：新築マンション没有地址排序，同一组合的所有页安排在同一天（`offset` 那天）抓取，避免默认排序变化造成跨天漏看（当前只有中央区、港区为 2 页）。

### 4.2 当前负载（按 2026-11-07 件数模拟）

- 每天 99–100 个列表页，加上 robots.txt 和 4 个汇总页，共约 105 个请求，约 10 分钟；
- 29 个组合（7 页以上）每天都有约 1/7 的抽样，覆盖 63% 的房源。例如世田谷中古マンション每天约 315 件；
- 页数少于 7 的组合每 7 天中有 `p` 天有数据，只有 1 页的组合每 7 天更新一次；
- 每 7 天完成一次全量普查。

### 4.3 地址排序的作用

按地址排序时，每页大致对应一片相邻的町丁目；按页号对 7 取余分配，等于每天在全区均匀抽取若干片区，各区数据天然具有地理代表性。地址顺序也比价格、新着顺序稳定，页边界漂移只影响少量边界房源。

## 5. 数据模型（步骤 3）

全部为 UTF-8 CSV（LF 换行），保存在 `data` 分支，代码在 `main` 分支。行按固定顺序写出，便于按天看差异。
文件名和列不变，但磁盘上的内容是编码后的（见 5.2）；`state.json` 为明文。

| 文件 | 内容 | 主键 |
|---|---|---|
| `listings/{category}.csv` | 每套房源的当前状态，按 `listing_id` 排序 | `listing_id` |
| `events/{YYYY-MM}.csv` | 新挂牌、调价、下架、重新上架 | 日期 + `listing_id` + 类型 |
| `counts/{YYYY}.csv` | 每天每个组合的在售件数（来自汇总页，含 0 件） | 日期 + 类别 + 区代码 |
| `stats/{YYYY}.csv` | 每天每个组合的抽样统计与全量统计 | 日期 + 范围 + 类别 + 区代码 |
| `archive/{YYYY}.csv` | 下架超过 90 天、从 `listings` 移出的房源（步骤 9） | 类别 + `listing_id` + 下架日 |
| `runs.csv` | 每天一行：槽位、状态、请求数、页数、是否合并、质量结果、各类事件数 | 日期 |
| `state.json` | 轮转偏移量、冷却截止时间、robots.txt 摘要（步骤 2） | — |

字段：

- `listings`：`listing_id, category, area_code, name, price_min, price_max, price_raw, address, line, station, walk_min, access_raw, area_min, area_max, land_min, land_max, layout, balcony, built_ym, delivery_raw, path, first_seen, last_seen, last_price_change, status, delisted_on`；`path` 是详情页路径（如 `/ms/chuko/tokyo/sc_setagaya/nc_123/`，步骤 5 加入，旧行在下次被抓到时补上）。新築一戸建て的列表里混有土地，这些房源的路径是 `/tochi/…`；
- `events`：`date, category, area_code, listing_id, type, price_min_old, price_max_old, price_min, price_max`（`new` 只有新价格，`delisted` 只有旧价格）；
- `stats`：`date, scope, category, area_code, n, price_p25, price_median, price_p75, unit_n, unit_price_median`；`area_code=13000` 为全东京汇总行（步骤 5 加入）；
- `runs`：`date, slot, status, stop_reason, requests, planned_pages, fetched_pages, failed_pages, listings, merged, quality, new, price_changes, delisted, relisted`；
- `archive`：`listing_id, category, area_code, address, price_min, price_max, area_min, area_max, first_seen, last_seen, delisted_on`。

下架超过 90 天的房源从 `listings` 移到 `archive/{移出年份}.csv`，只保留历史统计需要的列（价格变化在 `events` 中）。
这样网页的历史走势不会因为删除旧房源而变化（第 10.3 节）。按每天约 1,300 套下架估算，每年约增加 60MB（编码后）。

### 5.2 编码混淆（步骤 8，`codec.py`）

仓库公开后，`data` 分支、Actions artifact 和测试样本都能被任何人下载。为了不让采集到的内容被直接阅读、
搜索或收录，这些文件按行编码：

```text
#suumoviz-obf/1                       第 1 行：格式标记
base64(第 1 行原文 XOR KEY)            之后每行对应原文一行；KEY 每行从头开始
base64(第 2 行原文 XOR KEY)
...
```

- `KEY = sha256("suumoviz/obf/1")`（32 字节），写在 `codec.py` 和 `web/src/codec.ts` 中。**这是混淆，不是加密**，
  任何人用 `suumoviz decode FILE` 或读代码都能还原；
- 按行编码：未变化的行编码结果不变，`data` 分支每天的 git 差异与明文 CSV 一样只涉及变化的行；
  base64 使文件比明文大约三分之一（2026-11-18 的全部表格：明文 23MB → 编码后 31MB）。
  用 11-17、11-18 两天实测 git 压缩后的存储：明文首日 4.4MB、次日增加 0.18MB；编码后首日 12.1MB、
  次日增加 0.37MB（约每年 140MB），在 GitHub 仓库的建议大小内；
- 无损：任意字节都能还原（含 `\r`、空行、末尾换行）；检出时被转换成 CRLF 也能解码；
- 读取时按第 1 行自动识别，明文文件照常可读（迁移旧数据时用），写入一律编码；
- 不选 SQLite：每天一个新的二进制文件，git 无法做行级差异，`data` 分支每年会增长数 GB。

范围：`data/` 下全部 CSV（含 `runs.csv`）、`work/{日期}/` 下的 CSV、`tests/fixtures/suumo/` 下的页面样本、
网页数据 `data/*.dat`。明文：`state.json`、`run.json`（只有运行状态和计数）。

### 5.1 合并规则

- `suumoviz merge --date D` 把 `work/D/` 合并进 `data/`；`suumoviz daily` = 抓取 + 合并；
- 只合并状态为 `ok` 的页面；同一房源当天出现在两页（页边界漂移）时取后一次；
- **幂等**：同一天重复合并，所有文件不变；
- **不倒序**：比已合并的最新日期更早的日期拒绝合并；
- 质量门槛不通过时，房源、事件、统计都不写入，只记录 `runs.csv`（`merged=false` 和原因）和 `counts`。

## 6. 状态判定（步骤 3）

| 事件 | 条件 |
|---|---|
| 新挂牌 `new` | 首次出现的 `listing_id`（类别 + ID 唯一） |
| 调价 `price_change` | `price_min` 或 `price_max` 与上次不同（含“未定”↔有价格），记录旧值、新值 |
| 下架 `delisted` | 距最后一次出现 ≥ 15 天，且这期间（不含最后出现当天，含今天）`status=completed` 并已合并的运行 ≥ 13 次 |
| 重新上架 `relisted` | 已下架的房源再次出现 |

部分失败、被拦截、按 `--max-pages` 截断的运行不计入“成功运行”，避免把“没抓到”误判为“已下架”。

## 7. 统计口径（步骤 3）

- **件数**：每天来自汇总页，精确值，覆盖全部组合（包括 0 件）；
- **抽样统计** `scope=sample`：当天抓到的房源按组合统计；
- **全量统计** `scope=census`：当时全部 `active` 房源（即最近一个周期内见过的）按组合统计，正式趋势以此为准；第一个 7 天周期结束前覆盖不完整；
- 两种范围都额外输出每个类别的全东京汇总行（`area_code=13000`），全东京件数则由各区件数相加；
- 统计项：条数 `n`；价格（`price_min`）的 P25、中位数、P75（四分位用 inclusive 方法）；单价中位数（价格 ÷ 面积；マンション用専有面積，一戸建て用建物面積，均取区间下限；建物面積为空的土地类房源不计入；新築マンション不统计单价）；
- 抽样统计每 7 天循环一次同一组片区，单日数字可能有周期性波动，只作预览。

## 8. 质量门槛（步骤 3）

满足以下全部条件才合并当天数据：

- 至少有 1 个页面抓取成功；
- 每个成功页面都能解析出页头件数，且与汇总页件数相差不超过 max(5 件, 5%)；
- 每页实际条数应为 `min(100, 页头件数 − (页号 − 1) × 100)`，不符的页面不超过 max(1, 成功页数 × 5%)；
- 某类别当天条目 ≥ 20 条时，再检查该类别：价格原文、地址非空率 100%；价格原文不含“未定”的条目 `price_min` 可解析率 ≥ 99%；マンション两类専有面積、一戸建て两类土地面积可解析率 ≥ 95%（建物面積因混有土地类房源，不设门槛）。

## 9. 运行环境与成本（步骤 4）

- 公开仓库 `Imanity/suumoviz`，GitHub 托管 `ubuntu-latest`（公开仓库的标准 runner 不计用时）；
- 每次采集约 9–10 分钟（2026-11-08 起私有仓库实测），加上 Pages 构建约 2 分钟；
- `data` 分支每天提交一次；数据量约 6 万行，每天变化约 1 万行，按文本差异存储（编码按行进行，不影响差异大小）；
- 不需要任何 secret（推送 `data` 分支和发布 Pages 用 workflow 自带的 `GITHUB_TOKEN`）；日志中不打印房源内容；
- 公开仓库的 Actions 日志、artifact 任何人可见：日志只有“类别 区代码 页号：条数”，artifact 中的表格已编码。

### 9.1 Workflow

| 文件 | 触发 | 作用 |
|---|---|---|
| `.github/workflows/daily.yml` | 每天 UTC 18:17（日本时间 03:17）；也可手动触发，可填 `max_pages` | 检出 `main` 和 `data`（到 `./data`）→ `suumoviz daily` → 提交 `data/` 到 `data` 分支 → 上传 `work/` 为 artifact（7 天）→ 退出码非 0 时让任务失败（GitHub 邮件通知）→ 无论成败调用 `pages.yml` |
| `.github/workflows/pages.yml` | push 到 `main`、手动、被 `daily.yml` 调用 | 检出 `data` → `suumoviz build` 生成 `web/public/data/` → `npm test`、`npm run build` → 检查 `dist/` 只有页面、区域边界和编码后的统计 → 发布 GitHub Pages |
| `.github/workflows/canary.yml` | 仅手动 | 在 GitHub runner 上抓 robots.txt、4 个汇总页、1 个列表页（6 个请求），用临时目录，不提交 |
| `.github/workflows/ci.yml` | push 到 `main`、PR | Python：ruff + pytest；web：vitest + 构建 |

要点：

- `data` 分支只由 workflow 写入；即使抓取失败或被拦截也会提交，确保冷却状态（`state.json`）被保存；
- `concurrency: daily-crawl` 保证同一时间只有一个每日任务；Pages 发布用 `pages-deploy` 组排队；
- workflow 用 `GITHUB_TOKEN` 推送的提交不会触发其他 workflow，所以由 `daily.yml` 直接调用 `pages.yml`；
- 冷却中的运行不发请求、没有数据变化、不提交（Pages 照常重建，内容不变）；
- GitHub 的定时任务经常延迟数小时（2026-11-08 至 11-18 实际开始时间为日本时间 07:00–11:00），偶尔会被跳过；
  跳过的那天该槽位的页面要到下一个周期才会被抓；
- 公开仓库 60 天没有活动时，GitHub 会停用定时 workflow；每天的 `data` 提交算作活动。

### 9.2 从私有仓库迁移（步骤 8，一次性）

1. 在 `Imanity/suumoviz-data` 停用 Daily crawl（`gh workflow disable`），确保不会两边同时抓取；
2. 把私有仓库 `data` 分支的历史逐个提交重放到公开仓库的 `data` 分支：每个提交的 CSV 都编码，作者、时间、
   提交说明不变，逐个文件校验解码后与原内容一致（2026-11-19：16 个提交 + 1 个 README 提交，101 个数据文件版本
   全部为编码格式）；私有仓库中的明文历史不会进入公开仓库；
3. 合并代码到公开仓库 `main`，Pages workflow 自动发布；第二天起由公开仓库的 Daily crawl 继续采集。
   `state.json` 原样带过来，轮转偏移量和冷却状态不变。

### 9.3 运维操作

| 场景 | 做法 |
|---|---|
| 想先确认 GitHub runner 能访问 SUUMO | Actions → Canary → Run workflow |
| 想手动补跑当天 | Actions → Daily crawl → Run workflow（`max_pages` 留空）；同一天重跑会覆盖当天的运行记录，合并是幂等的 |
| 被拦截后提前解除冷却 | 在 `data` 分支编辑 `state.json`，把 `cooldown_until` 改为 `null` 并提交；建议先跑一次 Canary |
| 解析失败（质量门槛不过） | 下载当天 artifact 中的 `work/`，用 `suumoviz decode work/{日期}/pages.csv` 查看各页状态，对照页面更新解析器和 fixture；修好后手动补跑当天 |
| 查看某张表 | `suumoviz decode data/listings/used_condo.csv`（明文输出到标准输出） |
| 改了 `build.py` 或网页 | 推送到 `main` 即重新发布；也可 Actions → Pages → Run workflow |

## 10. 地理编码与 Web（步骤 5、6）

### 10.1 坐标来源

- 国交省“大字・町丁目レベル位置参照情報”东京都 令和 7 年（19.0b，`13000-19.0b.zip`，5,390 个町丁目代表点）；
- `tools/make_chome.py` 把原始 zip（Shift_JIS）转成 `src/suumoviz/geodata/tokyo_chome.csv`（UTF-8，约 370KB），随包发布；
- 使用条件：免费；转载或发布加工成果时注明“大字・町丁目位置参照情報 国土交通省”、整备年和文件名（`index.dat` 的 `sources.geo` 已写明）。

区域边界（步骤 9）：

- e-Stat「国勢調査 2020年 小地域（町丁・字等別）境界データ」东京都（`A002005212020DDSWC13-JGD2011.zip`，
  世界测地系经纬度 Shapefile，6,021 个多边形），2026-11-19 下载；使用条件为政府标准利用规约（注明出处即可）；
- `tools/make_boundaries.py`（用 mapshaper 0.8.5，一次性工具，不进依赖）：去掉水面（HCODE 8154）和所属未定地（199），
  简化（8m，约为缩放 15 级的 2 像素），按代码合并成三级，输出一份 TopoJSON `web/public/geo/areas.json`（2.3MB，
  gzip 后约 0.6MB）：区市町村 62 个（5 位代码）、町・大字 1,667 个（9 位：区市町村 + 町字 4 位）、丁目・字 5,596 个
  （11 位：区市町村 + S_AREA）；三级共用同一组边线；
- 同时给 `tokyo_chome.csv` 加 `estat_code` 列：每个位置参照情報的町丁目对应哪个 e-Stat 丁目。先找同一区市町村内同名的
  区域（5,231 个），找不到再看代表点落在哪个多边形里（159 个，多为“ヶ/ケ”等异体字和 2020 年之后新设的町名），
  1 个（冲之鸟岛）没有对应。

### 10.2 匹配规则（`geocode.py`）

1. 地址规范化：NFKC、去空白、“ヶ/ケ”统一；去掉开头的“東京都”（新築マンション的地址本来就没有）；
2. 区市町村：按名称最长前缀匹配，也接受省略“西多摩郡”的写法以及 SUUMO 的“三宅島三宅村”“八丈島八丈町”；匹配不到时用房源所属的区代码；
3. 町名：去掉“大字”，在该区市町村的町名中取最长前缀（“本町田”优先于“本町”）；
4. 丁目：町名后紧跟的数字（或“三丁目”这样的汉字）作为丁目号。

| 精度 | 条件 | 坐标 |
|---|---|---|
| `chome` | 命中某个町丁目（或没有丁目的町、大字） | 该町丁目的代表点 |
| `town` | 町名命中但没有该丁目 | 该町所有丁目代表点的平均 |
| `city` | 只命中区市町村 | 该区市町村所有町丁目代表点的平均 |

2026-11-07 的 8,672 条真实房源全部达到 `chome` 精度。SUUMO 的区代码与行政代码有 5 处不同：`13300` 西多摩郡（4 个町村合为一个区域）以及 4 个岛屿支厅（`13360/13380/13400/13420`，件数始终为 0，件数在下属町村上）；这些区域的代表点取下属町村的平均。

### 10.3 输出（`suumoviz build`，步骤 9 改为三级区域 + 时间轴）

`suumoviz build --data-dir data --out web/public/data`，只读 `data/`，不联网。每个文件都是编码后的 JSON（见 5.2），
**只有按区域汇总的数字，没有单条房源**：

```text
index.dat                          timeline、类别、全东京每天的值、SUUMO 公布的全东京件数、来源
day/{日期}/{类别}.dat               这一天所有区域（三级）的值：地图用
history/{类别}/{上级代码}.dat        上级区域之下各区域每天的值：点击区域后的走势用
                                   13000 → 各区市町村；区市町村 → 各町；町 → 各丁目
```

**区域**：`Geocoder.area_codes` 把房源地址对应到 e-Stat 的三级区域。地址只能对应到町（`town` 精度，且该町的丁目都在
同一个 e-Stat 町里）的房源只计入町和区市町村；只能对应到区市町村的只计入区市町村；SUUMO 的合并区域（西多摩郡等）
且地址认不出的只计入全东京。

**某一天的在售房源**：首次出现日 ≤ D，且 D < 最后一次被扫到的日期 + 9 天（`GRACE_DAYS` = 7 天周期 + 2 天）。
实测房源在 7 天后被再次扫到（偏差 ±1 天，翻页漂移所致），所以 9 天能盖住正常的重扫间隔。与合并时的下架判定（15 天）不同，
这里只用于统计；所有日期用同一规则，所以走势不受“刚开始采集”或“当天还没重扫”的影响。
价格取 D 当天或之前最近一次价格事件（`new`、`price_change`、`relisted`）。
2026-11-19 中古マンション：按此规则 38,383 套，SUUMO 公布 37,780 套（多 1.6%，即已下架但还在 9 天内的房源）。

**时间轴**：第一个完整轮转周期（连续 7 天成功合并）开始后的第 9 天起（2026-11-16），之前的天数窗口里有没扫过的页；
最近 90 天每天一个点，更早的每 7 天一个点（从起点算）。

**每个区域的值**（`count, n, mean, median, unit_n, unit_mean, unit_median`）：

| 字段 | 含义 |
|---|---|
| `count` | 在售套数 |
| `n` / `mean` / `median` | 有价格的套数；`price_min` 的平均数 / 中位数（万円，取整；价格为区间时取下限） |
| `unit_n` / `unit_mean` / `unit_median` | 价格和面积都是单一值的套数；价格 ÷ 面积的平均数 / 中位数（万円/m²，一位小数）；マンション用専有面積，一戸建て用建物面積 |

- 样本少于 3 套（`MIN_SAMPLE`）时价格类的值为 null，避免从区域值读出单套房源的价格；`count` 照常输出；
- 单价只用价格、面积都是单一值的房源：新築マンション一条房源常是一个楼盘，价格和面积是不同户型的区间，相除没有意义。
  2026-11-19 新築マンション 949 条中 672 条是单一值（单户出售），可以计算；新築一戸建て约 20% 是区间，不计入单价；
- 2026-11-19 的数据（4 个日期）：3,917 个文件，共 6.2MB，构建约 2 秒；每天约增加 1MB（day 文件）+ history 的增量；
  90 天后改为每周一个点，第一年约 300MB，在 Pages 的 1GB 限制内；
- 单个文件超过 4MB 时构建失败、不改动输出目录；先写到临时目录，全部成功后再替换 `index.dat`、`day/`、`history/`；
  同样的输入和时间得到逐字节相同的输出。

### 10.4 Web（步骤 6；步骤 8 简化；步骤 9 改为分区着色、时间轴、走势）

**部署结构**：代码和数据在同一个公开仓库 `Imanity/suumoviz`，Pages workflow 把网页、`geo/areas.json` 和 `data/`
一起发布到 <https://imanity.github.io/suumoviz/>。不需要登录或 Token。

- 页面只运行自身打包的脚本，CSP 只允许连接本站和地理院タイル；设置 `noindex`；
- `data/*.dat` 在浏览器中解码（`web/src/codec.ts`，与 Python 的 `codec.py` 用同一密钥，测试中有跨语言样例），
  每次打开都重新验证（`cache: no-cache`）；`geo/areas.json` 是公开的 e-Stat 数据，不编码；
- Pages workflow 检查 `dist/` 中只有 `index.html`、`assets/`、`geo/areas.json` 和 `data/` 下编码后的 `.dat`。

**地图与界面**：

- MapLibre GL JS + 地理院タイル 淡色地図；三级区域各一个 GeoJSON 源（`promoteId: id`），值通过 feature-state 着色，
  切换日期、指标时不重新加载边界；
- 颜色：单色蓝 7 档（蓝 100–700），分档按**最新一天**该级区域的值等分，切换日期时分档不变，颜色可以前后比较；
  样本不足为灰色，无在售房源不着色；
- 细分粒度随缩放切换：缩放 < 11 为区市町村，11–13 为町・大字，≥ 13 为丁目・字；也可以固定某一级；
- 左侧（一个滚动栏）：类别（4 类）、可视化维度（单价均价 / 单价中位数 / 总价均价 / 总价中位数 / 在售套数）、
  细分粒度、时间轴（滑块 + 前后一天）、所选区域、地图范围内该级区域的排行（最多 150 行）；
- 所选区域：层级导航（東京都 › 区 › 町 › 丁目，可点上级）、当天各项指标、当前指标的走势图（2px 折线、
  悬停十字线和数值、虚线标出地图上的日期、点击某天跳到该日期、可展开数据表）；未选区域时显示全东京和 SUUMO 公布的件数；
- 点击地图上的区域只选中（黑色描边，在任何一级都显示）；点击排行或层级导航还会把地图移到该区域；
- 手机：选项在上、地图 55% 高、详情和排行在下；地图需两指拖动，单指可以滚动页面。

## 11. 已知限制

- 同一套房被多家中介刊登时会有多个 `listing_id`，v1 不合并；
- 最细只到丁目・字：列表页地址约 80% 只写到丁目（2026-11-19 中古マンション：只到丁目 30,264 条，带番地 8,088 条），
  也没有可免费取得的番地级边界；番地级的值大多只有 1–2 套，等于公开单套房源；
- 房源按地址的町丁目归入区域，不是实际位置；位置参照情報与 e-Stat 2020 边界有约 3% 的町丁目名称不一致，
  靠代表点所在的多边形对应，个别丁目可能归到相邻丁目；2020 年以后新设的町名归到旧的区域；
- 新挂牌、调价最晚 7 天才被发现，挂牌天数精度为 ±7 天；
- 只有 1 页的组合，价格数据每 7 天更新一次（件数每天更新）；
- 第一个 7 天周期内所有房源都是第一次出现，这期间的 `new` 事件代表“初始库存”，不是真正的新挂牌；统计新挂牌应从首次运行日 + 7 天开始（首次运行日见 `runs.csv` 第一行）；全量统计同样要等第一个周期结束才覆盖完整；
- “在售”按最后一次被扫到后 9 天内计（10.3），比 SUUMO 当天公布的件数略多（2026-11-19 中古マンション多 1.6%）；
- 时间轴从第一个完整周期后的第 9 天（2026-11-16）开始，此前的数据不显示；
- 编码只是混淆：公开仓库的 `data` 分支任何人都能下载并用仓库里的代码还原。
