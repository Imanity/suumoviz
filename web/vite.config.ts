/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig, type Plugin } from 'vite'

// Only our own bundle runs; data comes from this site, tiles from GSI.
// MapLibre starts its worker from a blob: URL.
const CONTENT_SECURITY_POLICY = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob: https://cyberjapandata.gsi.go.jp",
  "connect-src 'self' https://cyberjapandata.gsi.go.jp",
  'worker-src blob:',
  'child-src blob:',
  "object-src 'none'",
  "base-uri 'none'",
  "form-action 'none'",
].join('; ')

function contentSecurityPolicy(): Plugin {
  return {
    name: 'content-security-policy',
    apply: 'build', // the dev server injects inline scripts for hot reload
    transformIndexHtml: () => [
      {
        tag: 'meta',
        attrs: { 'http-equiv': 'Content-Security-Policy', content: CONTENT_SECURITY_POLICY },
        injectTo: 'head-prepend',
      },
    ],
  }
}

// public/data/ comes from `suumoviz build` (the Pages workflow runs it before
// `vite build`; locally: `suumoviz build --data-dir data --out web/public/data`).
export default defineConfig(({ command, isPreview }) => ({
  // GitHub Pages serves the project at https://imanity.github.io/suumoviz/
  base: command === 'build' || isPreview ? '/suumoviz/' : '/',
  plugins: [react(), contentSecurityPolicy()],
  build: { chunkSizeWarningLimit: 1500 },
  test: { environment: 'node' },
}))
