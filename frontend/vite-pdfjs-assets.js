import { createRequire } from 'node:module'
import { readdirSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'

// PDF.js dynamically fetches these files by name; Vite cannot discover them from
// imports. Keep the complete, version-matched resource directories and licenses
// local, without checking generated copies into public/ or the repository.
export function pdfjsAssets() {
  const packageRoot = dirname(createRequire(import.meta.url).resolve('pdfjs-dist/package.json'))
  const assets = new Map()
  for (const directory of ['wasm', 'cmaps', 'standard_fonts']) {
    for (const file of readdirSync(join(packageRoot, directory), { withFileTypes: true })) {
      if (file.isFile()) assets.set(`assets/pdfjs/${directory}/${file.name}`, join(packageRoot, directory, file.name))
    }
  }
  let base = '/'
  return {
    name: 'local-pdfjs-assets',
    configResolved(config) { base = new URL(config.base, 'http://localhost').pathname },
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const pathname = new URL(req.url, 'http://localhost').pathname
        const name = pathname.startsWith(base) ? pathname.slice(base.length) : pathname.slice(1)
        const file = assets.get(name)
        if (!file || !['GET', 'HEAD'].includes(req.method)) return next()
        res.setHeader('Content-Type', name.endsWith('.js') ? 'text/javascript' : name.endsWith('.wasm') ? 'application/wasm' : 'application/octet-stream')
        res.setHeader('Cache-Control', 'no-cache')
        res.end(req.method === 'HEAD' ? undefined : readFileSync(file))
      })
    },
    generateBundle() {
      for (const [fileName, path] of assets) this.emitFile({ type: 'asset', fileName, source: readFileSync(path) })
    },
  }
}
