import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, readdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'
import { build, createServer } from 'vite'

const root = fileURLToPath(new URL('../../', import.meta.url))
const configFile = resolve(root, 'vite.config.js')
const resources = ['wasm', 'cmaps', 'standard_fonts'].flatMap(directory =>
  readdirSync(resolve(root, `node_modules/pdfjs-dist/${directory}`)).map(name => ({
    url: `assets/pdfjs/${directory}/${name}`,
    bytes: readFileSync(resolve(root, `node_modules/pdfjs-dist/${directory}/${name}`)),
  })))

test('production emits every installed PDF.js decoder, CMap, font and license byte-for-byte', async () => {
  const result = await build({ root, configFile, logLevel: 'silent', build: {
    write: false, rollupOptions: { input: resolve(root, 'tests/pdf-scans.html') },
  } })
  const emitted = new Map(result.output.map(asset => [asset.fileName, asset]))
  for (const resource of resources) {
    const asset = emitted.get(resource.url)
    assert.ok(asset, `Missing local PDF.js resource: ${resource.url}`)
    assert.deepEqual(Buffer.from(asset.source), resource.bytes, resource.url)
  }
})

test('dev serves the same local resources, with executable JS/WASM MIME types, also under a base path', async () => {
  const server = await createServer({ root, configFile, base: '/portal/', logLevel: 'silent', server: { host: '127.0.0.1', port: 0 }, optimizeDeps: { noDiscovery: true, include: [] } })
  await server.listen()
  try {
    const origin = server.resolvedUrls.local[0]
    for (const resource of resources) {
      const response = await fetch(new URL(resource.url, origin))
      assert.equal(response.status, 200, resource.url)
      assert.deepEqual(Buffer.from(await response.arrayBuffer()), resource.bytes, resource.url)
      if (resource.url.endsWith('.js')) assert.match(response.headers.get('content-type'), /javascript/)
      if (resource.url.endsWith('.wasm')) assert.match(response.headers.get('content-type'), /application\/wasm/)
    }
  } finally { await server.close() }
})
