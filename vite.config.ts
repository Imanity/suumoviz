/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig, type Plugin } from 'vite'

// Only our own bundle runs; data comes from the GitHub API, tiles from GSI.
// MapLibre starts its worker from a blob: URL.
const CONTENT_SECURITY_POLICY = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob: https://cyberjapandata.gsi.go.jp",
  "connect-src 'self' https://api.github.com https://cyberjapandata.gsi.go.jp",
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

// public/data/ holds private data for local development only. A production build never
// copies public/ (the deploy workflow also checks that dist/data does not exist).
const LOCAL_DATA = process.env.VITE_LOCAL_DATA === '1'

export default defineConfig(({ command, isPreview }) => ({
  // GitHub Pages serves the project at https://imanity.github.io/suumoviz/
  base: command === 'build' || isPreview ? '/suumoviz/' : '/',
  publicDir: command === 'build' && !LOCAL_DATA ? false : 'public',
  plugins: [react(), contentSecurityPolicy()],
  build: { chunkSizeWarningLimit: 1500 },
  test: { environment: 'node' },
}))
