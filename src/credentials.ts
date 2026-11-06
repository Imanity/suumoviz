/**
 * The visitor's repository + token. Kept for this tab only (sessionStorage) unless the
 * visitor asks to remember it on this device (localStorage). Every other Pages site of
 * the same account shares this origin, so "remember" is opt-in.
 */
const KEY = 'suumoviz.credentials'

export interface Credentials {
  repo: string
  token: string
}

function storages(): { session: Storage | null; local: Storage | null } {
  const get = (name: 'sessionStorage' | 'localStorage'): Storage | null => {
    try {
      return window[name]
    } catch {
      return null
    }
  }
  return { session: get('sessionStorage'), local: get('localStorage') }
}

function read(storage: Storage | null): Credentials | null {
  try {
    const raw = storage?.getItem(KEY)
    if (!raw) return null
    const value = JSON.parse(raw) as Partial<Credentials>
    return typeof value.repo === 'string' && typeof value.token === 'string'
      ? { repo: value.repo, token: value.token }
      : null
  } catch {
    return null
  }
}

export function loadCredentials(): Credentials | null {
  const { session, local } = storages()
  return read(session) ?? read(local)
}

export function saveCredentials(credentials: Credentials, remember: boolean): void {
  const { session, local } = storages()
  const keep = remember ? local : session
  const drop = remember ? session : local
  try {
    keep?.setItem(KEY, JSON.stringify(credentials))
    drop?.removeItem(KEY)
  } catch {
    // storage blocked: the credentials live only in memory for this page view
  }
}

export function clearCredentials(): void {
  const { session, local } = storages()
  for (const storage of [session, local]) {
    try {
      storage?.removeItem(KEY)
    } catch {
      // ignore
    }
  }
}
