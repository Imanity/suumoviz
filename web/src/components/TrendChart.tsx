import { useEffect, useMemo, useRef, useState } from 'react'
import type { Metric } from '../data'
import { formatCount, formatDay, formatMetric, formatMetricShort } from '../format'

export interface TrendPoint {
  date: string
  value: number | null
  sample: number | null // listings behind the value
}

interface Props {
  title: string
  metric: Metric
  points: TrendPoint[]
  current: number // index of the date shown on the map
  onPick: (index: number) => void
}

const HEIGHT = 156
const M = { top: 12, right: 14, bottom: 24, left: 46 }

/** About `count` round tick values covering [lo, hi]. */
export function niceTicks(lo: number, hi: number, count = 4): number[] {
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return []
  if (lo === hi) return [lo]
  const raw = (hi - lo) / count
  const power = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 5, 10].map((m) => m * power).find((s) => s >= raw) ?? raw
  const ticks: number[] = []
  for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step) {
    ticks.push(Math.round(v * 1e6) / 1e6)
  }
  return ticks
}

export function TrendChart({ title, metric, points, current, onPick }: Props) {
  const wrap = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(320)
  const [hover, setHover] = useState<number | null>(null)

  useEffect(() => {
    const node = wrap.current
    if (!node) return
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(200, entry.contentRect.width)))
    observer.observe(node)
    return () => observer.disconnect()
  }, [])

  const geometry = useMemo(() => {
    const times = points.map((p) => Date.parse(p.date))
    const values = points.flatMap((p) => (p.value === null ? [] : [p.value]))
    if (values.length === 0) return null
    let lo = Math.min(...values)
    let hi = Math.max(...values)
    const pad = (hi - lo) * 0.15 || Math.abs(hi) * 0.05 || 1
    lo -= pad
    hi += pad
    if (metric.kind === 'count' && lo < 0) lo = 0
    const ticks = niceTicks(lo, hi, 4).filter((t) => t >= lo && t <= hi)
    const t0 = times[0]
    const t1 = times[times.length - 1]
    const innerW = width - M.left - M.right
    const innerH = HEIGHT - M.top - M.bottom
    const x = (i: number) => (t1 === t0 ? M.left + innerW / 2 : M.left + ((times[i] - t0) / (t1 - t0)) * innerW)
    const y = (v: number) => M.top + (1 - (v - lo) / (hi - lo)) * innerH
    // a gap wherever a day has no value
    const segments: string[] = []
    let path = ''
    points.forEach((p, i) => {
      if (p.value === null) {
        if (path) segments.push(path)
        path = ''
        return
      }
      path += `${path ? 'L' : 'M'}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`
    })
    if (path) segments.push(path)
    return { x, y, ticks, segments, innerW }
  }, [points, width, metric.kind])

  const labelIndexes = useMemo(() => {
    if (points.length <= 6) return points.map((_, i) => i)
    const mid = Math.round((points.length - 1) / 2)
    return [0, mid, points.length - 1]
  }, [points])

  if (!geometry) {
    return (
      <figure className="trend" aria-label={title}>
        <figcaption className="trend-title">{title}</figcaption>
        <p className="muted small">这一期间没有可显示的数值（样本不足或无在售房源）。</p>
      </figure>
    )
  }
  const { x, y, ticks, segments } = geometry

  const nearest = (clientX: number, rect: DOMRect): number => {
    const px = clientX - rect.left
    let best = 0
    points.forEach((_, i) => {
      if (Math.abs(x(i) - px) < Math.abs(x(best) - px)) best = i
    })
    return best
  }

  const focus = hover ?? current
  const focusPoint = points[focus]
  const marker = (i: number, emphasis: boolean) => {
    const v = points[i]?.value
    if (v === null || v === undefined) return null
    return (
      <circle
        cx={x(i)}
        cy={y(v)}
        r={emphasis ? 5 : 4}
        className="trend-dot"
        // the 2px surface ring keeps the dot readable on the line
        strokeWidth={2}
      />
    )
  }

  return (
    <figure className="trend" aria-label={title}>
      <figcaption className="trend-title">{title}</figcaption>
      <div ref={wrap} className="trend-plot">
        <svg
          width={width}
          height={HEIGHT}
          role="img"
          aria-label={`${title}：${points
            .map((p) => `${p.date} ${formatMetric(metric, p.value)}`)
            .join('，')}`}
          onPointerMove={(e) => setHover(nearest(e.clientX, e.currentTarget.getBoundingClientRect()))}
          onPointerLeave={() => setHover(null)}
          onClick={(e) => onPick(nearest(e.clientX, e.currentTarget.getBoundingClientRect()))}
        >
          {ticks.map((t) => (
            <g key={t}>
              <line x1={M.left} x2={width - M.right} y1={y(t)} y2={y(t)} className="trend-grid" />
              <text x={M.left - 6} y={y(t)} className="trend-axis" textAnchor="end" dominantBaseline="middle">
                {formatMetricShort(metric, t)}
              </text>
            </g>
          ))}
          {labelIndexes.map((i) => (
            <text
              key={i}
              x={x(i)}
              y={HEIGHT - 6}
              className="trend-axis"
              // the end labels stay inside the plot
              textAnchor={points.length > 1 && i === 0 ? 'start' : i === points.length - 1 && i > 0 ? 'end' : 'middle'}
            >
              {formatDay(points[i].date)}
            </text>
          ))}
          {/* the day shown on the map */}
          <line x1={x(current)} x2={x(current)} y1={M.top} y2={HEIGHT - M.bottom} className="trend-current" />
          {segments.map((d) => (
            <path key={d} d={d} className="trend-line" />
          ))}
          {segments.length === 0 || points.filter((p) => p.value !== null).length === 1
            ? points.map((p, i) => (p.value === null ? null : <g key={p.date}>{marker(i, false)}</g>))
            : null}
          {hover !== null && (
            <line x1={x(hover)} x2={x(hover)} y1={M.top} y2={HEIGHT - M.bottom} className="trend-crosshair" />
          )}
          {marker(focus, hover !== null)}
        </svg>
        {focusPoint && (
          <div
            className="trend-tip"
            // on the inner side of the point, so it never leaves the plot
            style={x(focus) > width / 2 ? { right: width - x(focus) } : { left: x(focus) }}
            aria-hidden="true"
          >
            <span className="muted">{focusPoint.date}</span>
            <strong>{formatMetric(metric, focusPoint.value)}</strong>
            {metric.kind !== 'count' && focusPoint.sample !== null && (
              <span className="muted">计入 {formatCount(focusPoint.sample)} 套</span>
            )}
          </div>
        )}
      </div>
      <details className="trend-table">
        <summary>数据表</summary>
        <table>
          <thead>
            <tr>
              <th scope="col">日期</th>
              <th scope="col" className="num">
                {metric.short}
              </th>
              {metric.kind !== 'count' && (
                <th scope="col" className="num">
                  计入套数
                </th>
              )}
            </tr>
          </thead>
          <tbody>
            {points.map((p) => (
              <tr key={p.date}>
                <td>{p.date}</td>
                <td className="num">{formatMetric(metric, p.value)}</td>
                {metric.kind !== 'count' && <td className="num">{formatCount(p.sample)}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  )
}
