import { type Filters, type Metric, NO_FILTERS } from '../aggregate'
import { formatCount } from '../format'
import type { CategoryKey, Meta } from '../types'

interface Props {
  meta: Meta
  category: CategoryKey
  onCategory: (category: CategoryKey) => void
  filters: Filters
  onFilters: (filters: Filters) => void
  metric: Metric
  onMetric: (metric: Metric) => void
  matched: number
  placeCount: number
  onSale: number | null
}

function parse(value: string): number | null {
  if (value.trim() === '') return null
  const number = Number(value)
  return Number.isFinite(number) && number >= 0 ? number : null
}

function RangeInput(props: {
  label: string
  unit: string
  min: number | null
  max: number | null
  onChange: (min: number | null, max: number | null) => void
}) {
  const { label, unit, min, max, onChange } = props
  return (
    <div className="range" role="group" aria-label={label}>
      <span className="range-label">
        {label}
        <span className="unit">（{unit}）</span>
      </span>
      <input
        type="number"
        inputMode="numeric"
        min={0}
        placeholder="下限"
        aria-label={`${label}下限`}
        value={min ?? ''}
        onChange={(e) => onChange(parse(e.target.value), max)}
      />
      <span aria-hidden="true">～</span>
      <input
        type="number"
        inputMode="numeric"
        min={0}
        placeholder="上限"
        aria-label={`${label}上限`}
        value={max ?? ''}
        onChange={(e) => onChange(min, parse(e.target.value))}
      />
    </div>
  )
}

export function FilterBar(props: Props) {
  const { meta, category, filters, onFilters, metric } = props
  const unitAvailable = category !== 'new_condo'
  const active = Object.values(filters).some((v) => v !== null)
  return (
    <section className="filters" aria-label="筛选">
      <div className="segmented categories" role="radiogroup" aria-label="类别">
        {meta.categories.map((c) => (
          <button
            key={c.key}
            type="button"
            role="radio"
            aria-checked={c.key === category}
            className={c.key === category ? 'selected' : ''}
            onClick={() => props.onCategory(c.key)}
          >
            {c.label}
          </button>
        ))}
      </div>
      <div className="filter-row">
        <RangeInput
          label="价格"
          unit="万円"
          min={filters.priceMin}
          max={filters.priceMax}
          onChange={(priceMin, priceMax) => onFilters({ ...filters, priceMin, priceMax })}
        />
        <RangeInput
          label={category.endsWith('house') ? '建筑面积' : '专有面积'}
          unit="m²"
          min={filters.sizeMin}
          max={filters.sizeMax}
          onChange={(sizeMin, sizeMax) => onFilters({ ...filters, sizeMin, sizeMax })}
        />
      </div>
      <div className="filter-row filter-foot">
        <div className="segmented small" role="radiogroup" aria-label="颜色表示">
          <button
            type="button"
            role="radio"
            aria-checked={metric === 'price'}
            className={metric === 'price' ? 'selected' : ''}
            onClick={() => props.onMetric('price')}
          >
            价格
          </button>
          <button
            type="button"
            role="radio"
            aria-checked={metric === 'unit'}
            className={metric === 'unit' ? 'selected' : ''}
            disabled={!unitAvailable}
            title={unitAvailable ? undefined : '新築マンション的价格和面积都是区间，不计算单价'}
            onClick={() => props.onMetric('unit')}
          >
            单价
          </button>
        </div>
        {active && (
          <button type="button" className="link-button" onClick={() => onFilters(NO_FILTERS)}>
            清除筛选
          </button>
        )}
      </div>
      <p className="summary">
        地图上 <strong>{formatCount(props.matched)}</strong> 套，{formatCount(props.placeCount)}{' '}
        个町丁目
        {props.onSale !== null && (
          <span className="muted">（汇总页在售 {formatCount(props.onSale)} 套）</span>
        )}
      </p>
    </section>
  )
}
