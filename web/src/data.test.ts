import { describe, expect, it } from 'vitest'
import { decode, MAGIC } from './codec'
import { niceTicks } from './components/TrendChart'
import {
  binIndex,
  levelForZoom,
  levelOf,
  lineage,
  loadDay,
  loadHistory,
  loadIndex,
  METRICS,
  parentOf,
  parseDay,
  parseIndex,
  quantileBreaks,
  ranked,
} from './data'
import {
  formatCount,
  formatDay,
  formatMan,
  formatManShort,
  formatMetric,
  formatMetricShort,
  formatUnit,
} from './format'
import { displayName, parseAreas } from './geo'

// suumoviz.codec.encode('価格,8950\n東京都\n'.encode()) from the Python package
const PYTHON_VECTOR = '#suumoviz-obf/1\nhwKf6N1Sk6XoMbY=\nhSGP6sdCVh5s\n'

const FIELDS = ['count', 'n', 'mean', 'median', 'unit_n', 'unit_mean', 'unit_median']

const INDEX = {
  version: 3,
  generated_at: '2026-11-19T08:00:00+09:00',
  first_date: '2026-11-07',
  latest_date: '2026-11-19',
  complete: true,
  dates: ['2026-11-18', '2026-11-19'],
  grace_days: 9,
  min_sample: 3,
  units: { price: '万円', unit: '万円/m²' },
  sources: { listings: 'SUUMO', geo: '国土交通省', boundaries: 'e-Stat' },
  fields: FIELDS,
  categories: [
    {
      key: 'used_condo',
      label: '中古マンション',
      tokyo: [null, [10, 9, 7500, 6500, 8, 150.5, 140]],
      official: [null, 11],
    },
  ],
}

const DAY = {
  date: '2026-11-19',
  category: 'used_condo',
  fields: ['code', ...FIELDS],
  rows: [
    ['13101', 5, 5, 9000, 7000, 5, 180, 170],
    ['13113', 4, 3, 3000, 3000, 2, null, null],
    ['131010050', 5, 5, 9000, 7000, 5, 180, 170],
    ['13101005001', 3, 3, 8000, 8000, 3, 160, 160],
    ['13101005002', 2, 2, null, null, 2, null, null],
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

function fakeFetch(files: Record<string, unknown>, requested: string[] = []): typeof fetch {
  return (async (url: string) => {
    requested.push(url)
    return url in files
      ? new Response(encode(JSON.stringify(files[url])))
      : new Response('', { status: 404 })
  }) as typeof fetch
}

describe('codec', () => {
  it('decodes what the Python package encodes', () => {
    expect(decode(PYTHON_VECTOR)).toBe('価格,8950\n東京都\n')
    expect(encode('価格,8950\n東京都\n')).toBe(PYTHON_VECTOR)
  })

  it('accepts CRLF checkouts and rejects other files', () => {
    expect(decode(PYTHON_VECTOR.replaceAll('\n', '\r\n'))).toBe('価格,8950\n東京都\n')
    expect(() => decode('{"version":3}')).toThrow('格式不正确')
    expect(() => decode(`${MAGIC}\n!!!`)).toThrow()
  })
})

describe('index and day files', () => {
  it('parses the index', () => {
    const index = parseIndex(INDEX)
    expect(index.dates).toEqual(['2026-11-18', '2026-11-19'])
    expect(index.minSample).toBe(3)
    const [condo] = index.categories
    expect(condo.tokyo[0]).toBeNull()
    expect(condo.tokyo[1]).toEqual({
      count: 10, n: 9, mean: 7500, median: 6500, unit_n: 8, unit_mean: 150.5, unit_median: 140,
    })
    expect(condo.official).toEqual([null, 11])
  })

  it('refuses another format version', () => {
    expect(() => parseIndex({ ...INDEX, version: 2 })).toThrow('版本')
  })

  it('ranks one level by the metric, missing values last', () => {
    const day = parseDay(DAY)
    expect(day.get('13113')).toMatchObject({ count: 4, mean: 3000, unit_mean: null })
    expect(ranked(day, 'city', 'mean').map((r) => r.code)).toEqual(['13101', '13113'])
    expect(ranked(day, 'city', 'unit_mean').map((r) => [r.code, r.value])).toEqual([
      ['13101', 180],
      ['13113', null],
    ])
    expect(ranked(day, 'chome', 'count').map((r) => r.code)).toEqual(['13101005001', '13101005002'])
    expect(ranked(day, 'chome', 'mean', (c) => c.endsWith('2')).map((r) => r.code)).toEqual([
      '13101005002',
    ])
  })

  it('loads index, day and history files', async () => {
    const requested: string[] = []
    const fetchFn = fakeFetch(
      {
        '/suumoviz/data/index.dat': INDEX,
        '/suumoviz/data/day/2026-11-19/used_condo.dat': DAY,
        '/suumoviz/data/history/used_condo/131010050.dat': {
          fields: FIELDS,
          series: { '13101005001': [null, [3, 3, 8000, 8000, 3, 160, 160]] },
        },
      },
      requested,
    )
    expect((await loadIndex('/suumoviz/', fetchFn)).latestDate).toBe('2026-11-19')
    expect((await loadDay('/suumoviz/', '2026-11-19', 'used_condo', fetchFn)).size).toBe(5)
    const history = await loadHistory('/suumoviz/', 'used_condo', '13101005001', fetchFn)
    expect(history.get('13101005001')?.[1]?.mean).toBe(8000)
    // no file: the areas under that parent have no listings
    expect((await loadHistory('/suumoviz/', 'new_condo', '13101', fetchFn)).size).toBe(0)
    expect(requested).toContain('/suumoviz/data/history/new_condo/13000.dat')
    await expect(loadDay('/', '2026-01-01', 'used_condo', fetchFn)).rejects.toThrow('HTTP 404')
  })
})

describe('area codes', () => {
  it('knows levels and parents', () => {
    expect(['13000', '13101', '131010050', '13101005001', 'x'].map(levelOf)).toEqual([
      null, 'city', 'town', 'chome', null,
    ])
    expect(parentOf('13101005001')).toBe('131010050')
    expect(parentOf('131010050')).toBe('13101')
    expect(parentOf('13101')).toBe('13000')
    expect(lineage('13101005001')).toEqual(['13101', '131010050', '13101005001'])
    expect([9, 10.9, 11, 12.9, 13, 16].map(levelForZoom)).toEqual([
      'city', 'city', 'town', 'town', 'chome', 'chome',
    ])
  })
})

describe('boundaries', () => {
  // two unit squares sharing the arc x = 140 (quantized, delta-encoded)
  const TOPOLOGY = {
    type: 'Topology',
    transform: { scale: [0.5, 0.5], translate: [139, 35] },
    arcs: [
      [[2, 0], [0, 2]], // shared edge (140,35)→(140,36)
      [[2, 2], [-2, 0], [0, -2], [2, 0]], // the rest of the left square
      [[2, 0], [2, 0], [0, 2], [-2, 0]], // the rest of the right square
    ],
    objects: {
      city: {
        type: 'GeometryCollection',
        geometries: [{ type: 'Polygon', arcs: [[1, 2]], properties: { id: '13101', name: '千代田区' } }],
      },
      town: {
        type: 'GeometryCollection',
        geometries: [
          { type: 'Polygon', arcs: [[0, 1]], properties: { id: '131010050', name: '霞が関' } },
          { type: 'Polygon', arcs: [[2, -1]], properties: { id: '131010060', name: '永田町' } },
        ],
      },
      chome: {
        type: 'GeometryCollection',
        geometries: [
          {
            type: 'MultiPolygon',
            arcs: [[[0, 1]]],
            properties: { id: '13101005001', name: '霞が関一丁目' },
          },
          { type: null, properties: { id: '13101005009', name: 'empty' } },
        ],
      },
    },
  }

  it('decodes the topology into features and boxes', () => {
    const areas = parseAreas(TOPOLOGY)
    const [left, right] = areas.features.town.features
    expect(left.geometry.coordinates).toEqual([
      [[140, 35], [140, 36], [139, 36], [139, 35], [140, 35]],
    ])
    expect(right.geometry.coordinates).toEqual([
      [[140, 35], [141, 35], [141, 36], [140, 36], [140, 35]],
    ])
    expect(areas.features.chome.features).toHaveLength(1)
    expect(areas.info.get('131010060')).toMatchObject({ level: 'town', bbox: [140, 35, 141, 36] })
    expect(displayName('13101005001', areas.info)).toBe('千代田区 霞が関一丁目')
    expect(displayName('13101', areas.info)).toBe('千代田区')
    expect(() => parseAreas({})).toThrow('格式')
  })
})

describe('bins, ticks and formats', () => {
  it('splits values into equal-count bins', () => {
    expect(quantileBreaks([1, 2, 3, 4, 5, 6, 7, 8], 4)).toEqual([3, 5, 7])
    expect(quantileBreaks([5, 5, 5], 4)).toEqual([])
    expect(quantileBreaks([], 4)).toEqual([])
    expect([0, 3, 4, 7, 9].map((v) => binIndex(v, [3, 5, 7]))).toEqual([0, 1, 1, 3, 3])
  })

  it('picks round axis ticks', () => {
    expect(niceTicks(0, 100, 4)).toEqual([0, 50, 100])
    expect(niceTicks(152.3, 158.9, 4)).toEqual([154, 156, 158])
    expect(niceTicks(5, 5)).toEqual([5])
  })

  it('formats prices, counts and dates', () => {
    expect(formatMan(8950)).toBe('8,950万')
    expect(formatMan(13900)).toBe('1億3,900万')
    expect(formatMan(20000)).toBe('2億')
    expect(formatMan(null)).toBe('—')
    expect(formatManShort(15000)).toBe('1.5億')
    expect(formatUnit(180)).toBe('180万/m²')
    expect(formatCount(36894)).toBe('36,894')
    const [unit, , price, , count] = METRICS
    expect(formatMetric(unit, 185.34)).toBe('185.3万/m²')
    expect(formatMetric(price, 12000)).toBe('1億2,000万')
    expect(formatMetric(count, 1234)).toBe('1,234套')
    expect(formatMetric(count, null)).toBe('—')
    expect(formatMetricShort(unit, 185.34)).toBe('185.3')
    expect(formatDay('2026-11-09')).toBe('11/9')
  })
})
