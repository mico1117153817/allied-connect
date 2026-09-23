// Exercise the real viewer loader and worker, without replacing PDF.js.
import { loadLocalPdf } from '../src/components/CorporatePdfViewer.jsx'
window.renderScan = async bytes => {
  const task = await loadLocalPdf(new Uint8Array(bytes))
  try {
    const pdf = await task.promise
    const page = await pdf.getPage(1)
    const canvas = document.querySelector('canvas')
    const viewport = page.getViewport({ scale: 1 })
    canvas.width = viewport.width; canvas.height = viewport.height
    const ctx = canvas.getContext('2d', { willReadFrequently: true })
    await page.render({ canvasContext: ctx, viewport }).promise
    const pixels = ctx.getImageData(0, 0, 128, 128).data
    let dark = 0
    for (let i = 0; i < pixels.length; i += 4) if (pixels[i] < 64 && pixels[i + 1] < 64 && pixels[i + 2] < 64 && pixels[i + 3] === 255) dark++
    const pixel = (x, y) => [...ctx.getImageData(x, y, 1, 1).data]
    return { dark, inside: pixel(32, 64), outside: pixel(96, 64) }
  } finally { await task.destroy() }
}
