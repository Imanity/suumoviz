/** Shapes of the JSON written by `suumoviz build` (suumoviz-data, format version 1). */

export const FORMAT_VERSION = 1

export type CategoryKey = 'used_condo' | 'new_condo' | 'new_house' | 'used_house'

export interface Table {
  fields: string[]
  rows: unknown[][]
}

export interface Meta {
  version: number
  generated_at: string
  latest_date: string
  first_date: string
  steady_from: string
  cycle_days: number
  prefecture_area: string
  categories: { key: CategoryKey; label: string; listings: number }[]
  precision: Record<string, number>
  sources: { listings: string; geo: string }
  runs: Table
}

export interface Area {
  code: string
  name: string
  lat: number | null
  lng: number | null
}

export type Precision = 'chome' | 'town' | 'city'

export interface Place {
  id: string
  name: string
  city: string
  lat: number
  lng: number
  precision: Precision
}

export interface Listing {
  id: string
  place: number | null
  area: string
  name: string | null
  price: number | null // 万円
  price_max: number | null
  size: number | null // m²
  size_max: number | null
  land: number | null
  layout: string | null
  built: string | null
  station: string | null
  walk: number | null
  first_seen: string | null
  price_changed: string | null
  path: string | null
}

export type Values = (number | null)[]

export interface Series {
  count: Values
  n: Values
  p25: Values
  median: Values
  p75: Values
  unit: Values
  new: Values
  price_change: Values
  delisted: Values
  relisted: Values
}

export interface Trends {
  category: CategoryKey
  dates: string[]
  series: Record<string, Series>
}

export interface Dataset {
  meta: Meta
  areas: Area[]
  places: Place[]
}

export interface CategoryData {
  listings: Listing[]
  trends: Trends
}

/** Turn a {"fields", "rows"} table into objects, checking that expected fields exist. */
export function decodeTable<T>(table: Table, required: readonly (keyof T & string)[]): T[] {
  const missing = required.filter((f) => !table.fields.includes(f))
  if (missing.length > 0) {
    throw new Error(`数据格式不符：缺少字段 ${missing.join(', ')}`)
  }
  return table.rows.map((row) => {
    const item: Record<string, unknown> = {}
    table.fields.forEach((field, i) => {
      item[field] = row[i]
    })
    return item as T
  })
}

export const LISTING_FIELDS = [
  'id', 'place', 'area', 'name', 'price', 'price_max', 'size', 'size_max', 'land', 'layout',
  'built', 'station', 'walk', 'first_seen', 'price_changed', 'path',
] as const satisfies readonly (keyof Listing)[]

export const PLACE_FIELDS = [
  'id', 'name', 'city', 'lat', 'lng', 'precision',
] as const satisfies readonly (keyof Place)[]

export const AREA_FIELDS = ['code', 'name', 'lat', 'lng'] as const satisfies readonly (keyof Area)[]
