# geodata

`tokyo_chome.csv`：东京都的大字・町丁目代表点，5,390 行，UTF-8。

| 列 | 含义 |
|---|---|
| `town_code` | 大字町丁目コード（12 位） |
| `city_code` | 市区町村コード（5 位） |
| `city_name` | 市区町村名 |
| `town_name` | 大字町丁目名 |
| `lat`, `lng` | 代表点（世界测地系） |
| `estat_code` | 对应的 e-Stat 2020 小地域代码（11 位：区市町村 5 位 + S_AREA 6 位；空 = 没有对应） |

- 出典：大字・町丁目位置参照情報 国土交通省（令和 7 年，19.0b，`13000-19.0b.zip` 中的 `13_2025.csv`），
  取得日期为 2026-11-07，下载地址 https://nlftp.mlit.go.jp/isj/ ；
- 加工：只保留上表前 6 列，按 `town_code` 排序，Shift_JIS 转为 UTF-8（`tools/make_chome.py`）；
- 更新：下载新年度的东京都 zip，运行 `python tools/make_chome.py <zip> src/suumoviz/geodata/tokyo_chome.csv`，
  然后修改 `geocode.py` 中的 `GEO_SOURCE` 和本文件；之后必须重跑 `tools/make_boundaries.py` 补回 `estat_code`。

`estat_code` 由 `tools/make_boundaries.py` 写入：先找同一区市町村内同名的 e-Stat 区域，找不到再看代表点落在哪个
多边形里。边界来源：e-Stat「国勢調査 2020年 小地域（町丁・字等別）境界データ」东京都
（`A002005212020DDSWC13-JGD2011.zip`，2026-11-19 下载，https://www.e-stat.go.jp/gis/ ），
同一次运行还生成网页用的 `web/public/geo/areas.json`：

```bash
npm install --prefix <临时目录> mapshaper@0.8.5
python tools/make_boundaries.py <解压后的 r2ka13.shp> --mapshaper <临时目录>/node_modules/.bin/mapshaper
```
