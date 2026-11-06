import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { aggregateByPlace, type Filters, matches, type Metric, metricValue, NO_FILTERS, quantileBreaks } from './aggregate'
import { FilterBar } from './components/Filters'
import { Login } from './components/Login'
import { MapView, RAMP } from './components/MapView'
import { PlacePanel } from './components/PlacePanel'
import { TrendPanel } from './components/TrendPanel'
import { clearCredentials, loadCredentials, saveCredentials } from './credentials'
import {
  DataError,
  type DataSource,
  githubSource,
  loadCategory,
  loadDataset,
  localSource,
} from './source'
import type { CategoryData, CategoryKey, Dataset } from './types'

// Development reads public/data/ (from `suumoviz build`); production asks for a token.
const LOCAL_DATA = (import.meta.env.VITE_LOCAL_DATA ?? (import.meta.env.DEV ? '1' : '0')) === '1'

type Phase =
  | { kind: 'login'; error?: string; repo?: string; busy: boolean }
  | { kind: 'loading' }
  | { kind: 'ready'; source: DataSource; dataset: Dataset }
  | { kind: 'error'; message: string }

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

export function App() {
  const [phase, setPhase] = useState<Phase>({ kind: 'loading' })

  const connect = useCallback(async (source: DataSource, onSuccess?: () => void) => {
    const dataset = await loadDataset(source)
    onSuccess?.()
    setPhase({ kind: 'ready', source, dataset })
  }, [])

  useEffect(() => {
    if (LOCAL_DATA) {
      connect(localSource(`${import.meta.env.BASE_URL}data/`)).catch((e) =>
        setPhase({ kind: 'error', message: message(e) }),
      )
      return
    }
    const saved = loadCredentials()
    if (!saved) {
      setPhase({ kind: 'login', busy: false })
      return
    }
    connect(githubSource(saved.repo, saved.token)).catch((e) => {
      if (e instanceof DataError && e.isAuth) clearCredentials()
      setPhase({ kind: 'login', busy: false, repo: saved.repo, error: message(e) })
    })
  }, [connect])

  const login = (repo: string, token: string, remember: boolean) => {
    setPhase({ kind: 'login', busy: true, repo })
    try {
      const source = githubSource(repo, token)
      connect(source, () => saveCredentials({ repo, token }, remember)).catch((e) =>
        setPhase({ kind: 'login', busy: false, repo, error: message(e) }),
      )
    } catch (e) {
      setPhase({ kind: 'login', busy: false, repo, error: message(e) })
    }
  }

  const logout = () => {
    clearCredentials()
    setPhase({ kind: 'login', busy: false })
  }

  switch (phase.kind) {
    case 'login':
      return (
        <Login initialRepo={phase.repo} error={phase.error} busy={phase.busy} onSubmit={login} />
      )
    case 'loading':
      return <p className="center muted">加载中…</p>
    case 'error':
      return (
        <p className="center error" role="alert">
          {phase.message}
        </p>
      )
    case 'ready':
      return (
        <Explorer
          source={phase.source}
          dataset={phase.dataset}
          onLogout={LOCAL_DATA ? undefined : logout}
        />
      )
  }
}

function Explorer({
  source,
  dataset,
  onLogout,
}: {
  source: DataSource
  dataset: Dataset
  onLogout?: () => void
}) {
  const { meta, areas, places } = dataset
  const [category, setCategory] = useState<CategoryKey>(meta.categories[0]?.key ?? 'used_condo')
  const [shown, setShown] = useState<{ category: CategoryKey; data: CategoryData } | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [filters, setFilters] = useState<Filters>(NO_FILTERS)
  const [metricChoice, setMetric] = useState<Metric>('price')
  const [selected, setSelected] = useState<number | null>(null)
  const [area, setArea] = useState(meta.prefecture_area)
  const cache = useRef(new Map<CategoryKey, CategoryData>())

  useEffect(() => {
    let cancelled = false
    const cached = cache.current.get(category)
    if (cached) {
      setShown({ category, data: cached })
      return
    }
    setLoadError(null)
    loadCategory(source, category)
      .then((data) => {
        cache.current.set(category, data)
        if (!cancelled) setShown({ category, data })
      })
      .catch((e) => !cancelled && setLoadError(message(e)))
    return () => {
      cancelled = true
    }
  }, [source, category])

  const shownCategory = shown?.category ?? category
  const metric: Metric = shownCategory === 'new_condo' ? 'price' : metricChoice
  const listings = shown?.data.listings
  const filtered = useMemo(
    () => (listings ?? []).filter((l) => matches(l, filters)),
    [listings, filters],
  )
  const stats = useMemo(() => aggregateByPlace(filtered, shownCategory), [filtered, shownCategory])
  // Color bins come from the unfiltered category so colors stay put while filtering.
  const breaks = useMemo(() => {
    const all = aggregateByPlace(listings ?? [], shownCategory)
    return quantileBreaks(
      all.flatMap((s) => {
        const v = metricValue(s, metric)
        return v === null ? [] : [v]
      }),
      RAMP.length,
    )
  }, [listings, shownCategory, metric])

  const selectedStat = stats.find((s) => s.place === selected) ?? null
  const selectedListings = useMemo(
    () => (selected === null ? [] : filtered.filter((l) => l.place === selected)),
    [filtered, selected],
  )
  const areaNames = useMemo(() => new Map(areas.map((a) => [a.code, a.name])), [areas])

  const select = (place: number | null) => {
    setSelected(place)
    if (place === null) return
    // follow the place's SUUMO area in the trend panel (most listings win)
    const counts = new Map<string, number>()
    for (const l of filtered) if (l.place === place) counts.set(l.area, (counts.get(l.area) ?? 0) + 1)
    const top = [...counts.entries()].sort((a, b) => b[1] - a[1])[0]
    if (top) setArea(top[0])
  }

  const changeCategory = (next: CategoryKey) => {
    setCategory(next)
    setSelected(null)
  }

  const onSale = shown?.data.trends.series[meta.prefecture_area]?.count.at(-1) ?? null
  const loading = shown?.category !== category
  const selectedPlace = selected === null ? null : places[selected]
  const firstCycle = meta.latest_date < meta.steady_from

  return (
    <div className={`app${loading ? ' is-loading' : ''}`}>
      <header className="topbar">
        <span className="brand">SuumoViz</span>
        <span className="muted">数据截至 {meta.latest_date}</span>
        <span className="spacer" />
        <span className="muted small source">{source.label}</span>
        {onLogout && (
          <button type="button" className="link-button" onClick={onLogout}>
            退出
          </button>
        )}
      </header>
      {firstCycle && (
        <p className="banner">
          首个 7 天周期（{meta.first_date} 起）尚未结束：地图上只有已经抓到的片区，{meta.steady_from}{' '}
          之后覆盖全部房源。
        </p>
      )}
      {loadError && (
        <p className="banner error" role="alert">
          {loadError}
        </p>
      )}
      <div className="body">
        <FilterBar
          meta={meta}
          category={category}
          onCategory={changeCategory}
          filters={filters}
          onFilters={setFilters}
          metric={metric}
          onMetric={setMetric}
          matched={filtered.length}
          placeCount={stats.length}
          onSale={onSale}
        />
        <div className="map-wrap">
          <MapView
            places={places}
            stats={stats}
            metric={metric}
            breaks={breaks}
            selected={selected}
            onSelect={select}
          />
        </div>
        <div className="details">
          <PlacePanel
            place={selectedPlace}
            stat={selectedStat}
            listings={selectedListings}
            category={shownCategory}
            cityName={selectedPlace ? (areaNames.get(selectedPlace.city) ?? '') : ''}
          />
          {shown && (
            <TrendPanel
              meta={meta}
              areas={areas}
              trends={shown.data.trends}
              category={shown.category}
              area={area}
              onArea={setArea}
            />
          )}
          <footer className="sources muted small">
            <p>房源：{meta.sources.listings}</p>
            <p>坐标：{meta.sources.geo}</p>
            <p>底图：地理院タイル（国土地理院）</p>
          </footer>
        </div>
      </div>
    </div>
  )
}
