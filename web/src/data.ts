/**
 * Web data built by `suumoviz build` (see src/suumoviz/build.py): obfuscated JSON files
 * under data/, decoded in the browser.
 *
 *   data/index.dat                        timeline, categories, all-Tokyo series
 *   data/day/{date}/{category}.dat        every area's values on one day (the map)
 *   data/history/{category}/{parent}.dat  series of the areas under `parent` (trends)
 */

import { decode } from './codec'

export const FORMAT_VERSION = 3
export const PREFECTURE = '13000'

export type CategoryKey = 'used_condo' | 'new_condo' | 'new_house' | 'used_house'
export type Level = 'city' | 'town' | 'chome'
export const LEVELS: Level[] = ['city', 'town', 'chome']
export const LEVEL_LABELS: Record<Level, string> = { city: '区市町村', town: '町・大字', chome: '丁目・字' }

/** Value fields in build order (VALUE_FIELDS). */
export interface Values {
  count: number // listings on sale
  n: number // with a price
  mean: number | null // 万円
  median: number | null
  unit_n: number // with one price and one floor area
  unit_mean: number | null // 万円/m²
  unit_median: number | null
}
const FIELDS: (keyof Values)[] = ['count', 'n', 'mean', 'median', 'unit_n', 'unit_mean', 'unit_median']

export type MetricKey = 'unit_mean' | 'unit_median' | 'mean' | 'median' | 'count'
export interface Metric {
  key: MetricKey
  label: string
  short: string
  kind: 'unit' | 'price' | 'count'
  sample: 'unit_n' | 'n' | 'count' // listings behind the value
}
export const METRICS: Metric[] = [
  { key: 'unit_mean', label: '单价 · 均价', short: '单价均价', kind: 'unit', sample: 'unit_n' },
  { key: 'unit_median', label: '单价 · 中位数', short: '单价中位数', kind: 'unit', sample: 'unit_n' },
  { key: 'mean', label: '总价 · 均价', short: '总价均价', kind: 'price', sample: 'n' },
  { key: 'median', label: '总价 · 中位数', short: '总价中位数', kind: 'price', sample: 'n' },
  { key: 'count', label: '在售套数', short: '在售套数', kind: 'count', sample: 'count' },
]

export function metricValue(values: Values | null | undefined, metric: MetricKey): number | null {
  if (!values) return null
  return values[metric]
}

export interface Category {
  key: CategoryKey
  label: string
  tokyo: (Values | null)[] // per date
  official: (number | null)[] // SUUMO's own count of all Tokyo, per date
}

export interface Index {
  generatedAt: string
  firstDate: string
  latestDate: string
  complete: boolean // the timeline starts after a full 7-day rotation
  dates: string[]
  graceDays: number
  minSample: number
  sources: { listings: string; geo: string; boundaries: string }
  categories: Category[]
}

/** code → values, one category on one day (all levels; not 13000). */
export type DayTable = Map<string, Values>

/** code → values per index date, the areas under one parent. */
export type History = Map<string, (Values | null)[]>

function toValues(row: unknown[] | null, fields: string[], offset = 0): Values | null {
  if (!row) return null
  const out: Record<string, unknown> = {}
  fields.forEach((field, i) => {
    out[field] = row[i + offset]
  })
  const values = out as unknown as Values
  for (const field of FIELDS) {
    if (!(field in out)) throw new Error(`数据缺少字段 ${field}`)
  }
  return values
}

interface RawIndex {
  version: number
  generated_at: string
  first_date: string
  latest_date: string
  complete: boolean
  dates: string[]
  grace_days: number
  min_sample: number
  sources: Index['sources']
  fields: string[]
  categories: { key: CategoryKey; label: string; tokyo: (unknown[] | null)[]; official: (number | null)[] }[]
}

export function parseIndex(value: unknown): Index {
  const raw = value as RawIndex
  if (raw?.version !== FORMAT_VERSION) {
    throw new Error(`数据版本不匹配（${String(raw?.version)}，需要 ${FORMAT_VERSION}）`)
  }
  return {
    generatedAt: raw.generated_at,
    firstDate: raw.first_date,
    latestDate: raw.latest_date,
    complete: raw.complete,
    dates: raw.dates,
    graceDays: raw.grace_days,
    minSample: raw.min_sample,
    sources: raw.sources,
    categories: raw.categories.map((c) => ({
      key: c.key,
      label: c.label,
      tokyo: c.tokyo.map((row) => toValues(row, raw.fields)),
      official: c.official,
    })),
  }
}

export function parseDay(value: unknown): DayTable {
  const raw = value as { fields: string[]; rows: unknown[][] }
  const fields = raw.fields.slice(1) // "code" first
  return new Map(raw.rows.map((row) => [String(row[0]), toValues(row, fields, 1)!]))
}

export function parseHistory(value: unknown): History {
  const raw = value as { fields: string[]; series: Record<string, (unknown[] | null)[]> }
  return new Map(
    Object.entries(raw.series).map(([code, rows]) => [code, rows.map((r) => toValues(r, raw.fields))]),
  )
}

async function fetchDecoded(url: string, fetchFn: typeof fetch): Promise<unknown> {
  // revalidate: files change once a day
  const response = await fetchFn(url, { cache: 'no-cache' })
  if (!response.ok) throw new Error(`读取数据失败（HTTP ${response.status}）`)
  return JSON.parse(decode(await response.text()))
}

export async function loadIndex(base: string, fetchFn: typeof fetch = fetch): Promise<Index> {
  return parseIndex(await fetchDecoded(`${base}data/index.dat`, fetchFn))
}

export async function loadDay(
  base: string,
  date: string,
  category: CategoryKey,
  fetchFn: typeof fetch = fetch,
): Promise<DayTable> {
  return parseDay(await fetchDecoded(`${base}data/day/${date}/${category}.dat`, fetchFn))
}

/** The history file holding `code`'s series; resolves to an empty history when missing. */
export async function loadHistory(
  base: string,
  category: CategoryKey,
  code: string,
  fetchFn: typeof fetch = fetch,
): Promise<History> {
  const response = await fetchFn(`${base}data/history/${category}/${parentOf(code)}.dat`, {
    cache: 'no-cache',
  })
  if (response.status === 404) return new Map()
  if (!response.ok) throw new Error(`读取数据失败（HTTP ${response.status}）`)
  return parseHistory(JSON.parse(decode(await response.text())))
}

export function levelOf(code: string): Level | null {
  return code.length === 5 && code !== PREFECTURE
    ? 'city'
    : code.length === 9
      ? 'town'
      : code.length === 11
        ? 'chome'
        : null
}

/** 13000 for a municipality, the municipality for a town, the town for a chome. */
export function parentOf(code: string): string {
  return code.length === 11 ? code.slice(0, 9) : code.length === 9 ? code.slice(0, 5) : PREFECTURE
}

/** The codes from the municipality down to `code` (13000 not included). */
export function lineage(code: string): string[] {
  return [5, 9, 11].filter((n) => n <= code.length).map((n) => code.slice(0, n))
}

/** Map level for a zoom: municipalities, towns from 11, chome from 13. */
export const LEVEL_ZOOMS: Record<Level, number> = { city: 0, town: 11, chome: 13 }
export function levelForZoom(zoom: number): Level {
  return zoom >= LEVEL_ZOOMS.chome ? 'chome' : zoom >= LEVEL_ZOOMS.town ? 'town' : 'city'
}

export type ScaleMode = 'quantile' | 'linear'

export interface ColorStop {
  value: number
  index: number // position on the color ramp, 0 … count - 1
}

function quantile(sorted: number[], p: number): number {
  const i = p * (sorted.length - 1)
  const lo = Math.floor(i)
  const hi = Math.ceil(i)
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (i - lo)
}

/**
 * Where the `count` colors of a continuous ramp sit, ascending and distinct (colors in
 * between are interpolated):
 *
 * - `quantile`: at evenly spaced quantiles, so every color covers as many areas;
 * - `linear`: evenly spaced in value from the 2nd to the 98th percentile (values beyond
 *   take the end colors), so equal value steps look equally different.
 */
export function colorStops(values: number[], count: number, mode: ScaleMode): ColorStop[] {
  const sorted = values.filter(Number.isFinite).sort((a, b) => a - b)
  if (sorted.length === 0) return []
  if (count < 2) return [{ value: sorted[0], index: 0 }]
  const lo = quantile(sorted, mode === 'quantile' ? 0 : 0.02)
  const hi = quantile(sorted, mode === 'quantile' ? 1 : 0.98)
  const stops: ColorStop[] = []
  for (let index = 0; index < count; index++) {
    const t = index / (count - 1)
    const value = mode === 'quantile' ? quantile(sorted, t) : lo + (hi - lo) * t
    if (stops.length === 0 || value > stops[stops.length - 1].value) stops.push({ value, index })
  }
  return stops
}

export interface Ranked {
  code: string
  values: Values
  value: number | null
}

/** Areas of one level ordered by the metric, highest first; areas without a value last. */
export function ranked(table: DayTable, level: Level, metric: MetricKey, keep?: (code: string) => boolean): Ranked[] {
  const rows: Ranked[] = []
  for (const [code, values] of table) {
    if (levelOf(code) === level && (!keep || keep(code))) {
      rows.push({ code, values, value: metricValue(values, metric) })
    }
  }
  return rows.sort((a, b) => {
    if (a.value === null || b.value === null) {
      return a.value === b.value ? a.code.localeCompare(b.code) : a.value === null ? 1 : -1
    }
    return b.value - a.value || a.code.localeCompare(b.code)
  })
}
