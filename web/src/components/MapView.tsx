import {
  AttributionControl,
  type ExpressionSpecification,
  type MapGeoJSONFeature,
  type PointLike,
  Map as MapLibreMap,
  NavigationControl,
  Popup,
  type StyleSpecification,
} from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { useEffect, useRef, useState } from 'react'
import {
  type ColorStop,
  type DayTable,
  type Level,
  LEVEL_LABELS,
  LEVELS,
  levelOf,
  type Metric,
  metricValue,
  type ScaleMode,
} from '../data'
import { formatCount, formatMetric, formatMetricShort, metricUnit } from '../format'
import { type Areas, type BBox, displayName } from '../geo'

// Sequential blue, light → dark (steps 100…700): a choropleth may use the full range.
export const RAMP = ['#cde2fb', '#9ec5f4', '#6da7ec', '#3987e5', '#256abf', '#184f95', '#0d366b']
const NONE = 'rgba(0,0,0,0)'

const GSI_ATTRIBUTION =
  '<a href="https://maps.gsi.go.jp/development/ichiran.html" target="_blank" rel="noopener noreferrer">地理院タイル</a>'
const BOUNDARY_ATTRIBUTION = '境界：e-Stat 国勢調査 2020 小地域'

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

/** A continuous fill: the ramp's colors at the stops, interpolated in Lab between them. */
function fillColor(stops: ColorStop[]): ExpressionSpecification {
  // feature state is null for areas without a row: coalesce first (to-number(null) is 0)
  const value: ExpressionSpecification = ['to-number', ['coalesce', ['feature-state', 'v'], -1]]
  let color: ExpressionSpecification | string = RAMP[3]
  if (stops.length > 1) {
    const ramp: unknown[] = ['interpolate-lab', ['linear'], value]
    for (const stop of stops) ramp.push(stop.value, RAMP[stop.index])
    color = ramp as ExpressionSpecification
  } else if (stops.length === 1) {
    color = RAMP[stops[0].index]
  }
  // too few listings or none (-1): no fill, the base map shows through
  return ['case', ['>=', value, 0], color, NONE]
}

const flag = (name: string): ExpressionSpecification => ['boolean', ['feature-state', name], false]

export interface MapViewState {
  zoom: number
  bounds: BBox
}

export interface FocusRequest {
  bbox: BBox
  id: number
}

interface Props {
  areas: Areas
  level: Level
  table: DayTable | null
  metric: Metric
  stops: ColorStop[]
  scale: ScaleMode
  onScale: (scale: ScaleMode) => void
  minSample: number
  selected: string | null
  focus: FocusRequest | null
  onSelect: (code: string | null) => void
  onView: (view: MapViewState) => void
}

export function MapView(props: Props) {
  const { areas, level, table, metric, stops, minSample, selected, focus, onSelect, onView } = props
  const container = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MapLibreMap | null>(null)
  const [ready, setReady] = useState(false)
  // event handlers are bound once; read the latest props through refs
  const latest = useRef({ table, metric, level, minSample, onSelect, onView })
  latest.current = { table, metric, level, minSample, onSelect, onView }
  const hovered = useRef<{ source: Level; id: string } | null>(null)

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
      maxZoom: 17,
      attributionControl: false,
      dragRotate: false,
      pitchWithRotate: false,
    })
    map.touchZoomRotate.disableRotation()
    map.addControl(new AttributionControl({ compact: false }), 'bottom-right')
    map.addControl(new NavigationControl({ showCompass: false }), 'top-right')
    const popup = new Popup({ closeButton: false, closeOnClick: false, offset: 8, maxWidth: '260px' })

    const report = () => {
      const b = map.getBounds()
      latest.current.onView({ zoom: map.getZoom(), bounds: [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()] })
    }

    map.on('load', () => {
      for (const lv of LEVELS) {
        map.addSource(lv, {
          type: 'geojson',
          data: areas.features[lv],
          promoteId: 'id',
          attribution: BOUNDARY_ATTRIBUTION,
        })
        map.addLayer({
          id: `fill-${lv}`,
          type: 'fill',
          source: lv,
          paint: { 'fill-color': NONE, 'fill-opacity': 0.78 },
        })
        map.addLayer({
          id: `line-${lv}`,
          type: 'line',
          source: lv,
          paint: {
            'line-color': '#fcfcfb',
            'line-width': ['interpolate', ['linear'], ['zoom'], 9, 0.4, 14, 1.2],
            'line-opacity': 0.9,
          },
        })
        map.addLayer({
          id: `hover-${lv}`,
          type: 'line',
          source: lv,
          paint: { 'line-color': '#0b0b0b', 'line-width': 1.5, 'line-opacity': ['case', flag('hover'), 0.8, 0] },
        })
      }
      // the selection outline shows at every zoom, above the fills of any level
      for (const lv of LEVELS) {
        map.addLayer({
          id: `selected-${lv}`,
          type: 'line',
          source: lv,
          paint: {
            'line-color': '#0b0b0b',
            'line-width': 3,
            'line-opacity': ['case', flag('selected'), 1, 0],
          },
        })
      }
      setReady(true)
      report()
    })
    map.on('moveend', report)

    const clearHover = () => {
      if (hovered.current) map.setFeatureState(hovered.current, { hover: false })
      hovered.current = null
      map.getCanvas().style.cursor = ''
      popup.remove()
    }

    const visibleFeature = (point: PointLike): MapGeoJSONFeature | undefined =>
      map.queryRenderedFeatures(point, { layers: [`fill-${latest.current.level}`] })[0]

    map.on('click', (event) => {
      const feature = visibleFeature(event.point)
      latest.current.onSelect(feature ? String(feature.id) : null)
    })
    map.on('mousemove', (event) => {
      const feature = visibleFeature(event.point)
      const id = feature ? String(feature.id) : null
      const source = latest.current.level
      if (!id) return clearHover()
      if (hovered.current?.id !== id) {
        clearHover()
        hovered.current = { source, id }
        map.setFeatureState(hovered.current, { hover: true })
      }
      map.getCanvas().style.cursor = 'pointer'
      popup.setLngLat(event.lngLat).setDOMContent(popupContent(id)).addTo(map)
    })
    map.getCanvas().addEventListener('mouseleave', clearHover)

    function popupContent(code: string): HTMLElement {
      // area names are data: build text nodes, never innerHTML
      const { table, metric, minSample } = latest.current
      const values = table?.get(code)
      const node = document.createElement('div')
      const title = document.createElement('strong')
      title.textContent = displayName(code, areas.info)
      node.append(title)
      const lines: string[] = []
      if (!values) {
        lines.push('无在售房源')
      } else {
        const value = metricValue(values, metric.key)
        lines.push(
          value === null
            ? `${metric.short}：样本不足（少于 ${minSample} 套）`
            : `${metric.short}：${formatMetric(metric, value)}`,
        )
        if (metric.kind !== 'count') {
          lines.push(`在售 ${formatCount(values.count)} 套 · 计入 ${formatCount(values[metric.sample])} 套`)
        }
      }
      for (const text of lines) {
        const line = document.createElement('div')
        line.textContent = text
        node.append(line)
      }
      return node
    }

    mapRef.current = map
    return () => {
      popup.remove()
      map.remove()
      mapRef.current = null
      setReady(false)
    }
    // the geometry is loaded once before the map mounts
  }, [areas])

  // which level is drawn
  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map) return
    for (const lv of LEVELS) {
      const visibility = lv === level ? 'visible' : 'none'
      for (const prefix of ['fill', 'line', 'hover']) map.setLayoutProperty(`${prefix}-${lv}`, 'visibility', visibility)
    }
    if (hovered.current && hovered.current.source !== level) {
      map.setFeatureState(hovered.current, { hover: false })
      hovered.current = null
    }
  }, [ready, level])

  // values of the day as feature state
  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map) return
    for (const lv of LEVELS) map.removeFeatureState({ source: lv })
    if (table) {
      for (const [code, values] of table) {
        const lv = levelOf(code)
        if (!lv) continue
        const value = metricValue(values, metric.key)
        map.setFeatureState({ source: lv, id: code }, { v: value ?? -1 })
      }
    }
    if (selected) {
      const lv = levelOf(selected)
      if (lv) map.setFeatureState({ source: lv, id: selected }, { selected: true })
    }
    if (hovered.current) map.setFeatureState(hovered.current, { hover: true })
  }, [ready, table, metric, selected])

  useEffect(() => {
    if (!ready) return
    for (const lv of LEVELS) mapRef.current?.setPaintProperty(`fill-${lv}`, 'fill-color', fillColor(stops))
  }, [ready, stops])

  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map || !focus) return
    const [w, s, e, n] = focus.bbox
    map.fitBounds(
      [
        [w, s],
        [e, n],
      ],
      { padding: 60, maxZoom: 15, duration: 600 },
    )
  }, [ready, focus])

  return (
    <>
      <div ref={container} className="map" role="region" aria-label="区域价格地图" />
      <Legend
        metric={metric}
        level={level}
        stops={stops}
        scale={props.scale}
        onScale={props.onScale}
        minSample={minSample}
      />
    </>
  )
}

const GRADIENT = RAMP.map((c, i) => `${c} ${((i / (RAMP.length - 1)) * 100).toFixed(1)}%`).join(', ')
const LABELLED = [0, 2, 4, 6] // ramp positions that get a value label

interface LegendProps {
  metric: Metric
  level: Level
  stops: ColorStop[]
  scale: ScaleMode
  onScale: (scale: ScaleMode) => void
  minSample: number
}

const SCALES: [ScaleMode, string, string][] = [
  ['quantile', '按分位', '颜色按区域排名均匀分布：每一段颜色覆盖同样多的区域'],
  ['linear', '按数值', '颜色与数值成正比（两端截在第 2 和第 98 百分位）'],
]

function Legend({ metric, level, stops, scale, onScale, minSample }: LegendProps) {
  const fmt = (v: number) => formatMetricShort(metric, v)
  const last = RAMP.length - 1
  const ticks = stops
    .filter((s, i) => LABELLED.includes(s.index) || i === stops.length - 1)
    .map((s) => {
      // linear: the ends are clipped at the 2nd and 98th percentiles
      const clipped = scale === 'linear' && (s.index === 0 || s.index === last)
      const text = clipped ? `${s.index === 0 ? '≤' : '≥'}${fmt(s.value)}` : fmt(s.value)
      return { position: s.index / last, text }
    })
  return (
    <div className="legend" aria-label="图例">
      <div className="legend-title">
        {metric.short}（{metricUnit(metric)}）· {LEVEL_LABELS[level]}
      </div>
      <div className="legend-bar" style={{ background: `linear-gradient(to right, ${GRADIENT})` }} />
      <div className="legend-ticks">
        {ticks.map((t) => (
          <span
            key={t.position}
            style={{ left: `${t.position * 100}%` }}
            className={t.position === 0 ? 'start' : t.position === 1 ? 'end' : ''}
          >
            {t.text}
          </span>
        ))}
      </div>
      <div className="legend-row">
        <span className="swatch empty" />
        {metric.kind === 'count' ? '无在售房源' : `无在售房源或少于 ${minSample} 套`}
      </div>
      <div className="legend-row">
        <span className="muted-ink">色阶</span>
        <div className="segmented tiny" role="group" aria-label="色阶">
          {SCALES.map(([mode, label, title]) => (
            <button
              key={mode}
              type="button"
              title={title}
              className={scale === mode ? 'selected' : ''}
              aria-pressed={scale === mode}
              onClick={() => onScale(mode)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      <div className="legend-note">色阶按最新一天的数据确定，切换日期时不变</div>
    </div>
  )
}
