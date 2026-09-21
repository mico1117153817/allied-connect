import React from 'react'
import { api } from '../lib/api'
import { complianceError } from '../lib/compliance'

// Engine, worker and version-matched decoder/font resources are served locally.
export async function loadLocalPdf(bytes) {
  const [pdfjs, worker] = await Promise.all([import('pdfjs-dist'), import('pdfjs-dist/build/pdf.worker.min.mjs?url')])
  pdfjs.GlobalWorkerOptions.workerSrc = worker.default
  // Absolute directory URLs (including trailing slash) also work inside the worker.
  const assets = new URL(`${import.meta.env.BASE_URL}assets/pdfjs/`, window.location.origin)
  return pdfjs.getDocument({
    data: new Uint8Array(bytes), isEvalSupported: false, useWasm: false, useSystemFonts: true,
    wasmUrl: new URL('wasm/', assets).href,
    cMapUrl: new URL('cmaps/', assets).href, cMapPacked: true,
    standardFontDataUrl: new URL('standard_fonts/', assets).href,
  })
}
const buttonClass = 'border rounded-lg px-3 py-2 text-sm disabled:opacity-40'
export default function CorporatePdfViewer({ companyId, document: doc, onClose, loadPdf = loadLocalPdf }) {
  const [pdf, setPdf] = React.useState(null)
  const [error, setError] = React.useState('')
  const [page, setPage] = React.useState(1)
  const [zoom, setZoom] = React.useState(1)
  const [width, setWidth] = React.useState(600)
  const [rendering, setRendering] = React.useState(false)
  const dialog = React.useRef(null)
  const closeButton = React.useRef(null)
  const close = React.useRef(onClose)
  close.current = onClose
  React.useEffect(() => {
    if (typeof document === 'undefined' || !dialog.current) return
    const opener = document.activeElement
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    closeButton.current?.focus()
    const keydown = event => {
      if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close.current(); return }
      if (event.key !== 'Tab') return
      const items = Array.from(dialog.current.querySelectorAll('button:not(:disabled), [href], input:not(:disabled), [tabindex="0"]'))
      const first = items[0], last = items[items.length - 1]
      if (event.shiftKey ? document.activeElement === first : document.activeElement === last) {
        event.preventDefault(); (event.shiftKey ? last : first)?.focus()
      }
    }
    const focusin = event => { if (!dialog.current.contains(event.target)) closeButton.current?.focus() }
    document.addEventListener('keydown', keydown, true)
    document.addEventListener('focusin', focusin, true)
    return () => {
      document.removeEventListener('keydown', keydown, true)
      document.removeEventListener('focusin', focusin, true)
      document.body.style.overflow = overflow
      if (opener?.isConnected) opener.focus()
    }
  }, [])
  const canvas = React.useRef(null)
  const viewport = React.useRef(null)
  React.useEffect(() => {
    const controller = new AbortController()
    let loadingTask
    ;(async () => {
      try {
        const response = await api.get(`/api/compliance/companies/${companyId}/corporate-documents/${doc.id}/view`, { responseType: 'arraybuffer', signal: controller.signal })
        if (controller.signal.aborted) return
        loadingTask = await loadPdf(response.data)
        if (controller.signal.aborted) { await loadingTask.destroy(); return }
        const document = await loadingTask.promise
        if (!controller.signal.aborted) setPdf(document)
      } catch (err) { if (!controller.signal.aborted) setError(complianceError(err)) }
    })()
    return () => { controller.abort(); loadingTask?.destroy() }
  }, [companyId, doc.id, loadPdf])
  React.useEffect(() => {
    const node = viewport.current
    if (!node) return
    const resize = () => setWidth(Math.max(100, node.clientWidth - 32))
    resize()
    if (typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(resize)
    observer.observe(node)
    return () => observer.disconnect()
  }, [])
  React.useEffect(() => {
    if (!pdf || !canvas.current) return
    let cancelled = false, task
    setRendering(true)
    ;(async () => {
      try {
        const pdfPage = await pdf.getPage(page)
        if (cancelled) return
        const base = pdfPage.getViewport({ scale: 1 })
        const scale = width / base.width * zoom
        const view = pdfPage.getViewport({ scale })
        const ratio = Math.min(globalThis.devicePixelRatio || 1, 2)
        const target = canvas.current
        target.width = Math.floor(view.width * ratio); target.height = Math.floor(view.height * ratio)
        target.style.width = `${view.width}px`; target.style.height = `${view.height}px`
        task = pdfPage.render({ canvasContext: target.getContext('2d'), viewport: view, transform: ratio === 1 ? null : [ratio, 0, 0, ratio, 0, 0] })
        await task.promise
      } catch (err) { if (!cancelled && err.name !== 'RenderingCancelledException') setError(complianceError(err)) }
      finally { if (!cancelled) setRendering(false) }
    })()
    return () => { cancelled = true; task?.cancel() }
  }, [pdf, page, zoom, width])
  return <div className="fixed inset-0 z-[60] bg-black/70 p-2 sm:p-4" onClick={e => e.stopPropagation()}><section ref={dialog} role="dialog" aria-modal="true" aria-label={`PDF: ${doc.original_file_name}`} className="bg-white rounded-xl w-full h-full flex flex-col">
    <header className="flex justify-between items-center gap-3 p-3 border-b"><h2 className="font-semibold break-all">{doc.original_file_name}</h2><button ref={closeButton} type="button" onClick={onClose} className={`${buttonClass} shrink-0`}>Close PDF</button></header>
    {error && <p role="alert" className="p-4 text-red-700">Unable to display PDF: {error}. Try downloading the PDF.</p>}
    {!pdf && !error && <p role="status" className="p-4">Loading PDF…</p>}
    {pdf && <div className="flex flex-wrap items-center gap-2 p-2 border-b" aria-label="PDF controls">
      <button type="button" className={buttonClass} disabled={page <= 1} onClick={() => setPage(n => n - 1)}>Previous page</button>
      <span aria-live="polite" className="text-sm">Page {page} of {pdf.numPages}</span>
      <button type="button" className={buttonClass} disabled={page >= pdf.numPages} onClick={() => setPage(n => n + 1)}>Next page</button>
      <button type="button" className={buttonClass} disabled={zoom <= 0.5} onClick={() => setZoom(n => Math.max(0.5, n - 0.25))}>Zoom out</button>
      <button type="button" className={buttonClass} disabled={zoom >= 3} onClick={() => setZoom(n => Math.min(3, n + 0.25))}>Zoom in</button>
      <button type="button" className={buttonClass} onClick={() => setZoom(1)}>Fit width</button>
    </div>}
    <div ref={viewport} className="flex-1 min-h-0 overflow-auto overscroll-contain bg-gray-100 p-4" aria-busy={rendering}>
      {rendering && <p role="status">Rendering page…</p>}
      <canvas ref={canvas} role="img" aria-label={`${doc.original_file_name}, page ${page}`} className={pdf ? 'block mx-auto shadow' : 'hidden'} />
    </div>
  </section></div>
}
