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
import { type Metric, metricValue, type PlaceStat } from '../aggregate'
import { formatCount, formatMan, formatManShort, formatUnit } from '../format'
import type { Place } from '../types'

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

interface Props {
  places: Place[]
  stats: PlaceStat[]
  metric: Metric
  breaks: number[]
  selected: number | null
  onSelect: (place: number | null) => void
}

export function MapView({ places, stats, metric, breaks, selected, onSelect }: Props) {
  const container = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MapLibreMap | null>(null)
  const [ready, setReady] = useState(false)
  const onSelectRef = useRef(onSelect)
  onSelectRef.current = onSelect
  const formatRef = useRef<(v: number) => string>(formatMan)
  formatRef.current = metric === 'price' ? formatMan : formatUnit

  useEffect(() => {
    if (!container.current) return
    const map = new MapLibreMap({
      container: container.current,
      style: STYLE,
      // mainland Tokyo: Tama in the west to Edogawa in the east
      bounds: [
        [139.25, 35.52],
        [139.92, 35.83],
      ],
      fitBoundsOptions: { padding: 8 },
      // on touch screens one finger scrolls the page; two fingers move the map
      cooperativeGestures: window.matchMedia('(pointer: coarse)').matches,
      locale: {
        'CooperativeGesturesHandler.MobileHelpText': '用两根手指移动地图',
        'CooperativeGesturesHandler.WindowsHelpText': '按住 Ctrl 并滚动来缩放地图',
        'CooperativeGesturesHandler.MacHelpText': '按住 ⌘ 并滚动来缩放地图',
      },
      minZoom: 7,
      maxZoom: 18,
      attributionControl: false,
      dragRotate: false,
      pitchWithRotate: false,
    })
    map.touchZoomRotate.disableRotation()
    map.addControl(new AttributionControl({ compact: false }), 'bottom-right')
    map.addControl(new NavigationControl({ showCompass: false }), 'top-right')
    const popup = new Popup({ closeButton: false, closeOnClick: false, offset: 10 })

    map.on('load', () => {
      map.addSource('places', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
        attribution: GEO_ATTRIBUTION,
      })
      map.addLayer({
        id: 'places',
        type: 'circle',
        source: 'places',
        layout: { 'circle-sort-key': ['-', 0, ['get', 'n']] }, // small circles on top
        paint: {
          'circle-color': MISSING,
          'circle-opacity': 0.88,
          'circle-radius': [
            'interpolate', ['linear'], ['zoom'],
            9, ['+', 2.5, ['*', 0.8, ['sqrt', ['get', 'n']]]],
            15, ['+', 6, ['*', 3, ['sqrt', ['get', 'n']]]],
          ],
          'circle-stroke-color': '#fcfcfb',
          'circle-stroke-width': 1,
        },
      })
      map.addLayer({
        id: 'selected',
        type: 'circle',
        source: 'places',
        filter: ['==', ['get', 'i'], -1],
        paint: {
          'circle-color': 'rgba(0,0,0,0)',
          'circle-radius': [
            'interpolate', ['linear'], ['zoom'],
            9, ['+', 6, ['*', 0.8, ['sqrt', ['get', 'n']]]],
            15, ['+', 10, ['*', 3, ['sqrt', ['get', 'n']]]],
          ],
          'circle-stroke-color': '#0b0b0b',
          'circle-stroke-width': 2.5,
        },
      })
      setReady(true)
    })

    map.on('click', (event) => {
      const [feature] = map.queryRenderedFeatures(event.point, { layers: ['places'] })
      onSelectRef.current(feature ? Number(feature.properties.i) : null)
    })
    map.on('mousemove', 'places', (event) => {
      const feature = event.features?.[0]
      if (!feature) return
      map.getCanvas().style.cursor = 'pointer'
      const { name, n, v } = feature.properties as { name: string; n: number; v: number }
      const node = document.createElement('div')
      const title = document.createElement('strong')
      title.textContent = name // place names are data: never innerHTML
      const line = document.createElement('div')
      line.textContent = `${formatCount(n)} 套 · 中位 ${v >= 0 ? formatRef.current(v) : '—'}`
      node.append(title, line)
      popup.setLngLat(event.lngLat).setDOMContent(node).addTo(map)
    })
    map.on('mouseleave', 'places', () => {
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
    const source = mapRef.current?.getSource<GeoJSONSource>('places')
    if (!ready || !source) return
    source.setData({
      type: 'FeatureCollection',
      features: stats.map((stat) => {
        const place = places[stat.place]
        return {
          type: 'Feature',
          geometry: { type: 'Point', coordinates: [place.lng, place.lat] },
          properties: { i: stat.place, n: stat.count, v: metricValue(stat, metric) ?? -1, name: place.name },
        }
      }),
    })
  }, [ready, stats, places, metric])

  useEffect(() => {
    if (ready) mapRef.current?.setPaintProperty('places', 'circle-color', colorExpression(breaks))
  }, [ready, breaks])

  useEffect(() => {
    if (ready) mapRef.current?.setFilter('selected', ['==', ['get', 'i'], selected ?? -1])
  }, [ready, selected])

  return (
    <>
      <div ref={container} className="map" role="region" aria-label="房源分布地图" />
      <Legend metric={metric} breaks={breaks} />
    </>
  )
}

function Legend({ metric, breaks }: { metric: Metric; breaks: number[] }) {
  const colors = binColors(breaks.length + 1)
  const fmt = metric === 'price' ? formatManShort : (v: number) => `${Math.round(v)}`
  const labels = colors.map((_, i) => {
    if (breaks.length === 0) return '全部'
    if (i === 0) return `< ${fmt(breaks[0])}`
    if (i === breaks.length) return `≥ ${fmt(breaks[i - 1])}`
    return `${fmt(breaks[i - 1])}–${fmt(breaks[i])}`
  })
  return (
    <div className="legend" aria-label="图例">
      <div className="legend-title">
        {metric === 'price' ? '町丁目中位价格（万円）' : '町丁目单价中位数（万円/m²）'}
      </div>
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
        <li>
          <span className="swatch" style={{ background: MISSING }} />
          无价格
        </li>
      </ul>
      <div className="legend-note">圆点大小 = 套数</div>
    </div>
  )
}
