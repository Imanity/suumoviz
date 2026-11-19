import {
  AttributionControl,
  type ExpressionSpecification,
  type GeoJSONSource,
  Map as MapLibreMap,
  NavigationControl,
  Popup,
  type StyleSpecification,
} from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { useEffect, useRef, useState } from 'react'
import { formatCount, formatMan, formatManShort, formatUnit } from '../format'
import { type AreaValue, type Metric, metricValue, MIN_SAMPLE } from '../summary'

// Sequential blue (one hue, light → dark). Kept off the lightest steps so small values
// still read on the pale base map.
export const RAMP = ['#9ec5f4', '#6da7ec', '#3987e5', '#2a78d6', '#256abf', '#184f95', '#0d366b']
export const MISSING = '#898781'

const GSI_ATTRIBUTION =
  '<a href="https://maps.gsi.go.jp/development/ichiran.html" target="_blank" rel="noopener noreferrer">地理院タイル</a>'
const GEO_ATTRIBUTION = '位置参照情報 国土交通省'

const STYLE: StyleSpecification = {
  version: 8,
  sources: {
    gsi: {
      type: 'raster',
      tiles: ['https://cyberjapandata.gsi.go.jp/xyz/pale/{z}/{x}/{y}.png'],
      tileSize: 256,
      minzoom: 5,
      maxzoom: 18,
      attribution: GSI_ATTRIBUTION,
    },
  },
  layers: [{ id: 'gsi', type: 'raster', source: 'gsi' }],
}

// circle size = listings on sale (square root, so area tracks the count); `zoom` may only
// appear in a top-level interpolate, so the selection ring gets its own expression
function radius(extra = 0): ExpressionSpecification {
  return [
    'interpolate', ['linear'], ['zoom'],
    9, ['+', 4 + extra, ['*', 0.22, ['sqrt', ['get', 'count']]]],
    13, ['+', 8 + extra, ['*', 0.6, ['sqrt', ['get', 'count']]]],
  ]
}

/** Colors for `bins` bins, spread over the ramp. */
export function binColors(bins: number): string[] {
  if (bins <= 1) return [RAMP[3]]
  return Array.from({ length: bins }, (_, k) => RAMP[Math.round((k * (RAMP.length - 1)) / (bins - 1))])
}

function colorExpression(breaks: number[]): ExpressionSpecification {
  const colors = binColors(breaks.length + 1)
  const step: unknown[] = ['step', ['get', 'v'], colors[0]]
  breaks.forEach((b, i) => step.push(b, colors[i + 1]))
  return [
    'case',
    ['<', ['get', 'v'], 0],
    MISSING,
    breaks.length ? (step as ExpressionSpecification) : colors[0],
  ]
}

function popupContent(area: AreaValue, metric: Metric): HTMLElement {
  // area names are data: build text nodes, never innerHTML
  const node = document.createElement('div')
  const title = document.createElement('strong')
  title.textContent = area.name
  node.append(title)
  const lines = [
    metric === 'mean'
      ? `均价 ${formatMan(area.mean)}（中位 ${formatMan(area.median)}）`
      : `单价均价 ${formatUnit(area.unitMean)}`,
    `在售 ${formatCount(area.count)} 套 · 统计 ${formatCount(area.n)} 套`,
  ]
  if (area.n < MIN_SAMPLE) lines.push('样本少，仅供参考')
  for (const text of lines) {
    const line = document.createElement('div')
    line.textContent = text
    node.append(line)
  }
  return node
}

interface Props {
  areas: AreaValue[]
  metric: Metric
  breaks: number[]
  selected: string | null
  onSelect: (code: string | null) => void
}

export function MapView({ areas, metric, breaks, selected, onSelect }: Props) {
  const container = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MapLibreMap | null>(null)
  const [ready, setReady] = useState(false)
  // event handlers are bound once; read the latest props through refs
  const latest = useRef({ areas, metric, onSelect })
  latest.current = { areas, metric, onSelect }

  useEffect(() => {
    if (!container.current) return
    const map = new MapLibreMap({
      container: container.current,
      style: STYLE,
      // mainland Tokyo: Tama in the west to Edogawa in the east
      bounds: [
        [139.1, 35.5],
        [139.92, 35.83],
      ],
      fitBoundsOptions: { padding: 12 },
      // on touch screens one finger scrolls the page; two fingers move the map
      cooperativeGestures: window.matchMedia('(pointer: coarse)').matches,
      locale: {
        'CooperativeGesturesHandler.MobileHelpText': '用两根手指移动地图',
        'CooperativeGesturesHandler.WindowsHelpText': '按住 Ctrl 并滚动来缩放地图',
        'CooperativeGesturesHandler.MacHelpText': '按住 ⌘ 并滚动来缩放地图',
      },
      minZoom: 7,
      maxZoom: 16,
      attributionControl: false,
      dragRotate: false,
      pitchWithRotate: false,
    })
    map.touchZoomRotate.disableRotation()
    map.addControl(new AttributionControl({ compact: false }), 'bottom-right')
    map.addControl(new NavigationControl({ showCompass: false }), 'top-right')
    const popup = new Popup({ closeButton: false, closeOnClick: false, offset: 10 })

    map.on('load', () => {
      map.addSource('areas', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
        attribution: GEO_ATTRIBUTION,
      })
      map.addLayer({
        id: 'areas',
        type: 'circle',
        source: 'areas',
        layout: { 'circle-sort-key': ['-', 0, ['get', 'count']] }, // small circles on top
        paint: {
          'circle-color': MISSING,
          'circle-opacity': 0.88,
          'circle-radius': radius(),
          'circle-stroke-color': '#fcfcfb',
          'circle-stroke-width': 1.2,
        },
      })
      map.addLayer({
        id: 'selected',
        type: 'circle',
        source: 'areas',
        filter: ['==', ['get', 'code'], ''],
        paint: {
          'circle-color': 'rgba(0,0,0,0)',
          'circle-radius': radius(3),
          'circle-stroke-color': '#0b0b0b',
          'circle-stroke-width': 2.5,
        },
      })
      setReady(true)
    })

    map.on('click', (event) => {
      const [feature] = map.queryRenderedFeatures(event.point, { layers: ['areas'] })
      latest.current.onSelect(feature ? String(feature.properties.code) : null)
    })
    map.on('mousemove', 'areas', (event) => {
      const code = event.features?.[0]?.properties.code
      const area = latest.current.areas.find((a) => a.code === code)
      if (!area) return
      map.getCanvas().style.cursor = 'pointer'
      popup.setLngLat(event.lngLat).setDOMContent(popupContent(area, latest.current.metric)).addTo(map)
    })
    map.on('mouseleave', 'areas', () => {
      map.getCanvas().style.cursor = ''
      popup.remove()
    })

    mapRef.current = map
    return () => {
      popup.remove()
      map.remove()
      mapRef.current = null
      setReady(false)
    }
  }, [])

  useEffect(() => {
    const source = mapRef.current?.getSource<GeoJSONSource>('areas')
    if (!ready || !source) return
    source.setData({
      type: 'FeatureCollection',
      features: areas.flatMap((area) =>
        area.lat === null || area.lng === null
          ? []
          : [
              {
                type: 'Feature' as const,
                geometry: { type: 'Point' as const, coordinates: [area.lng, area.lat] },
                properties: {
                  code: area.code,
                  count: area.count ?? area.n,
                  v: metricValue(area, metric) ?? -1,
                },
              },
            ],
      ),
    })
  }, [ready, areas, metric])

  useEffect(() => {
    if (ready) mapRef.current?.setPaintProperty('areas', 'circle-color', colorExpression(breaks))
  }, [ready, breaks])

  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map) return
    map.setFilter('selected', ['==', ['get', 'code'], selected ?? ''])
    const area = areas.find((a) => a.code === selected)
    if (area?.lat != null && area.lng != null) {
      map.easeTo({ center: [area.lng, area.lat], zoom: Math.max(map.getZoom(), 10.5) })
    }
    // only when the selection changes, not when the category or metric does
  }, [ready, selected])

  return (
    <>
      <div ref={container} className="map" role="region" aria-label="区域均价地图" />
      <Legend metric={metric} breaks={breaks} />
    </>
  )
}

function Legend({ metric, breaks }: { metric: Metric; breaks: number[] }) {
  const colors = binColors(breaks.length + 1)
  const fmt = metric === 'mean' ? formatManShort : (v: number) => `${Math.round(v)}`
  const labels = colors.map((_, i) => {
    if (breaks.length === 0) return '全部'
    if (i === 0) return `< ${fmt(breaks[0])}`
    if (i === breaks.length) return `≥ ${fmt(breaks[i - 1])}`
    return `${fmt(breaks[i - 1])}–${fmt(breaks[i])}`
  })
  return (
    <div className="legend" aria-label="图例">
      <div className="legend-title">{metric === 'mean' ? '均价（万円）' : '单价均价（万円/m²）'}</div>
      {/* compact strip on narrow screens */}
      <div className="legend-strip" aria-hidden="true">
        <div className="legend-ramp">
          {colors.map((color, i) => (
            <span key={color + i} style={{ background: color }} />
          ))}
        </div>
        <div className="legend-ends">
          <span>{labels[0]}</span>
          <span>{labels[labels.length - 1]}</span>
        </div>
      </div>
      <ul>
        {colors.map((color, i) => (
          <li key={color + i}>
            <span className="swatch" style={{ background: color }} />
            {labels[i]}
          </li>
        ))}
      </ul>
      <div className="legend-note">圆点大小 = 在售套数</div>
    </div>
  )
}
