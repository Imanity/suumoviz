import type { Metric, Ranked } from '../data'
import { formatCount, formatMetric } from '../format'
import { type AreaInfo, pathNames } from '../geo'

const MAX_ROWS = 150

interface Props {
  rows: Ranked[] // already ranked
  metric: Metric
  info: Map<string, AreaInfo>
  selected: string | null
  onSelect: (code: string | null) => void
}

export function RankList({ rows, metric, info, selected, onSelect }: Props) {
  const shown = rows.slice(0, MAX_ROWS)
  const max = Math.max(0, ...shown.map((r) => r.value ?? 0))

  if (rows.length === 0) return <p className="muted small">地图范围内没有在售房源。</p>

  return (
    <>
      <table className="ranking">
        <caption className="sr-only">地图范围内各区域{metric.short}排行</caption>
        <thead>
          <tr>
            <th scope="col" className="num">
              #
            </th>
            <th scope="col">区域</th>
            <th scope="col">{metric.short}</th>
            {metric.kind !== 'count' && (
              <th scope="col" className="num">
                在售
              </th>
            )}
          </tr>
        </thead>
        <tbody>
          {shown.map((row, i) => {
            const few = row.value === null
            return (
              <tr
                key={row.code}
                data-code={row.code}
                className={`${row.code === selected ? 'selected' : ''}${few ? ' few' : ''}`}
                aria-selected={row.code === selected}
                tabIndex={0}
                onClick={() => onSelect(row.code === selected ? null : row.code)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    onSelect(row.code === selected ? null : row.code)
                  }
                }}
              >
                <td className="num muted">{few ? '' : i + 1}</td>
                <td>
                  <AreaName code={row.code} info={info} />
                </td>
                <td className="value">
                  <span
                    className="bar"
                    style={{ width: row.value === null || !max ? 0 : `${(row.value / max) * 100}%` }}
                  />
                  <span className="num">{few ? '样本不足' : formatMetric(metric, row.value)}</span>
                </td>
                {metric.kind !== 'count' && <td className="num">{formatCount(row.values.count)}</td>}
              </tr>
            )
          })}
        </tbody>
      </table>
      {rows.length > MAX_ROWS && (
        <p className="muted small">
          共 {formatCount(rows.length)} 个区域，只列出前 {MAX_ROWS} 个；放大地图可缩小范围。
        </p>
      )}
    </>
  )
}

/** "南烏山一丁目" with its municipality in small print. */
function AreaName({ code, info }: { code: string; info: Map<string, AreaInfo> }) {
  const names = pathNames(code, info)
  const own = names[names.length - 1] ?? code
  return (
    <>
      {names.length > 1 && <span className="area-city">{names[0]}</span>}
      {own}
    </>
  )
}
