/** The area summary built by `suumoviz build` (data/summary.dat, obfuscated JSON). */

import { decode } from './codec'

export const SUMMARY_FILE = 'data/summary.dat'
export const FORMAT_VERSION = 2
export const PREFECTURE = '13000'
/** Areas with fewer priced listings than this are shown as unreliable. */
export const MIN_SAMPLE = 5

export type CategoryKey = 'used_condo' | 'new_condo' | 'new_house' | 'used_house'
export type Metric = 'mean' | 'unit'

export interface AreaValue {
  code: string
  name: string
  lat: number | null
  lng: number | null
  count: number | null // on sale on the latest day (city pages)
  n: number // listings with a price behind the averages
  mean: number | null // 万円
  median: number | null // 万円
  unitMean: number | null // 万円/m²
}

export interface Category {
  key: CategoryKey
  label: string
  tokyo: AreaValue | null // all of Tokyo (13000)
  areas: AreaValue[] // municipalities and SUUMO area groups
}

export interface Summary {
  generatedAt: string
  firstDate: string
  latestDate: string
  sources: { listings: string; geo: string }
  categories: Category[]
}

interface Table {
  fields: string[]
  rows: unknown[][]
}

interface RawSummary {
  version: number
  generated_at: string
  first_date: string
  latest_date: string
  sources: { listings: string; geo: string }
  areas: Table
  categories: (Table & { key: CategoryKey; label: string })[]
}

function records(table: Table): Record<string, unknown>[] {
  return table.rows.map((row) => Object.fromEntries(table.fields.map((f, i) => [f, row[i]])))
}

const num = (value: unknown): number | null => (typeof value === 'number' ? value : null)

export function parseSummary(value: unknown): Summary {
  const raw = value as RawSummary
  if (raw?.version !== FORMAT_VERSION) {
    throw new Error(`数据版本不匹配（${String(raw?.version)}，需要 ${FORMAT_VERSION}）`)
  }
  const points = new Map(
    records(raw.areas).map((a) => [
      String(a.code),
      { name: String(a.name), lat: num(a.lat), lng: num(a.lng) },
    ]),
  )
  const categories = raw.categories.map((category): Category => {
    const values = records(category).map((r): AreaValue => {
      const code = String(r.area)
      const point = points.get(code)
      return {
        code,
        name: point?.name ?? code,
        lat: point?.lat ?? null,
        lng: point?.lng ?? null,
        count: num(r.count),
        n: num(r.n) ?? 0,
        mean: num(r.mean),
        median: num(r.median),
        unitMean: num(r.unit_mean),
      }
    })
    return {
      key: category.key,
      label: category.label,
      tokyo: values.find((v) => v.code === PREFECTURE) ?? null,
      areas: values.filter((v) => v.code !== PREFECTURE),
    }
  })
  return {
    generatedAt: raw.generated_at,
    firstDate: raw.first_date,
    latestDate: raw.latest_date,
    sources: raw.sources,
    categories,
  }
}

export async function loadSummary(base: string, fetchFn: typeof fetch = fetch): Promise<Summary> {
  // revalidate: the file changes once a day
  const response = await fetchFn(`${base}${SUMMARY_FILE}`, { cache: 'no-cache' })
  if (!response.ok) throw new Error(`读取数据失败（HTTP ${response.status}）`)
  return parseSummary(JSON.parse(decode(await response.text())))
}

/** 新築マンション has no unit price (its price ranges span units of different sizes). */
export function hasUnitPrice(category: CategoryKey): boolean {
  return category !== 'new_condo'
}

export function metricValue(area: AreaValue, metric: Metric): number | null {
  return metric === 'mean' ? area.mean : area.unitMean
}

/** Areas ordered by the metric, highest first; areas without a value last. */
export function ranked(areas: AreaValue[], metric: Metric): AreaValue[] {
  return [...areas].sort((a, b) => {
    const va = metricValue(a, metric)
    const vb = metricValue(b, metric)
    if (va === null || vb === null) return va === vb ? a.code.localeCompare(b.code) : va === null ? 1 : -1
    return vb - va || a.code.localeCompare(b.code)
  })
}

/**
 * Up to `bins - 1` ascending, distinct thresholds splitting `values` into equal-count
 * bins (a value v falls in bin i when breaks[i-1] <= v < breaks[i]).
 */
export function quantileBreaks(values: number[], bins: number): number[] {
  const sorted = values.filter(Number.isFinite).sort((a, b) => a - b)
  if (sorted.length === 0 || bins < 2) return []
  const breaks: number[] = []
  for (let i = 1; i < bins; i++) {
    const value = sorted[Math.min(sorted.length - 1, Math.floor((i * sorted.length) / bins))]
    if (value > sorted[0] && (breaks.length === 0 || value > breaks[breaks.length - 1])) {
      breaks.push(value)
    }
  }
  return breaks
}

/** Index of the bin `value` falls in (see quantileBreaks). */
export function binIndex(value: number, breaks: number[]): number {
  let i = 0
  while (i < breaks.length && value >= breaks[i]) i++
  return i
}
