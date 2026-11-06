/**
 * Where the JSON comes from.
 *
 * - GitHub: the `site` branch of the private data repository, read through the REST API
 *   with the visitor's own read-only token. Nothing is published with this site.
 * - Local: `public/data/` during development (`suumoviz build --out public/data`).
 */
import {
  AREA_FIELDS,
  type Area,
  type CategoryData,
  type CategoryKey,
  type Dataset,
  decodeTable,
  FORMAT_VERSION,
  LISTING_FIELDS,
  type Listing,
  type Meta,
  PLACE_FIELDS,
  type Place,
  type Table,
  type Trends,
} from './types'

export const DEFAULT_REPO = 'Imanity/suumoviz-data'
export const DATA_REF = 'site'
const REPO_PATTERN = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/

export class DataError extends Error {
  readonly status: number | undefined

  constructor(message: string, status?: number) {
    super(message)
    this.name = 'DataError'
    this.status = status
  }

  /** The token or repository is wrong: ask for credentials again. */
  get isAuth(): boolean {
    return this.status === 401 || this.status === 403 || this.status === 404
  }
}

export interface DataSource {
  label: string
  get<T>(path: string): Promise<T>
}

type Fetch = typeof fetch

export function isValidRepo(repo: string): boolean {
  return REPO_PATTERN.test(repo)
}

export function contentsUrl(repo: string, path: string): string {
  return `https://api.github.com/repos/${repo}/contents/${path}?ref=${DATA_REF}`
}

export function statusMessage(status: number): string {
  switch (status) {
    case 401:
      return 'Token 无效或已过期。'
    case 403:
      return 'Token 没有读取权限，或 GitHub API 达到速率限制。'
    case 404:
      return '找不到数据：仓库名不对、Token 没有这个仓库的权限，或 site 分支尚未生成。'
    default:
      return `读取数据失败（HTTP ${status}）。`
  }
}

export function githubSource(repo: string, token: string, fetchImpl: Fetch = fetch): DataSource {
  if (!isValidRepo(repo)) {
    throw new DataError('仓库名应为 owner/repo 的形式。')
  }
  return {
    label: repo,
    async get<T>(path: string): Promise<T> {
      let response: Response
      try {
        response = await fetchImpl(contentsUrl(repo, path), {
          headers: {
            Authorization: `Bearer ${token}`,
            Accept: 'application/vnd.github.raw+json',
            'X-GitHub-Api-Version': '2022-11-28',
          },
          cache: 'no-cache', // revalidate with the ETag; unchanged files come back as 304
        })
      } catch {
        throw new DataError('无法连接 GitHub，请检查网络。')
      }
      if (!response.ok) {
        throw new DataError(statusMessage(response.status), response.status)
      }
      return (await response.json()) as T
    },
  }
}

export function localSource(base: string, fetchImpl: Fetch = fetch): DataSource {
  return {
    label: '本地数据',
    async get<T>(path: string): Promise<T> {
      const response = await fetchImpl(`${base}${path}`, { cache: 'no-cache' })
      if (!response.ok) {
        throw new DataError(
          `本地数据不存在（${path}）。请先运行 suumoviz build --out public/data。`,
          response.status,
        )
      }
      return (await response.json()) as T
    },
  }
}

export async function loadDataset(source: DataSource): Promise<Dataset> {
  const meta = await source.get<Meta>('meta.json')
  if (meta.version !== FORMAT_VERSION) {
    throw new DataError(`数据格式版本 ${meta.version} 与页面（${FORMAT_VERSION}）不一致。`)
  }
  const [areas, places] = await Promise.all([
    source.get<Table>('areas.json'),
    source.get<Table>('places.json'),
  ])
  return {
    meta,
    areas: decodeTable<Area>(areas, AREA_FIELDS),
    places: decodeTable<Place>(places, PLACE_FIELDS),
  }
}

export async function loadCategory(
  source: DataSource,
  category: CategoryKey,
): Promise<CategoryData> {
  const [listings, trends] = await Promise.all([
    source.get<Table & { category: string }>(`listings/${category}.json`),
    source.get<Trends>(`trends/${category}.json`),
  ])
  return { listings: decodeTable<Listing>(listings, LISTING_FIELDS), trends }
}
