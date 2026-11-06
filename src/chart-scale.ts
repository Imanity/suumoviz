/** Clean, evenly spaced axis ticks covering [min, max] (about `count` intervals). */
export function niceTicks(min: number, max: number, count = 4): number[] {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return []
  if (min === max) {
    const pad = Math.abs(min) * 0.1 || 1
    min = min - pad
    max = max + pad
  }
  const raw = (max - min) / count
  const magnitude = 10 ** Math.floor(Math.log10(raw))
  const normalized = raw / magnitude
  const step = (normalized < 1.5 ? 1 : normalized < 3 ? 2 : normalized < 7 ? 5 : 10) * magnitude
  const start = Math.floor(min / step) * step
  const end = Math.ceil(max / step) * step
  const ticks: number[] = []
  for (let value = start; value <= end + step / 2; value += step) {
    ticks.push(Number(value.toPrecision(12)))
  }
  return ticks
}

export const DAY_MS = 86_400_000

export function dayValue(iso: string): number {
  return Date.parse(`${iso}T00:00:00Z`)
}

/** Index of the defined value whose date is closest to `time`. */
export function nearestDefined(times: number[], values: (number | null)[], time: number): number {
  let best = -1
  let bestDistance = Infinity
  values.forEach((value, i) => {
    if (value === null) return
    const distance = Math.abs(times[i] - time)
    if (distance < bestDistance) {
      best = i
      bestDistance = distance
    }
  })
  return best
}
