import { type FormEvent, useState } from 'react'
import { DEFAULT_REPO } from '../source'

interface Props {
  initialRepo?: string
  error?: string
  busy: boolean
  onSubmit: (repo: string, token: string, remember: boolean) => void
}

const NEW_TOKEN_URL = 'https://github.com/settings/personal-access-tokens/new'

export function Login({ initialRepo, error, busy, onSubmit }: Props) {
  const [repo, setRepo] = useState(initialRepo ?? DEFAULT_REPO)
  const [token, setToken] = useState('')
  const [remember, setRemember] = useState(false)

  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (repo.trim() && token.trim()) onSubmit(repo.trim(), token.trim(), remember)
  }

  return (
    <main className="login">
      <form onSubmit={submit} className="card">
        <h1>SuumoViz</h1>
        <p className="muted">
          数据保存在私有仓库里。用一个只读 Token 连接，页面直接从 GitHub 读取，不经过其他服务器。
        </p>
        <label>
          数据仓库
          <input
            value={repo}
            onChange={(e) => setRepo(e.target.value)}
            autoComplete="off"
            spellCheck={false}
            required
          />
        </label>
        <label>
          Token
          <input
            type="password"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            autoComplete="off"
            spellCheck={false}
            placeholder="github_pat_…"
            required
          />
        </label>
        <label className="check">
          <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
          在这台设备上记住（默认只保存到关闭标签页为止）
        </label>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <button type="submit" disabled={busy}>
          {busy ? '连接中…' : '连接'}
        </button>
        <details>
          <summary>如何创建 Token</summary>
          <ol>
            <li>
              打开{' '}
              <a href={NEW_TOKEN_URL} target="_blank" rel="noopener noreferrer">
                Fine-grained personal access token
              </a>
              ；
            </li>
            <li>Repository access 选 “Only select repositories”，只勾选数据仓库；</li>
            <li>Permissions → Repository permissions → Contents 设为 “Read-only”，其他保持默认；</li>
            <li>设一个有效期（例如 90 天），生成后复制到上面。</li>
          </ol>
          <p className="muted small">
            Token 只用于读取该仓库，可以随时在 GitHub 上撤销。
          </p>
        </details>
      </form>
    </main>
  )
}
