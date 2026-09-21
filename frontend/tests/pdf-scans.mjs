import assert from 'node:assert/strict'
import { readFile, mkdir } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'
import { build, createServer, preview } from 'vite'
import { chromium } from '@playwright/test'

const root = fileURLToPath(new URL('../', import.meta.url))
const outDir = resolve(root, 'node_modules/.cache/pdf-scans-build')
const evidence = resolve(root, 'node_modules/.cache/pdf-scans-evidence')
await mkdir(evidence, { recursive: true })
const common = { root, configFile: resolve(root, 'vite.config.js'), logLevel: 'error' }
const browser = await chromium.launch({ headless: true })
let failures = 0
try {
  for (const mode of ['dev', 'build']) {
    let server
    if (mode === 'dev') { server = await createServer({ ...common, server: { port: 0, host: '127.0.0.1', open: false } }); await server.listen() }
    else {
      await build({ ...common, base: '/portal/', build: { outDir, emptyOutDir: true, rollupOptions: { input: resolve(root, 'tests/pdf-scans.html') } } })
      server = await preview({ ...common, base: '/portal/', build: { outDir }, preview: { port: 0, host: '127.0.0.1', open: false } })
    }
    const origin = server.resolvedUrls.local[0]
    try {
      for (const fixture of ['ccitt', 'jbig2', 'jpx', 'symbol', 'cmap']) {
        const page = await browser.newPage()
        const warnings = [], requests = []
        page.on('console', msg => { if (/warn|error/.test(msg.type()) || /Warning:/.test(msg.text())) warnings.push(msg.text()) })
        page.on('request', request => requests.push(request.url()))
        try {
          await page.goto(`${origin}tests/pdf-scans.html`)
          await page.waitForFunction(() => typeof window.renderScan === 'function')
          const bytes = [...await readFile(resolve(root, `tests/fixtures/${fixture}.pdf`))]
          const result = await page.evaluate(bytes => window.renderScan(bytes), bytes)
          await page.screenshot({ path: resolve(evidence, `${mode}-${fixture}.png`) })
          console.log(JSON.stringify({ mode, fixture, ...result, warnings, decoderRequests: requests.filter(url => /pdfjs\/|fallback|\.wasm/.test(url)) }))
          if (fixture === 'symbol' || fixture === 'cmap') {
            assert.ok(result.dark > 100, `${fixture}: expected visible text`)
            assert.ok(requests.some(url => url.includes(fixture === 'symbol' ? '/standard_fonts/FoxitSymbol.pfb' : '/cmaps/UniJIS-UCS2-H.bcmap')))
          } else {
            assert.equal(result.dark, 4608, `${fixture}: expected black rectangle, not an empty canvas`)
            assert.deepEqual(result.inside, [0, 0, 0, 255])
            assert.deepEqual(result.outside, [255, 255, 255, 255])
          }
          assert.deepEqual(warnings, [])
          assert.ok(requests.every(url => new URL(url).origin === new URL(origin).origin), 'all worker/decoder requests must remain same-origin')
        } catch (error) { failures++; console.error(`${mode}/${fixture}: ${error.message}`) }
        finally { await page.close() }
      }
    } finally { if (mode === 'dev') await server.close(); else await new Promise(resolve => server.httpServer.close(resolve)) }
  }
} finally { await browser.close() }
assert.equal(failures, 0, `${failures} scan render regressions`)
