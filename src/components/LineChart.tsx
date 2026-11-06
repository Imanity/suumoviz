import { type KeyboardEvent, type PointerEvent, useCallback, useRef, useState } from 'react'
import { DAY_MS, dayValue, nearestDefined, niceTicks } from '../chart-scale'
import { shortDate } from '../format'
import type { Values } from '../types'

interface Band {
  lo: Values
  hi: Values
  loLabel: string
  hiLabel: string
}

interface Props {
  title: string
  note?: string
  dates: string[]
  values: Values
  valueLabel: string
  band?: Band
  kind?: 'line' | 'column'
  format: (value: number) => string // tooltip and end label
  tickFormat: (value: number) => string // y axis
  zeroBased?: boolean
}

const HEIGHT = 156
const M = { top: 14, right: 22, bottom: 22, left: 50 }

/** Callback ref + observed width (works even when the element mounts later). */
function useWidth<T extends HTMLElement>() {
  const [width, setWidth] = useState(0)
  const observer = useRef<ResizeObserver | null>(null)
  const ref = useCallback((node: T | null) => {
    observer.current?.disconnect()
    observer.current = null
    if (node) {
      observer.current = new ResizeObserver(([entry]) =>
        setWidth(Math.floor(entry.contentRect.width)),
      )
      observer.current.observe(node)
    }
  }, [])
  return [ref, width] as const
}

/** Runs of consecutive indices where every array is defined. */
function runs(length: number, defined: (i: number) => boolean): number[][] {
  const out: number[][] = []
  let current: number[] = []
  for (let i = 0; i < length; i++) {
    if (defined(i)) current.push(i)
    else if (current.length) {
      out.push(current)
      current = []
    }
  }
  if (current.length) out.push(current)
  return out
}

function lastDefined(values: Values): number {
  for (let i = values.length - 1; i >= 0; i--) if (values[i] !== null) return i
  return -1
}

/**
 * Single-series time chart: a 2px line (optionally over a 10% P25–P75 wash) or
 * columns from a zero baseline. Crosshair + tooltip on pointer and arrow keys.
 */
export function LineChart(props: Props) {
  const { title, note, dates, values, valueLabel, band, kind = 'line', format, tickFormat } = props
  const [wrapRef, width] = useWidth<HTMLDivElement>()
  const [hover, setHover] = useState<number | null>(null)
  const last = lastDefined(values)

  const header = (
    <figcaption>
      <span className="chart-title">{title}</span>
      {note && <span className="chart-note">{note}</span>}
    </figcaption>
  )
  if (last < 0) {
    return (
      <figure className="chart">
        {header}
        <p className="chart-empty">暂无数据</p>
      </figure>
    )
  }

  const times = dates.map(dayValue)
  let t0 = Math.min(...times)
  let t1 = Math.max(...times)
  if (kind === 'column') {
    t0 -= DAY_MS / 2
    t1 += DAY_MS / 2
  }
  if (t0 === t1) {
    t0 -= DAY_MS
    t1 += DAY_MS
  }
  const innerW = Math.max(10, width - M.left - M.right)
  const innerH = HEIGHT - M.top - M.bottom
  const x = (t: number) => M.left + ((t - t0) / (t1 - t0)) * innerW

  const all = [...values, ...(band?.lo ?? []), ...(band?.hi ?? [])].filter(
    (v): v is number => v !== null,
  )
  const ticks = niceTicks(props.zeroBased ? 0 : Math.min(...all), Math.max(...all), 3)
  const [ylo, yhi] = [ticks[0], ticks[ticks.length - 1]]
  const y = (v: number) => M.top + innerH - ((v - ylo) / (yhi - ylo)) * innerH

  const lineRuns = runs(values.length, (i) => values[i] !== null)
  const linePaths = lineRuns
    .filter((r) => r.length > 1)
    .map((r) => r.map((i, k) => `${k ? 'L' : 'M'}${x(times[i])},${y(values[i]!)}`).join(''))
  const lonePoints = lineRuns.filter((r) => r.length === 1).map((r) => r[0])
  const bandPaths = band
    ? runs(values.length, (i) => band.lo[i] !== null && band.hi[i] !== null)
        .filter((r) => r.length > 1)
        .map(
          (r) =>
            r.map((i, k) => `${k ? 'L' : 'M'}${x(times[i])},${y(band.hi[i]!)}`).join('') +
            [...r].reverse().map((i) => `L${x(times[i])},${y(band.lo[i]!)}`).join('') +
            'Z',
        )
    : []

  const slot = (innerW * DAY_MS) / (t1 - t0)
  const barW = Math.min(24, Math.max(2, slot * 0.6))
  const base = y(Math.max(ylo, 0))
  const bars = values.flatMap((v, i) => {
    if (v === null || v <= 0) return []
    const top = y(v)
    const r = Math.min(4, barW / 2, base - top)
    const x0 = x(times[i]) - barW / 2
    const x1 = x0 + barW
    return [
      `M${x0},${base}V${top + r}Q${x0},${top} ${x0 + r},${top}H${x1 - r}Q${x1},${top} ${x1},${top + r}V${base}Z`,
    ]
  })

  const xTickCount = Math.min(dates.length, Math.max(2, Math.floor(innerW / 70)))
  const xTicks =
    dates.length === 1
      ? [0]
      : [
          ...new Set(
            Array.from({ length: xTickCount }, (_, k) =>
              Math.round((k * (dates.length - 1)) / (xTickCount - 1)),
            ),
          ),
        ]

  const move = (event: PointerEvent<SVGSVGElement>) => {
    const rect = event.currentTarget.getBoundingClientRect()
    const t = t0 + ((event.clientX - rect.left - M.left) / innerW) * (t1 - t0)
    const i = nearestDefined(times, values, t)
    setHover(i >= 0 ? i : null)
  }
  const key = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
    event.preventDefault()
    const step = event.key === 'ArrowLeft' ? -1 : 1
    let i = (hover ?? last) + step
    while (i >= 0 && i < values.length && values[i] === null) i += step
    if (i >= 0 && i < values.length) setHover(i)
  }

  const active = hover ?? null
  const tipLeft = active === null ? 0 : x(times[active])
  const tipOnLeft = tipLeft > width - 150

  return (
    <figure className="chart">
      {header}
      <div
        ref={wrapRef}
        className="chart-plot"
        tabIndex={0}
        onKeyDown={key}
        onFocus={() => setHover(last)}
        onBlur={() => setHover(null)}
        aria-label={`${title}：最新 ${dates[last]} ${valueLabel} ${format(values[last]!)}。用左右方向键查看各日数值。`}
      >
        {width > 0 && (
          <svg
            width={width}
            height={HEIGHT}
            role="img"
            aria-hidden="true"
            onPointerMove={move}
            onPointerLeave={() => setHover(null)}
          >
            {ticks.map((t) => (
              <g key={t}>
                <line
                  x1={M.left}
                  x2={width - M.right}
                  y1={y(t)}
                  y2={y(t)}
                  className={t === ylo && props.zeroBased ? 'axis-line' : 'grid-line'}
                />
                <text x={M.left - 6} y={y(t)} dy="0.32em" textAnchor="end" className="tick">
                  {tickFormat(t)}
                </text>
              </g>
            ))}
            {xTicks.map((i) => (
              <text
                key={i}
                x={x(times[i])}
                y={HEIGHT - 6}
                textAnchor="middle"
                className="tick"
              >
                {shortDate(dates[i])}
              </text>
            ))}
            {bandPaths.map((d) => (
              <path key={d} d={d} className="band" />
            ))}
            {kind === 'column'
              ? bars.map((d) => <path key={d} d={d} className="bar" />)
              : linePaths.map((d) => <path key={d} d={d} className="line" />)}
            {kind === 'line' &&
              lonePoints.map((i) => (
                <circle key={i} cx={x(times[i])} cy={y(values[i]!)} r={4} className="dot" />
              ))}
            {kind === 'line' && active === null && (
              <text
                x={Math.min(x(times[last]), width - 2)}
                y={y(values[last]!) - 9}
                textAnchor="end"
                className="end-label"
              >
                {format(values[last]!)}
              </text>
            )}
            {active !== null && (
              <g pointerEvents="none">
                <line
                  x1={x(times[active])}
                  x2={x(times[active])}
                  y1={M.top}
                  y2={M.top + innerH}
                  className="crosshair"
                />
                {kind === 'line' && (
                  <circle cx={x(times[active])} cy={y(values[active]!)} r={4} className="dot" />
                )}
              </g>
            )}
          </svg>
        )}
        {active !== null && (
          <div
            className="tooltip"
            style={
              tipOnLeft
                ? { right: width - tipLeft + 10, top: M.top }
                : { left: tipLeft + 10, top: M.top }
            }
          >
            <div className="tooltip-date">{dates[active]}</div>
            <div className="tooltip-row">
              <span className="key-line" />
              <strong>{format(values[active]!)}</strong>
              <span className="tooltip-label">{valueLabel}</span>
            </div>
            {band && band.lo[active] !== null && band.hi[active] !== null && (
              <div className="tooltip-row secondary">
                <span className="key-wash" />
                {format(band.lo[active]!)}～{format(band.hi[active]!)}
                <span className="tooltip-label">
                  {band.loLabel}–{band.hiLabel}
                </span>
              </div>
            )}
          </div>
        )}
      </div>
    </figure>
  )
}
