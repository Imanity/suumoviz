# 测试样本（fixtures）

`suumo/` 下的 HTML 取自 2026-11-07 的真实 SUUMO 页面，仅用于离线解析测试。仓库公开，所以这些文件
和 `data` 分支一样以编码形式存放（`#suumoviz-obf/1`，见 `docs/design.md` 5.2）；测试读取时自动解码，
查看原文用 `suumoviz decode tests/fixtures/suumo/<文件>`。处理方式：

- 用 `tools/trim_fixture.py` 去掉脚本、样式、图片和注释；
- 列表页只保留少量条目，经纪公司电话块已删除，残留电话号码遮蔽为 `00-0000-0000`；
- 区汇总页保留全部区市町村条目（测试依赖当日件数合计）。

| 文件 | 来源 URL | 保留条目 |
|---|---|---|
| `city_used_condo.html` | https://suumo.jp/ms/chuko/tokyo/city/ | 全部 |
| `city_new_condo.html` | https://suumo.jp/ms/shinchiku/tokyo/city/ | 全部 |
| `city_new_house.html` | https://suumo.jp/ikkodate/tokyo/city/ | 全部 |
| `city_used_house.html` | https://suumo.jp/chukoikkodate/tokyo/city/ | 全部 |
| `list_used_condo_setagaya_p1.html` | https://suumo.jp/ms/chuko/tokyo/sc_setagaya/?pc=100&po=3&pj=1 | 前 4 条 + 21895565（億、価格更新） |
| `list_used_condo_setagaya_p23.html` | https://suumo.jp/ms/chuko/tokyo/sc_setagaya/?page=23&pc=100&po=3&pj=1 | 全部 11 条（最后一页） |
| `list_new_condo_chuo_p1.html` | https://suumo.jp/ms/shinchiku/tokyo/sc_chuo/?pc=100 | 前 3 条（未定、区间价） |
| `list_new_house_setagaya_p1.html` | https://suumo.jp/ikkodate/tokyo/sc_setagaya/?pc=100&po=3&pj=1 | 前 3 条 + 21916513（土地类）+ 22106824（未定） |
| `list_used_house_setagaya_p1.html` | https://suumo.jp/chukoikkodate/tokyo/sc_setagaya/?pc=100&po=3&pj=1 | 前 3 条 + 21675148（巴士、地下室附注） |

重新生成示例：

```bash
python tools/trim_fixture.py raw.html tests/fixtures/suumo/list_x.html --keep 3 --also 21916513
```

`trim_fixture.py` 直接写出编码后的文件；放进其他来源的文件时先运行 `suumoviz encode <文件>`
（`tests/test_codec.py` 会检查所有样本都已编码）。

页面改版后，用新页面重新生成对应 fixture，并更新测试中的期望值。
