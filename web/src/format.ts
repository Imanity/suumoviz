/** Display formats. Prices are in 万円 throughout. */

import type { Metric } from './data'

const integer = new Intl.NumberFormat('ja-JP', { maximumFractionDigits: 0 })
const oneDecimal = new Intl.NumberFormat('ja-JP', { maximumFractionDigits: 1 })

/** 8950 → "8,950万", 13900 → "1億3,900万", 20000 → "2億". */
export function formatMan(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  const rounded = Math.round(value)
  if (rounded < 10_000) return `${integer.format(rounded)}万`
  const oku = Math.floor(rounded / 10_000)
  const man = rounded % 10_000
  return man === 0 ? `${oku}億` : `${oku}億${integer.format(man)}万`
}

/** Legend and axis labels: 8000 → "8,000万", 15000 → "1.5億". */
export function formatManShort(value: number): string {
  return value >= 10_000 ? `${oneDecimal.format(value / 10_000)}億` : `${integer.format(value)}万`
}

export function formatUnit(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : `${oneDecimal.format(value)}万/m²`
}

export function formatCount(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : integer.format(value)
}

/** A value of `metric` in full: "1億2,000万", "185.3万/m²", "1,234套". */
export function formatMetric(metric: Metric, value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  if (metric.kind === 'price') return formatMan(value)
  if (metric.kind === 'unit') return formatUnit(value)
  return `${formatCount(value)}套`
}

/** Short form for legends and axes: "1.2億", "185.5", "1,234". */
export function formatMetricShort(metric: Metric, value: number): string {
  if (metric.kind === 'price') return formatManShort(value)
  return metric.kind === 'unit' ? oneDecimal.format(value) : integer.format(value)
}

export function metricUnit(metric: Metric): string {
  return metric.kind === 'price' ? '万円' : metric.kind === 'unit' ? '万円/m²' : '套'
}

/** "2026-11-19" → "11/19". */
export function formatDay(date: string): string {
  const [, month, day] = date.split('-')
  return `${Number(month)}/${Number(day)}`
}
