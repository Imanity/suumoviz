import { useEffect, useRef } from 'react'
import { formatCount, formatMan, formatUnit } from '../format'
import { type AreaValue, type Metric, metricValue, MIN_SAMPLE } from '../summary'

interface Props {
  areas: AreaValue[] // already ranked
  metric: Metric
  selected: string | null
  onSelect: (code: string | null) => void
}

export function RankList({ areas, metric, selected, onSelect }: Props) {
  const body = useRef<HTMLTableSectionElement>(null)
  const max = Math.max(0, ...areas.map((a) => metricValue(a, metric) ?? 0))
  const format = metric === 'mean' ? formatMan : formatUnit

  // keep the selected row visible when it was picked on the map
  useEffect(() => {
    if (!selected) return
    body.current
      ?.querySelector<HTMLElement>(`[data-code="${selected}"]`)
      ?.scrollIntoView({ block: 'nearest' })
  }, [selected])

  return (
    <table className="ranking">
      <caption className="sr-only">各区域{metric === 'mean' ? '均价' : '单价均价'}排行</caption>
      <thead>
        <tr>
          <th scope="col" className="num">#</th>
          <th scope="col">区域</th>
          <th scope="col">{metric === 'mean' ? '均价' : '单价均价'}</th>
          <th scope="col" className="num">在售</th>
        </tr>
      </thead>
      <tbody ref={body}>
        {areas.map((area, i) => {
          const value = metricValue(area, metric)
          const few = area.n < MIN_SAMPLE
          return (
            <tr
              key={area.code}
              data-code={area.code}
              className={`${area.code === selected ? 'selected' : ''}${few ? ' few' : ''}`}
              aria-selected={area.code === selected}
              tabIndex={0}
              onClick={() => onSelect(area.code === selected ? null : area.code)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  onSelect(area.code === selected ? null : area.code)
                }
              }}
            >
              <td className="num muted">{value === null ? '' : i + 1}</td>
              <td>
                {area.name}
                {few && <span className="tag" title={`只有 ${area.n} 套房源有价格`}>样本少</span>}
              </td>
              <td className="value">
                <span className="bar" style={{ width: value === null || !max ? 0 : `${(value / max) * 100}%` }} />
                <span className="num">{format(value)}</span>
              </td>
              <td className="num">{formatCount(area.count)}</td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
