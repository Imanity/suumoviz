/**
 * Area boundaries: geo/areas.json, one TopoJSON topology written by
 * tools/make_boundaries.py with three objects (city, town, chome); every geometry has
 * properties {id, name}. Public data (e-Stat), so not obfuscated.
 */

import type { Feature, FeatureCollection, MultiPolygon, Polygon, Position } from 'geojson'
import { type Level, LEVELS, lineage } from './data'

export type BBox = [number, number, number, number] // west, south, east, north

export interface AreaInfo {
  code: string
  name: string
  level: Level
  bbox: BBox
}

export interface Areas {
  features: Record<Level, FeatureCollection<Polygon | MultiPolygon, { id: string; name: string }>>
  info: Map<string, AreaInfo>
}

type ArcIndexes = number[]
interface TopoGeometry {
  type: 'Polygon' | 'MultiPolygon' | null
  arcs?: ArcIndexes[] | ArcIndexes[][]
  properties: { id: string; name: string }
}
interface Topology {
  type: 'Topology'
  transform?: { scale: [number, number]; translate: [number, number] }
  arcs: number[][][]
  objects: Record<string, { type: 'GeometryCollection'; geometries: TopoGeometry[] }>
}

function decodeArcs(topology: Topology): Position[][] {
  const t = topology.transform
  return topology.arcs.map((arc) => {
    if (!t) return arc.map(([x, y]) => [x, y])
    let x = 0
    let y = 0
    return arc.map(([dx, dy]) => {
      x += dx
      y += dy
      return [x * t.scale[0] + t.translate[0], y * t.scale[1] + t.translate[1]]
    })
  })
}

function ring(indexes: ArcIndexes, arcs: Position[][]): Position[] {
  const points: Position[] = []
  for (const index of indexes) {
    const arc = index < 0 ? [...arcs[~index]].reverse() : arcs[index]
    // consecutive arcs share their joining point
    points.push(...(points.length ? arc.slice(1) : arc))
  }
  return points
}

function extend(bbox: BBox, rings: Position[][]): void {
  for (const r of rings) {
    for (const [x, y] of r) {
      if (x < bbox[0]) bbox[0] = x
      if (y < bbox[1]) bbox[1] = y
      if (x > bbox[2]) bbox[2] = x
      if (y > bbox[3]) bbox[3] = y
    }
  }
}

export function parseAreas(value: unknown): Areas {
  const topology = value as Topology
  if (topology?.type !== 'Topology') throw new Error('边界数据格式不正确')
  const arcs = decodeArcs(topology)
  const info = new Map<string, AreaInfo>()
  const features = {} as Areas['features']
  for (const level of LEVELS) {
    const geometries = topology.objects[level]?.geometries ?? []
    const list: Feature<Polygon | MultiPolygon, { id: string; name: string }>[] = []
    for (const g of geometries) {
      if (!g.type || !g.arcs) continue
      const bbox: BBox = [Infinity, Infinity, -Infinity, -Infinity]
      const { id, name } = g.properties
      let geometry: Polygon | MultiPolygon
      if (g.type === 'Polygon') {
        const rings = (g.arcs as ArcIndexes[]).map((r) => ring(r, arcs))
        extend(bbox, rings)
        geometry = { type: 'Polygon', coordinates: rings }
      } else {
        const polygons = (g.arcs as ArcIndexes[][]).map((p) => p.map((r) => ring(r, arcs)))
        polygons.forEach((p) => extend(bbox, p))
        geometry = { type: 'MultiPolygon', coordinates: polygons }
      }
      list.push({ type: 'Feature', geometry, properties: { id, name } })
      info.set(id, { code: id, name, level, bbox })
    }
    features[level] = { type: 'FeatureCollection', features: list }
  }
  return { features, info }
}

export async function loadAreas(base: string, fetchFn: typeof fetch = fetch): Promise<Areas> {
  const response = await fetchFn(`${base}geo/areas.json`)
  if (!response.ok) throw new Error(`读取边界数据失败（HTTP ${response.status}）`)
  return parseAreas(await response.json())
}

/** "世田谷区 成城 成城八丁目" style names from the municipality down. */
export function pathNames(code: string, info: Map<string, AreaInfo>): string[] {
  return lineage(code).flatMap((c) => {
    const name = info.get(c)?.name
    return name ? [name] : []
  })
}

/** Name for lists and tooltips: a town or chome gets its municipality in front. */
export function displayName(code: string, info: Map<string, AreaInfo>): string {
  const names = pathNames(code, info)
  if (names.length === 0) return code
  return names.length === 1 ? names[0] : `${names[0]} ${names[names.length - 1]}`
}
