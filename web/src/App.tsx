import { useEffect, useMemo, useState } from 'react'
import { MapView, RAMP } from './components/MapView'
import { RankList } from './components/RankList'
import { formatCount, formatMan, formatUnit } from './format'
import {
  type CategoryKey,
  hasUnitPrice,
  loadSummary,
  type Metric,
  metricValue,
  quantileBreaks,
  ranked,
  type Summary,
} from './summary'

type Phase = { kind: 'loading' } | { kind: 'error'; message: string } | { kind: 'ready'; summary: Summary }

export function App() {
  const [phase, setPhase] = useState<Phase>({ kind: 'loading' })

  useEffect(() => {
    loadSummary(import.meta.env.BASE_URL)
      .then((summary) => setPhase({ kind: 'ready', summary }))
      .catch((e: unknown) =>
        setPhase({ kind: 'error', message: e instanceof Error ? e.message : String(e) }),
      )
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
      return <Explorer summary={phase.summary} />
  }
}

function Explorer({ summary }: { summary: Summary }) {
  const [categoryKey, setCategory] = useState<CategoryKey>(summary.categories[0]?.key ?? 'used_condo')
  const [metricChoice, setMetric] = useState<Metric>('mean')
  const [selected, setSelected] = useState<string | null>(null)

  const category = summary.categories.find((c) => c.key === categoryKey) ?? summary.categories[0]
  const unitAvailable = hasUnitPrice(category.key)
  const metric: Metric = unitAvailable ? metricChoice : 'mean'
  const areas = useMemo(() => ranked(category.areas, metric), [category, metric])
  const breaks = useMemo(
    () =>
      quantileBreaks(
        category.areas.flatMap((a) => {
          const v = metricValue(a, metric)
          return v === null ? [] : [v]
        }),
        RAMP.length,
      ),
    [category, metric],
  )
  const tokyo = category.tokyo

  return (
    <div className="app">
      <header className="topbar">
        <h1 className="brand">SuumoViz</h1>
        <span className="muted">东京都在售房源 · 区域均价</span>
        <span className="spacer" />
        <span className="muted small">数据截至 {summary.latestDate}</span>
      </header>
      {/* DOM order is the phone order (controls, map, list); the grid places them on desktop */}
      <div className="body">
        <section className="controls" aria-label="选择">
          <div className="segmented categories" role="group" aria-label="类别">
            {summary.categories.map((c) => (
              <button
                key={c.key}
                type="button"
                className={c.key === category.key ? 'selected' : ''}
                aria-pressed={c.key === category.key}
                onClick={() => {
                  setCategory(c.key)
                  setSelected(null)
                }}
              >
                {c.label}
              </button>
            ))}
          </div>
          <div className="segmented small" role="group" aria-label="指标">
            <button
              type="button"
              className={metric === 'mean' ? 'selected' : ''}
              aria-pressed={metric === 'mean'}
              onClick={() => setMetric('mean')}
            >
              总价均价
            </button>
            <button
              type="button"
              className={metric === 'unit' ? 'selected' : ''}
              aria-pressed={metric === 'unit'}
              disabled={!unitAvailable}
              title={unitAvailable ? undefined : '新築マンション的价格是不同户型的区间，不计算单价'}
              onClick={() => setMetric('unit')}
            >
              单价均价
            </button>
          </div>
          {tokyo && (
            <dl className="tokyo">
              <div>
                <dt>全东京在售</dt>
                <dd>{formatCount(tokyo.count)} 套</dd>
              </div>
              <div>
                <dt>均价</dt>
                <dd>{formatMan(tokyo.mean)}</dd>
              </div>
              <div>
                <dt>中位价</dt>
                <dd>{formatMan(tokyo.median)}</dd>
              </div>
              {unitAvailable && (
                <div>
                  <dt>单价均价</dt>
                  <dd>{formatUnit(tokyo.unitMean)}</dd>
                </div>
              )}
            </dl>
          )}
        </section>
        <div className="map-wrap">
          <MapView areas={areas} metric={metric} breaks={breaks} selected={selected} onSelect={setSelected} />
        </div>
        <section className="list" aria-label="区域排行">
          <RankList areas={areas} metric={metric} selected={selected} onSelect={setSelected} />
          <footer className="notes muted small">
            <p>
              均价：区域内在售房源价格的算术平均（价格为区间时取下限）；单价按専有面積或建物面積计算，不含纯土地。
              统计范围是最近 7 天轮转周期内看到的房源；在售套数是 SUUMO 当天的区域件数。
            </p>
            <p>房源：{summary.sources.listings}</p>
            <p>坐标：{summary.sources.geo}</p>
            <p>底图：地理院タイル（国土地理院）</p>
          </footer>
        </section>
      </div>
    </div>
  )
}
