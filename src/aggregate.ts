import type { CategoryKey, Listing } from './types'

export interface Filters {
  priceMin: number | null // 万円
  priceMax: number | null
  sizeMin: number | null // m²
  sizeMax: number | null
}

export const NO_FILTERS: Filters = { priceMin: null, priceMax: null, sizeMin: null, sizeMax: null }

export type Metric = 'price' | 'unit'

/** A bound only applies when set; a listing without the value fails an active bound. */
function within(value: number | null, min: number | null, max: number | null): boolean {
  if (min === null && max === null) return true
  if (value === null) return false
  return (min === null || value >= min) && (max === null || value <= max)
}

export function matches(listing: Listing, filters: Filters): boolean {
  return (
    within(listing.price, filters.priceMin, filters.priceMax) &&
    within(listing.size, filters.sizeMin, filters.sizeMax)
  )
}

/** 万円/m². New condo prices and areas are ranges over different units, so none there. */
export function unitPrice(listing: Listing, category: CategoryKey): number | null {
  if (category === 'new_condo' || listing.price === null || !listing.size) return null
  return listing.price / listing.size
}

export function median(values: number[]): number | null {
  if (values.length === 0) return null
  const sorted = [...values].sort((a, b) => a - b)
  const mid = Math.floor(sorted.length / 2)
  return sorted.length % 2 === 1 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2
}

export interface PlaceStat {
  place: number
  count: number
  price: number | null // median 万円
  unit: number | null // median 万円/m²
}

export function aggregateByPlace(listings: Listing[], category: CategoryKey): PlaceStat[] {
  const groups = new Map<number, Listing[]>()
  for (const listing of listings) {
    if (listing.place === null) continue
    const group = groups.get(listing.place)
    if (group) group.push(listing)
    else groups.set(listing.place, [listing])
  }
  return [...groups.entries()]
    .sort(([a], [b]) => a - b)
    .map(([place, group]) => ({
      place,
      count: group.length,
      price: median(group.flatMap((l) => (l.price === null ? [] : [l.price]))),
      unit: median(
        group.flatMap((l) => {
          const unit = unitPrice(l, category)
          return unit === null ? [] : [unit]
        }),
      ),
    }))
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

export function metricValue(stat: PlaceStat, metric: Metric): number | null {
  return metric === 'price' ? stat.price : stat.unit
}
