# geodata

`tokyo_chome.csv`：东京都的大字・町丁目代表点，5,390 行，UTF-8。

| 列 | 含义 |
|---|---|
| `town_code` | 大字町丁目コード（12 位） |
| `city_code` | 市区町村コード（5 位） |
| `city_name` | 市区町村名 |
| `town_name` | 大字町丁目名 |
| `lat`, `lng` | 代表点（世界测地系） |

- 出典：大字・町丁目位置参照情報 国土交通省（令和 7 年，19.0b，`13000-19.0b.zip` 中的 `13_2025.csv`），
  取得日期为 2026-11-07，下载地址 https://nlftp.mlit.go.jp/isj/ ；
- 加工：只保留上表中的 6 列，按 `town_code` 排序，Shift_JIS 转为 UTF-8（`tools/make_chome.py`）；
- 更新：下载新年度的东京都 zip，运行 `python tools/make_chome.py <zip> src/suumoviz/geodata/tokyo_chome.csv`，
  然后修改 `geocode.py` 中的 `GEO_SOURCE` 和本文件。
