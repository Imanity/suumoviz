# SuumoViz（地图前端）

东京都 SUUMO 在售房源的地图与趋势页面。页面部署在 GitHub Pages：<https://imanity.github.io/suumoviz/>

**本仓库只有前端代码，不含任何房源数据。** 数据由私有仓库 `Imanity/suumoviz-data` 每天采集并生成，
保存在该仓库的 `site` 分支；页面在浏览器里用访问者自己的只读 Token 通过 GitHub API 读取，
不经过其他服务器。没有 Token 的访问者只能看到登录框。

## 使用

1. 创建一个 [fine-grained personal access token](https://github.com/settings/personal-access-tokens/new)：
   - Repository access：Only select repositories → 只选数据仓库；
   - Permissions → Repository permissions → **Contents: Read-only**（其他保持默认）；
   - 设有效期（例如 90 天）。
2. 打开页面，填入数据仓库名与 Token。默认只保存到关闭标签页为止；勾选“在这台设备上记住”才写入浏览器存储。

功能：按类别（中古/新築マンション、新築/中古一戸建て）、价格、面积筛选；地图按町丁目聚合
（圆点大小 = 套数，颜色 = 中位价格或单价）；点击圆点查看房源并跳转 SUUMO 详情；
按区查看在售件数、价格中位数（P25–P75）、单价、每日新挂牌的趋势。

## 开发

需要 Node.js 22+。

```bash
npm ci
# 用数据仓库生成本地数据（public/data/ 已被 .gitignore 忽略，绝不提交）
(cd ../suumoviz-data && suumoviz build --data-dir data --out ../suumoviz/public/data)
npm run dev        # 开发模式直接读 public/data/，不需要 Token
npm test           # 单元测试（vitest）
npm run build      # 类型检查 + 生产构建（不复制 public/，产物中没有数据）
```

`VITE_LOCAL_DATA=1 npm run build` 可以生成读取本地数据的构建，用于 `npm run preview` 验证；
生产构建默认读取 GitHub。

## 部署

推送到 `main` 后，`.github/workflows/pages.yml` 运行测试、构建，确认 `dist/` 中没有数据，
然后发布到 GitHub Pages。

## 安全

- 页面只运行自身打包的脚本；Content-Security-Policy 只允许连接 `api.github.com` 和地理院タイル；
- Token 只发给 `api.github.com`；同一账号的其他 Pages 站点与本页同源，因此“记住”默认关闭；
- Token 泄露的影响限于读取数据仓库，可随时在 GitHub 上撤销；
- 页面设置了 `noindex`。

## 出典

- 底图：[地理院タイル](https://maps.gsi.go.jp/development/ichiran.html)（淡色地図，国土地理院）
- 町丁目坐标：「大字・町丁目レベル位置参照情報」国土交通省（令和7年，19.0b）を加工
- 房源：SUUMO 列表页，仅供个人分析，不公开、不转载
- 地图库：[MapLibre GL JS](https://maplibre.org/)（BSD-3-Clause）
