import type { PlaceStat } from '../aggregate'
import { formatArea, formatCount, formatMan, formatRange, formatUnit } from '../format'
import type { CategoryKey, Listing, Place } from '../types'

const MAX_ROWS = 200
const SUUMO = 'https://suumo.jp'
const PRECISION_NOTE: Record<string, string> = {
  town: '位置为町的中心（地址没有对应的丁目）',
  city: '位置为区市町村的中心（地址无法匹配到町）',
}

interface Props {
  place: Place | null
  stat: PlaceStat | null
  listings: Listing[]
  category: CategoryKey
  cityName: string
}

export function PlacePanel({ place, stat, listings, category, cityName }: Props) {
  if (!place || !stat) {
    return (
      <section className="card place">
        <p className="hint">点击地图上的圆点，查看该町丁目的房源。</p>
      </section>
    )
  }
  const house = category.endsWith('house')
  const sorted = [...listings].sort((a, b) => (a.price ?? Infinity) - (b.price ?? Infinity))
  return (
    <section className="card place" aria-label={`${place.name}的房源`}>
      <header className="place-head">
        <h2>
          {place.name}
          <span className="muted"> {cityName}</span>
        </h2>
        <p>
          {formatCount(stat.count)} 套 · 中位 {formatMan(stat.price)}
          {stat.unit !== null && ` · 单价 ${formatUnit(stat.unit)}`}
        </p>
        {PRECISION_NOTE[place.precision] && (
          <p className="muted small">{PRECISION_NOTE[place.precision]}</p>
        )}
      </header>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">物件</th>
              <th scope="col" className="num">
                价格
              </th>
              <th scope="col" className="num">
                面积
              </th>
              <th scope="col">间取</th>
              <th scope="col">交通</th>
            </tr>
          </thead>
          <tbody>
            {sorted.slice(0, MAX_ROWS).map((l) => (
              <tr key={l.id}>
                <td>
                  {l.path ? (
                    <a href={`${SUUMO}${l.path}`} target="_blank" rel="noopener noreferrer">
                      {l.name ?? '（无名称）'}
                    </a>
                  ) : (
                    (l.name ?? '（无名称）')
                  )}
                  <div className="muted small">
                    {l.built ? `築 ${l.built}` : ''}
                    {l.path?.startsWith('/tochi/') ? '土地' : ''}
                    {l.first_seen ? ` · 首见 ${l.first_seen}` : ''}
                    {l.price_changed ? ` · 调价 ${l.price_changed}` : ''}
                  </div>
                </td>
                <td className="num">{formatRange(l.price, l.price_max, formatMan)}</td>
                <td className="num">
                  {formatRange(l.size, l.size_max, formatArea)}
                  {house && l.land !== null && <div className="muted small">土地 {formatArea(l.land)}</div>}
                </td>
                <td>{l.layout ?? '—'}</td>
                <td>
                  {l.station ?? '—'}
                  {l.walk !== null && <span className="muted"> 徒步{l.walk}分</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {sorted.length > MAX_ROWS && (
        <p className="muted small">只显示价格最低的 {MAX_ROWS} 套。</p>
      )}
    </section>
  )
}
