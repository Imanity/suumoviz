import { useEffect, useMemo, useState } from 'react'
import { AreaPanel } from './components/AreaPanel'
import { type FocusRequest, MapView, type MapViewState, RAMP } from './components/MapView'
import { RankList } from './components/RankList'
import {
  type CategoryKey,
  type DayTable,
  type History,
  type Index,
  type Level,
  LEVEL_LABELS,
  LEVEL_ZOOMS,
  LEVELS,
  levelForZoom,
  loadDay,
  loadHistory,
  loadIndex,
  type MetricKey,
  METRICS,
  parentOf,
  quantileBreaks,
  ranked,
} from './data'
import { formatDay } from './format'
import { type Areas, loadAreas } from './geo'

const BASE = import.meta.env.BASE_URL

type Phase =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; index: Index; areas: Areas }

const message = (e: unknown) => (e instanceof Error ? e.message : String(e))

export function App() {
  const [phase, setPhase] = useState<Phase>({ kind: 'loading' })

  useEffect(() => {
    Promise.all([loadIndex(BASE), loadAreas(BASE)])
      .then(([index, areas]) => setPhase({ kind: 'ready', index, areas }))
      .catch((e: unknown) => setPhase({ kind: 'error', message: message(e) }))
  }, [])

  switch (phase.kind) {
    case 'loading':
      return <p className="center muted">加载中…</p>
    case 'error':
      return (
        <p className="center error" role="alert">
          {phase.message}
        </p>
      )
    case 'ready':
      return <Explorer index={phase.index} areas={phase.areas} />
  }
}

// one request per file per page view; failed requests are retried next time
const cache = new Map<string, Promise<unknown>>()

interface Loaded<T> {
  key: string | null
  data: T | null
  error: string | null
}

/** Loads `key` once; with `keepPrevious` the last data stays while the next one loads. */
function useCached<T>(key: string | null, load: () => Promise<T>, keepPrevious = false): Loaded<T> {
  const [state, setState] = useState<Loaded<T>>({ key: null, data: null, error: null })
  useEffect(() => {
    if (key === null) return
    let live = true
    let promise = cache.get(key) as Promise<T> | undefined
    if (!promise) {
      promise = load()
      cache.set(key, promise)
      promise.catch(() => cache.delete(key))
    }
    promise.then(
      (data) => live && setState({ key, data, error: null }),
      (e: unknown) => live && setState({ key, data: null, error: message(e) }),
    )
    return () => {
      live = false
    }
    // `load` is derived from `key`
  }, [key])
  if (state.key === key) return state
  return keepPrevious ? { key, data: state.data, error: null } : { key, data: null, error: null }
}

type LevelMode = 'auto' | Level

function Explorer({ index, areas }: { index: Index; areas: Areas }) {
  const [categoryKey, setCategory] = useState<CategoryKey>(index.categories[0]?.key ?? 'used_condo')
  const [metricKey, setMetric] = useState<MetricKey>('unit_mean')
  const [levelMode, setLevelMode] = useState<LevelMode>('auto')
  const [dateIndex, setDateIndex] = useState(index.dates.length - 1)
  const [selected, setSelected] = useState<string | null>(null)
  const [view, setView] = useState<MapViewState | null>(null)
  const [focus, setFocus] = useState<FocusRequest | null>(null)

  const category = index.categories.find((c) => c.key === categoryKey) ?? index.categories[0]
  const metric = METRICS.find((m) => m.key === metricKey) ?? METRICS[0]
  const level: Level = levelMode === 'auto' ? levelForZoom(view?.zoom ?? 9) : levelMode
  const date = index.dates[dateIndex]
  const latestDate = index.dates[index.dates.length - 1]

  const day = useCached<DayTable>(`day/${date}/${category.key}`, () => loadDay(BASE, date, category.key), true)
  const latest = useCached<DayTable>(`day/${latestDate}/${category.key}`, () =>
    loadDay(BASE, latestDate, category.key),
  )
  const history = useCached<History>(
    selected ? `history/${category.key}/${parentOf(selected)}` : null,
    () => loadHistory(BASE, category.key, selected ?? ''),
  )

  // bins from the latest day, so colors keep their meaning along the timeline
  const breaks = useMemo(() => {
    if (!latest.data) return []
    const values = ranked(latest.data, level, metric.key).flatMap((r) => (r.value === null ? [] : [r.value]))
    return quantileBreaks(values, RAMP.length)
  }, [latest.data, level, metric.key])

  const rows = useMemo(() => {
    if (!day.data) return []
    const bounds = view?.bounds
    const inView = (code: string) => {
      const box = areas.info.get(code)?.bbox
      if (!box || !bounds) return true
      const x = (box[0] + box[2]) / 2
      const y = (box[1] + box[3]) / 2
      return x >= bounds[0] && x <= bounds[2] && y >= bounds[1] && y <= bounds[3]
    }
    return ranked(day.data, level, metric.key, inView)
  }, [day.data, level, metric.key, view, areas])

  const select = (code: string | null, move: boolean) => {
    setSelected(code)
    const box = code ? areas.info.get(code)?.bbox : undefined
    if (move && box) setFocus({ bbox: box, id: Date.now() })
  }

  const values = selected ? (day.data?.get(selected) ?? null) : (category.tokyo[dateIndex] ?? null)
  const series = selected ? (history.data ? (history.data.get(selected) ?? index.dates.map(() => null)) : null) : category.tokyo

  return (
    <div className="app">
      <header className="topbar">
        <h1 className="brand">SuumoViz</h1>
        <span className="muted">东京都在售房源 · 区域价格</span>
        <span className="spacer" />
        <span className="muted small">数据截至 {index.latestDate}</span>
      </header>
      {/* phones: controls, map, details (.side dissolves); desktop: one scrolling sidebar */}
      <div className="body">
        <aside className="side">
          <section className="controls" aria-label="选项">
            <div className="field">
              <div className="label" id="label-category">
                类别
              </div>
              <div className="segmented categories" role="group" aria-labelledby="label-category">
                {index.categories.map((c) => (
                  <button
                    key={c.key}
                    type="button"
                    className={c.key === category.key ? 'selected' : ''}
                    aria-pressed={c.key === category.key}
                    onClick={() => setCategory(c.key)}
                  >
                    {c.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="field">
              <div className="label" id="label-metric">
                可视化维度
              </div>
              <div className="segmented metrics" role="group" aria-labelledby="label-metric">
                {METRICS.map((m) => (
                  <button
                    key={m.key}
                    type="button"
                    className={m.key === metric.key ? 'selected' : ''}
                    aria-pressed={m.key === metric.key}
                    onClick={() => setMetric(m.key)}
                  >
                    {m.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="field">
              <div className="label" id="label-level">
                细分粒度
                {levelMode === 'auto' && <span className="muted"> · 当前 {LEVEL_LABELS[level]}</span>}
              </div>
              <div className="segmented" role="group" aria-labelledby="label-level">
                {(['auto', ...LEVELS] as LevelMode[]).map((mode) => (
                  <button
                    key={mode}
                    type="button"
                    className={mode === levelMode ? 'selected' : ''}
                    aria-pressed={mode === levelMode}
                    title={
                      mode === 'auto'
                        ? `随缩放切换：缩放 ${LEVEL_ZOOMS.town} 起为町・大字，${LEVEL_ZOOMS.chome} 起为丁目・字`
                        : undefined
                    }
                    onClick={() => setLevelMode(mode)}
                  >
                    {mode === 'auto' ? '随缩放' : LEVEL_LABELS[mode]}
                  </button>
                ))}
              </div>
            </div>
            <div className="field">
              <label className="label" htmlFor="timeline">
                时间轴 <strong className="date">{date}</strong>
                {day.key !== `day/${date}/${category.key}` || (day.data === null && !day.error) ? (
                  <span className="muted"> · 读取中…</span>
                ) : null}
              </label>
              {index.dates.length > 1 ? (
                <div className="timeline">
                  <button
                    type="button"
                    className="step"
                    aria-label="前一天"
                    disabled={dateIndex === 0}
                    onClick={() => setDateIndex((i) => Math.max(0, i - 1))}
                  >
                    ‹
                  </button>
                  <div className="timeline-track">
                    <input
                      id="timeline"
                      type="range"
                      min={0}
                      max={index.dates.length - 1}
                      step={1}
                      value={dateIndex}
                      aria-valuetext={date}
                      onChange={(e) => setDateIndex(Number(e.target.value))}
                    />
                    <div className="timeline-ends muted small" aria-hidden="true">
                      <span>{formatDay(index.dates[0])}</span>
                      <span>{formatDay(latestDate)}</span>
                    </div>
                  </div>
                  <button
                    type="button"
                    className="step"
                    aria-label="后一天"
                    disabled={dateIndex === index.dates.length - 1}
                    onClick={() => setDateIndex((i) => Math.min(index.dates.length - 1, i + 1))}
                  >
                    ›
                  </button>
                </div>
              ) : (
                <p className="muted small">还没有完整的 7 天轮转周期，只能显示最新一天。</p>
              )}
              {day.error && <p className="error small">{day.error}</p>}
            </div>
          </section>
          <div className="list">
            <AreaPanel
              code={selected}
              info={areas.info}
              categoryLabel={category.label}
              metric={metric}
              dates={index.dates}
              current={dateIndex}
              values={values}
              series={series}
              official={selected ? null : (category.official[dateIndex] ?? null)}
              error={selected ? history.error : null}
              onSelect={(code) => select(code, true)}
              onPickDate={setDateIndex}
            />
            <section aria-label="区域排行">
              <h2 className="section-title">
                地图范围内的{LEVEL_LABELS[level]} · 按{metric.short}排序
              </h2>
              <RankList
                rows={rows}
                metric={metric}
                info={areas.info}
                selected={selected}
                onSelect={(code) => select(code, true)}
              />
            </section>
            <footer className="notes muted small">
              <p>
                在售：首次出现之后、最后一次被扫到后 {index.graceDays} 天之内的房源（每页每 7
                天重扫一次）。价格为区间时取下限；单价只用价格和面积都是单一值的房源，按専有面積或建物面積计算。
                计入少于 {index.minSample} 套时不显示价格，以免显示单套房源的价格。
              </p>
              <p>
                房源地址大多只写到丁目，所以最细到丁目・字。地址只能对应到町或区的房源只计入上一级。
              </p>
              <p>房源：{index.sources.listings}</p>
              <p>地址对照：{index.sources.geo}</p>
              <p>边界：{index.sources.boundaries}</p>
              <p>底图：地理院タイル（国土地理院）</p>
            </footer>
          </div>
        </aside>
        <div className="map-wrap">
          <MapView
            areas={areas}
            level={level}
            table={day.data}
            metric={metric}
            breaks={breaks}
            minSample={index.minSample}
            selected={selected}
            focus={focus}
            onSelect={(code) => select(code, false)}
            onView={setView}
          />
        </div>
      </div>
    </div>
  )
}
