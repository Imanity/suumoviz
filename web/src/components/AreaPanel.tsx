import { useEffect, useRef } from 'react'
import { lineage, type Metric, METRICS, metricValue, type Values } from '../data'
import { formatCount, formatMetric } from '../format'
import type { AreaInfo } from '../geo'
import { type TrendPoint, TrendChart } from './TrendChart'

interface Props {
  code: string | null // null: all of Tokyo
  info: Map<string, AreaInfo>
  categoryLabel: string
  metric: Metric
  dates: string[]
  current: number
  values: Values | null // on the current date
  series: (Values | null)[] | null // per date; null while loading
  official: number | null // SUUMO's own count (all of Tokyo only)
  error: string | null
  onSelect: (code: string | null) => void
  onPickDate: (index: number) => void
}

export function AreaPanel(props: Props) {
  const { code, info, categoryLabel, metric, dates, current, values, series, official, error } = props
  const section = useRef<HTMLElement>(null)
  // a new selection: bring its details into view in the desktop sidebar (on phones the
  // page would scroll away from the map)
  useEffect(() => {
    if (code && window.matchMedia('(min-width: 801px)').matches) {
      section.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
    }
  }, [code])
  const path = code ? lineage(code) : []
  const name = code ? (info.get(code)?.name ?? code) : '東京都'
  const points: TrendPoint[] | null = series
    ? dates.map((date, i) => ({
        date,
        value: metricValue(series[i], metric.key),
        sample: series[i] ? series[i]![metric.sample] : null,
      }))
    : null

  return (
    <section ref={section} className="panel" aria-label="所选区域">
      <nav className="crumbs" aria-label="区域层级">
        {code ? (
          <button type="button" className="link" onClick={() => props.onSelect(null)}>
            東京都
          </button>
        ) : (
          <span>東京都</span>
        )}
        {path.slice(0, -1).map((c) => (
          <span key={c}>
            <span className="sep" aria-hidden="true">
              ›
            </span>
            <button type="button" className="link" onClick={() => props.onSelect(c)}>
              {info.get(c)?.name ?? c}
            </button>
          </span>
        ))}
      </nav>
      <h2 className="panel-title">
        {name}
        <span className="muted small">
          {' '}
          {categoryLabel} · {dates[current]}
        </span>
      </h2>
      {values ? (
        <dl className="stats">
          {METRICS.map((m) => {
            const value = metricValue(values, m.key)
            return (
              <div key={m.key} className={m.key === metric.key ? 'current' : ''}>
                <dt>{m.short}</dt>
                <dd>{value === null ? <span className="muted small">样本不足</span> : formatMetric(m, value)}</dd>
              </div>
            )
          })}
          <div className="wide muted small">
            有价格 {formatCount(values.n)} 套 · 可算单价 {formatCount(values.unit_n)} 套
            {official !== null && <> · SUUMO 公布在售 {formatCount(official)} 套</>}
          </div>
        </dl>
      ) : (
        <p className="muted small">这一天没有在售房源。</p>
      )}
      {error ? (
        <p className="error small">{error}</p>
      ) : points ? (
        <TrendChart
          title={`${metric.short}走势`}
          metric={metric}
          points={points}
          current={current}
          onPick={props.onPickDate}
        />
      ) : (
        <p className="muted small">正在读取走势…</p>
      )}
    </section>
  )
}
