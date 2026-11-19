import { describe, expect, it } from 'vitest'
import { decode, MAGIC } from './codec'
import { formatCount, formatMan, formatManShort, formatUnit } from './format'
import {
  binIndex,
  hasUnitPrice,
  loadSummary,
  parseSummary,
  quantileBreaks,
  ranked,
  type AreaValue,
} from './summary'

// suumoviz.codec.encode('価格,8950\n東京都\n'.encode()) from the Python package
const PYTHON_VECTOR = '#suumoviz-obf/1\nhwKf6N1Sk6XoMbY=\nhSGP6sdCVh5s\n'

const RAW = {
  version: 2,
  generated_at: '2026-11-19T08:00:00+09:00',
  first_date: '2026-11-07',
  latest_date: '2026-11-18',
  units: { price: '万円', unit: '万円/m²' },
  sources: { listings: 'SUUMO', geo: '国土交通省' },
  areas: {
    fields: ['code', 'name', 'lat', 'lng'],
    rows: [
      ['13000', '東京都', 35.69, 139.5],
      ['13101', '千代田区', 35.69, 139.75],
      ['13113', '渋谷区', 35.66, 139.69],
      ['13363', '新島村', null, null],
    ],
  },
  categories: [
    {
      key: 'used_condo',
      label: '中古マンション',
      fields: ['area', 'count', 'n', 'mean', 'median', 'unit_mean'],
      rows: [
        ['13000', 1092, 4, 7500, 6500, 165],
        ['13101', 691, 3, 9000, 7000, 180],
        ['13113', 401, 1, 3000, 3000, 120],
        ['13363', 0, 1, null, null, null],
      ],
    },
    { key: 'new_condo', label: '新築マンション', fields: ['area'], rows: [] },
  ],
}

/** The same encoding as the Python package, for building fixtures. */
function encode(text: string): string {
  const key = Uint8Array.from(
    '63bc3e0e7deebf9dd10486861648bc76c358fc9f09facb0664109292fe499ace'.match(/../g)!,
    (h) => parseInt(h, 16),
  )
  const lines = text.split('\n').map((line) => {
    const bytes = new TextEncoder().encode(line)
    let binary = ''
    bytes.forEach((b, i) => (binary += String.fromCharCode(b ^ key[i % key.length])))
    return btoa(binary)
  })
  return [MAGIC, ...lines].join('\n')
}

describe('codec', () => {
  it('decodes what the Python package encodes', () => {
    expect(decode(PYTHON_VECTOR)).toBe('価格,8950\n東京都\n')
    expect(encode('価格,8950\n東京都\n')).toBe(PYTHON_VECTOR)
  })

  it('accepts CRLF checkouts and rejects other files', () => {
    expect(decode(PYTHON_VECTOR.replaceAll('\n', '\r\n'))).toBe('価格,8950\n東京都\n')
    expect(() => decode('{"version":2}')).toThrow('格式不正确')
    expect(() => decode(`${MAGIC}\n!!!`)).toThrow()
  })
})

describe('summary', () => {
  it('joins values to area names and points', () => {
    const summary = parseSummary(RAW)
    expect(summary.latestDate).toBe('2026-11-18')
    const [condo, newCondo] = summary.categories
    expect(condo.tokyo).toMatchObject({ code: '13000', count: 1092, mean: 7500, median: 6500 })
    expect(condo.areas.map((a) => a.code)).toEqual(['13101', '13113', '13363'])
    expect(condo.areas[0]).toEqual({
      code: '13101', name: '千代田区', lat: 35.69, lng: 139.75,
      count: 691, n: 3, mean: 9000, median: 7000, unitMean: 180,
    })
    expect(condo.areas[2]).toMatchObject({ name: '新島村', lat: null, mean: null })
    expect(newCondo).toMatchObject({ key: 'new_condo', tokyo: null, areas: [] })
  })

  it('refuses another format version', () => {
    expect(() => parseSummary({ ...RAW, version: 1 })).toThrow('版本')
  })

  it('ranks by the metric, missing values last', () => {
    const { areas } = parseSummary(RAW).categories[0]
    const extra: AreaValue = { ...areas[1], code: '13200', mean: 3000, unitMean: 200 }
    expect(ranked([...areas, extra], 'mean').map((a) => a.code)).toEqual([
      '13101', '13113', '13200', '13363',
    ])
    expect(ranked([...areas, extra], 'unit').map((a) => a.code)).toEqual([
      '13200', '13101', '13113', '13363',
    ])
    expect(hasUnitPrice('new_condo')).toBe(false)
    expect(hasUnitPrice('used_house')).toBe(true)
  })

  it('loads and decodes the summary file', async () => {
    const requested: string[] = []
    const fake = (async (url: string) => {
      requested.push(url)
      return new Response(encode(JSON.stringify(RAW)))
    }) as typeof fetch
    const summary = await loadSummary('/suumoviz/', fake)
    expect(requested).toEqual(['/suumoviz/data/summary.dat'])
    expect(summary.categories[0].areas).toHaveLength(3)

    const missing = (async () => new Response('', { status: 404 })) as unknown as typeof fetch
    await expect(loadSummary('/', missing)).rejects.toThrow('HTTP 404')
  })
})

describe('color bins', () => {
  it('splits values into equal-count bins', () => {
    expect(quantileBreaks([1, 2, 3, 4, 5, 6, 7, 8], 4)).toEqual([3, 5, 7])
    expect(quantileBreaks([5, 5, 5], 4)).toEqual([])
    expect(quantileBreaks([], 4)).toEqual([])
    expect([0, 3, 4, 7, 9].map((v) => binIndex(v, [3, 5, 7]))).toEqual([0, 1, 1, 3, 3])
  })
})

describe('format', () => {
  it('formats prices and counts', () => {
    expect(formatMan(8950)).toBe('8,950万')
    expect(formatMan(13900)).toBe('1億3,900万')
    expect(formatMan(20000)).toBe('2億')
    expect(formatMan(null)).toBe('—')
    expect(formatManShort(15000)).toBe('1.5億')
    expect(formatUnit(180)).toBe('180万/m²')
    expect(formatCount(36894)).toBe('36,894')
  })
})
