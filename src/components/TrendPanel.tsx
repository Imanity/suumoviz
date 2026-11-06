import {
  formatCount,
  formatCountShort,
  formatMan,
  formatManShort,
  formatUnit,
} from '../format'
import type { Area, CategoryKey, Meta, Trends, Values } from '../types'
import { LineChart } from './LineChart'

interface Props {
  meta: Meta
  areas: Area[]
  trends: Trends
  category: CategoryKey
  area: string
  onArea: (area: string) => void
}

const TABLE_ROWS = 60

function sumRecent(values: Values, days: number): number {
  return values.slice(-days).reduce<number>((sum, v) => sum + (v ?? 0), 0)
}

export function TrendPanel({ meta, areas, trends, category, area, onArea }: Props) {
  const options = areas.filter(
    (a) =>
      a.code === meta.prefecture_area ||
      trends.series[a.code]?.count.some((v) => v !== null && v > 0),
  )
  const series = trends.series[area]
  const label = meta.categories.find((c) => c.key === category)?.label ?? category
  const { dates } = trends
  const steady = meta.steady_from
  const newListings = series?.new.map((v, i) => (dates[i] < steady ? null : v)) ?? []

  return (
    <section className="card trends" aria-label="趋势">
      <header className="trend-head">
        <h2>趋势</h2>
        <label>
          <span className="sr-only">区域</span>
          <select value={area} onChange={(e) => onArea(e.target.value)}>
            {options.map((a) => (
              <option key={a.code} value={a.code}>
                {a.name}
              </option>
            ))}
          </select>
        </label>
        <span className="muted">{label}</span>
      </header>

      {!series ? (
        <p className="hint">该区域没有{label}的数据。</p>
      ) : (
        <>
          <LineChart
            title="在售件数"
            note="来自区汇总页，每天精确"
            dates={dates}
            values={series.count}
            valueLabel="在售件数"
            format={(v) => `${formatCount(v)} 件`}
            tickFormat={formatCountShort}
          />
          <LineChart
            title="价格中位数"
            note="全量在售房源；阴影为 P25–P75"
            dates={dates}
            values={series.median}
            valueLabel="中位数"
            band={{ lo: series.p25, hi: series.p75, loLabel: 'P25', hiLabel: 'P75' }}
            format={formatMan}
            tickFormat={formatManShort}
          />
          {category !== 'new_condo' && (
            <LineChart
              title="单价中位数"
              note="价格 ÷ 面积，土地类除外"
              dates={dates}
              values={series.unit}
              valueLabel="单价中位数"
              format={formatUnit}
              tickFormat={(v) => `${Math.round(v)}`}
            />
          )}
          <LineChart
            title="每日新挂牌"
            note={`${steady} 之前是首个周期的初始库存，不计入`}
            dates={dates}
            values={newListings}
            valueLabel="新挂牌"
            kind="column"
            zeroBased
            format={(v) => `${formatCount(v)} 套`}
            tickFormat={formatCountShort}
          />
          <p className="muted small">
            最近 7 天：新挂牌 {formatCount(sumRecent(newListings, 7))} · 调价{' '}
            {formatCount(sumRecent(series.price_change, 7))} · 下架{' '}
            {formatCount(sumRecent(series.delisted, 7))}
          </p>
          <details>
            <summary>数据表</summary>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th scope="col">日期</th>
                    <th scope="col" className="num">件数</th>
                    <th scope="col" className="num">中位价</th>
                    <th scope="col" className="num">P25–P75</th>
                    <th scope="col" className="num">单价</th>
                    <th scope="col" className="num">新挂牌</th>
                    <th scope="col" className="num">调价</th>
                    <th scope="col" className="num">下架</th>
                  </tr>
                </thead>
                <tbody>
                  {dates
                    .map((date, i) => ({ date, i }))
                    .reverse()
                    .slice(0, TABLE_ROWS)
                    .map(({ date, i }) => (
                      <tr key={date}>
                        <td>{date}</td>
                        <td className="num">{formatCount(series.count[i])}</td>
                        <td className="num">{formatMan(series.median[i])}</td>
                        <td className="num">
                          {series.p25[i] === null
                            ? '—'
                            : `${formatMan(series.p25[i])}～${formatMan(series.p75[i])}`}
                        </td>
                        <td className="num">{formatUnit(series.unit[i])}</td>
                        <td className="num">{formatCount(newListings[i])}</td>
                        <td className="num">{formatCount(series.price_change[i])}</td>
                        <td className="num">{formatCount(series.delisted[i])}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </details>
        </>
      )}
    </section>
  )
}
