# SuumoViz

每天采集一次东京都 SUUMO 在售房源（中古/新築マンション、新築/中古一戸建て）的列表页，按区域统计价格，
在地图上分区着色展示（区市町村 → 町 → 丁目，随缩放切换），可以沿时间轴查看，点击区域看走势。
页面：<https://imanity.github.io/suumoviz/>

- 按 7 天轮转，每天只扫约 1/7 的列表页（约 100 页，每 5 秒 1 页），每 7 天覆盖全部房源一次；
- 采集结果存放在本仓库的 `data` 分支，**逐行编码混淆**，不能直接阅读（`suumoviz decode` 可以还原，见下文）；
- 网页只发布各区域每天的汇总数字（总价与单价的均价、中位数，在售套数），不发布单条房源；样本少于 3 套不显示价格。

计划、设计与验收：[docs/plan.md](docs/plan.md)、[docs/design.md](docs/design.md)、[docs/acceptance.md](docs/acceptance.md)。

## 目录

```text
src/suumoviz/          Python 包：采集、合并、统计、编码、网页数据
  categories.py        类别与 URL
  parse/               区汇总页、列表页解析与文本规范化
  robots.py            robots.txt 匹配（支持通配符）
  fetch.py             限速抓取与停机规则
  rotation.py          7 天轮转
  state.py             偏移量与冷却状态（state.json，明文）
  crawl.py / cli.py    一次运行的编排与命令行
  codec.py             数据文件的编码混淆
  store.py             data/ 下 CSV 表的读写（经过 codec）
  quality.py           质量门槛
  merge.py             合并、事件、下架判定、统计
  geocode.py           地址 → 町丁目（国交省位置参照情報）→ e-Stat 三级区域
  build.py             网页用的按日期、按区域统计 web/public/data/
tests/                 单元测试；fixtures/suumo/ 为编码后的页面样本
tools/                 fixture 裁剪、町丁目数据转换、区域边界生成（make_boundaries.py）
web/                   网页（Vite + React + MapLibre GL JS + 地理院タイル）
  public/geo/areas.json  三级区域边界（e-Stat，TopoJSON，随仓库发布）
docs/                  计划、设计、验收
.github/workflows/     CI、每日采集、Pages 发布、试探
```

## 开发

需要 Python 3.12 和 Node.js 22+。

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"   # Linux/macOS: .venv/bin/python
.venv/Scripts/ruff check .
.venv/Scripts/python -m pytest                     # 完全离线
```

```bash
cd web
npm ci
npm test
npm run dev
```

本地看页面需要先取数据：

```bash
git fetch origin data
git worktree add data data                                      # 只需一次；之后 git -C data pull
suumoviz build --data-dir data --out web/public/data            # 生成 index.dat、day/、history/（已被 .gitignore 忽略）
```

## 采集

```bash
suumoviz crawl --dry-run --city-html tests/fixtures/suumo   # 不联网，只看今天的计划
suumoviz crawl --dry-run                                     # 联网 5 个请求，用当日件数看计划
suumoviz crawl --max-pages 5                                 # 试运行：只抓 5 个列表页
suumoviz daily                                               # 抓今天槽位的全部页面并合并进 data/
```

请求间隔固定不少于 5 秒；遇到 403/429/验证码会停止并冷却 24 小时（7 天内再次触发为 72 小时）。
线上由 GitHub Actions 每天日本时间 03:17 运行（GitHub 的定时任务经常延迟几个小时），
完成后提交 `data` 分支并重新发布 Pages。

## 数据编码

`data/` 下的 CSV 表、每日快照 `work/` 和测试样本都以 `#suumoviz-obf/1` 开头：之后每行是原文一行与固定密钥
异或后的 base64。**这只是混淆，不是加密**：密钥就在代码里（`src/suumoviz/codec.py`、`web/src/codec.ts`），
目的只是让数据不能被直接阅读、搜索或被搜索引擎收录。按行编码使未变化的行保持不变，`data` 分支每天的差异
和明文 CSV 一样小。

```bash
suumoviz decode data/listings/used_condo.csv | head   # 查看明文
suumoviz encode path/to/plain.csv                      # 就地编码（目录：其中所有 *.csv）
```

读取时自动识别：明文文件照常可读，下次写入时变为编码格式。`state.json` 和 `work/*/run.json`
只有运行状态，保持明文。

## 出典

- 底图：[地理院タイル](https://maps.gsi.go.jp/development/ichiran.html)（淡色地図，国土地理院）
- 地址对照：「大字・町丁目レベル位置参照情報」国土交通省（令和7年，19.0b）を加工
- 区域边界：「国勢調査 2020年 小地域（町丁・字等別）境界データ」総務省統計局（e-Stat）を加工
- 房源：SUUMO 列表页；网页只展示按区域汇总的统计值
- 地图库：[MapLibre GL JS](https://maplibre.org/)（BSD-3-Clause）
