import { describe, expect, it, vi } from 'vitest'
import {
  aggregateByPlace,
  matches,
  median,
  NO_FILTERS,
  quantileBreaks,
  unitPrice,
} from './aggregate'
import { nearestDefined, niceTicks } from './chart-scale'
import { formatCountShort, formatMan, formatManShort, formatRange, formatUnit } from './format'
import { contentsUrl, DataError, githubSource, isValidRepo, loadCategory } from './source'
import { decodeTable, LISTING_FIELDS, type Listing } from './types'

function listing(id: string, values: Partial<Listing> = {}): Listing {
  return {
    id, place: 0, area: '13101', name: null, price: 5000, price_max: null, size: 50,
    size_max: null, land: null, layout: null, built: null, station: null, walk: null,
    first_seen: null, price_changed: null, path: null, ...values,
  }
}

describe('filters and aggregation', () => {
  it('applies only the bounds that are set', () => {
    expect(matches(listing('a'), NO_FILTERS)).toBe(true)
    expect(matches(listing('a'), { ...NO_FILTERS, priceMin: 6000 })).toBe(false)
    expect(matches(listing('a'), { ...NO_FILTERS, priceMax: 5000, sizeMin: 50 })).toBe(true)
    // land-only listing has no size: it fails an active size bound but not a price bound
    const land = listing('b', { size: null })
    expect(matches(land, { ...NO_FILTERS, sizeMin: 10 })).toBe(false)
    expect(matches(land, { ...NO_FILTERS, priceMin: 1000 })).toBe(true)
    expect(matches(listing('c', { price: null }), { ...NO_FILTERS, priceMax: 9000 })).toBe(false)
  })

  it('computes unit price except for new condos', () => {
    expect(unitPrice(listing('a', { price: 6000, size: 60 }), 'used_condo')).toBe(100)
    expect(unitPrice(listing('a'), 'new_condo')).toBeNull()
    expect(unitPrice(listing('a', { size: null }), 'new_house')).toBeNull()
  })

  it('takes medians of odd and even groups', () => {
    expect(median([])).toBeNull()
    expect(median([3, 1, 2])).toBe(2)
    expect(median([4, 1, 3, 2])).toBe(2.5)
  })

  it('groups listings by place', () => {
    const stats = aggregateByPlace(
      [
        listing('a', { place: 2, price: 4000, size: 40 }),
        listing('b', { place: 2, price: 8000, size: 40 }),
        listing('c', { place: 1, price: null }),
        listing('d', { place: null }),
      ],
      'used_condo',
    )
    expect(stats).toEqual([
      { place: 1, count: 1, price: null, unit: null },
      { place: 2, count: 2, price: 6000, unit: 150 },
    ])
  })

  it('makes ascending distinct quantile breaks', () => {
    const values = Array.from({ length: 100 }, (_, i) => i + 1)
    expect(quantileBreaks(values, 4)).toEqual([26, 51, 76])
    expect(quantileBreaks([5, 5, 5, 5], 4)).toEqual([])
    expect(quantileBreaks([1, 1, 1, 9], 4)).toEqual([9])
    expect(quantileBreaks([], 4)).toEqual([])
  })
})

describe('formatting and scales', () => {
  it('formats 万円 and 億', () => {
    expect(formatMan(8950)).toBe('8,950万')
    expect(formatMan(13900)).toBe('1億3,900万')
    expect(formatMan(20000)).toBe('2億')
    expect(formatMan(null)).toBe('—')
    expect(formatManShort(15000)).toBe('1.5億')
    expect(formatManShort(8000)).toBe('8,000万')
    expect(formatUnit(135.24)).toBe('135.2万/m²')
    expect(formatCountShort(35000)).toBe('3.5万')
    expect(formatRange(3980, 4280, formatMan)).toBe('3,980万～4,280万')
    expect(formatRange(3980, null, formatMan)).toBe('3,980万')
  })

  it('makes nice ticks', () => {
    expect(niceTicks(0, 37109, 4)).toEqual([0, 10000, 20000, 30000, 40000])
    expect(niceTicks(4990, 12000, 4)).toEqual([4000, 6000, 8000, 10000, 12000])
    expect(niceTicks(5, 5, 4).length).toBeGreaterThan(1)
  })

  it('finds the nearest defined point', () => {
    expect(nearestDefined([0, 10, 20, 30], [1, null, 3, null], 12)).toBe(2)
    expect(nearestDefined([0, 10], [null, null], 5)).toBe(-1)
  })
})

describe('data source', () => {
  it('validates repository names and builds API URLs', () => {
    expect(isValidRepo('Imanity/suumoviz-data')).toBe(true)
    expect(isValidRepo('https://github.com/x/y')).toBe(false)
    expect(contentsUrl('a/b', 'listings/used_condo.json')).toBe(
      'https://api.github.com/repos/a/b/contents/listings/used_condo.json?ref=site',
    )
  })

  it('sends the token as a bearer header and maps HTTP errors', async () => {
    const fetchMock = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
      const headers = init?.headers as Record<string, string>
      if (headers.Authorization !== 'Bearer good') return new Response('', { status: 401 })
      if (String(url).includes('missing')) return new Response('', { status: 404 })
      return Response.json({ ok: true })
    })
    const source = githubSource('a/b', 'good', fetchMock as typeof fetch)
    await expect(source.get('meta.json')).resolves.toEqual({ ok: true })
    const init = fetchMock.mock.calls[0][1] as RequestInit
    expect((init.headers as Record<string, string>).Accept).toBe('application/vnd.github.raw+json')

    const missing = source.get('missing.json')
    await expect(missing).rejects.toBeInstanceOf(DataError)
    await expect(missing).rejects.toMatchObject({ status: 404, isAuth: true })
    const bad = githubSource('a/b', 'bad', fetchMock as typeof fetch)
    await expect(bad.get('meta.json')).rejects.toMatchObject({ status: 401 })
    expect(() => githubSource('not a repo', 't')).toThrow(DataError)
  })

  it('decodes tables and rejects unexpected formats', async () => {
    const fields = [...LISTING_FIELDS]
    const row = fields.map((f) => (f === 'id' ? '100' : null))
    const source = {
      label: 'test',
      get: async <T,>(path: string): Promise<T> =>
        (path.startsWith('listings/')
          ? { category: 'used_condo', fields, rows: [row] }
          : { category: 'used_condo', dates: [], series: {} }) as T,
    }
    const data = await loadCategory(source, 'used_condo')
    expect(data.listings[0].id).toBe('100')
    expect(() => decodeTable<Listing>({ fields: ['id'], rows: [] }, LISTING_FIELDS)).toThrow(
      /缺少字段/,
    )
  })
})
