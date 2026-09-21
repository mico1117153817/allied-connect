import test, { after } from 'node:test'
import assert from 'node:assert/strict'
import { mkdirSync, rmSync } from 'node:fs'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { buildSync } from 'esbuild'
import React from 'react'
import TestRenderer, { act } from 'react-test-renderer'
const directory = fileURLToPath(new URL('../../node_modules/.cache/', import.meta.url))
mkdirSync(directory, { recursive: true })
const bundle = `${directory}/pdf-test-${process.pid}.mjs`
buildSync({ stdin: { contents: "export { default as Viewer } from './src/components/CorporatePdfViewer.jsx'; export { api } from './src/lib/api.js'", resolveDir: fileURLToPath(new URL('../../', import.meta.url)), loader: 'jsx' }, bundle: true, platform: 'node', format: 'esm', packages: 'external', external: ['*?url'], define: { 'import.meta.env.VITE_API_URL': '""' }, outfile: bundle })
const { Viewer, api } = await import(pathToFileURL(bundle).href)
after(() => rmSync(bundle, { force: true }))
const tick = () => new Promise(resolve => setTimeout(resolve, 20))
const button = (r, label) => r.root.findAllByType('button').find(n => n.children.join('') === label)
globalThis.localStorage = { getItem: () => null }
test('modal focuses Close, traps Tab, closes on Escape and restores focus/body scrolling', async () => {
  const listeners = new Map()
  let restored = 0, focused = 0, closed = 0, prevented = 0
  const opener = { isConnected: true, focus: () => restored++ }
  const close = { focus: () => focused++ }
  const dialog = { querySelectorAll: () => [close], contains: target => target === close }
  globalThis.document = { activeElement: opener, body: { style: { overflow: 'auto' } }, addEventListener: (name, fn) => listeners.set(name, fn), removeEventListener: name => listeners.delete(name) }
  api.defaults.adapter = () => new Promise(() => {})
  let r
  await act(async () => { r = TestRenderer.create(React.createElement(Viewer, { companyId: 1, document: { id: 7 }, onClose: () => closed++ }), { createNodeMock: e => e.type === 'section' ? dialog : e.type === 'button' ? close : null }) })
  try {
    assert.equal(focused, 1)
    assert.equal(document.body.style.overflow, 'hidden')
    document.activeElement = close
    listeners.get('keydown')({ key: 'Tab', shiftKey: false, preventDefault: () => prevented++, stopPropagation() {} })
    assert.equal(prevented, 1)
    listeners.get('keydown')({ key: 'Escape', preventDefault() {}, stopPropagation() {} })
    assert.equal(closed, 1)
  } finally { await act(async () => r.unmount()); }
  assert.equal(document.body.style.overflow, 'auto')
  assert.equal(restored, 1)
  assert.equal(listeners.size, 0)
  delete globalThis.document
})
test('PDF bytes render to canvas with paging, zoom, fit-width and destroyed render tasks', async () => {
  const rendered = [], requested = []
  let destroyed = 0, cancelled = 0
  const pdf = { numPages: 2, getPage: async number => { requested.push(number); return { getViewport: ({ scale }) => ({ width: 600 * scale, height: 800 * scale }), render: options => { rendered.push(options); return { promise: Promise.resolve(), cancel: () => cancelled++ } } } } }
  const loadPdf = async bytes => { assert.ok(bytes instanceof ArrayBuffer); return { promise: Promise.resolve(pdf), destroy: () => { destroyed++ } } }
  api.defaults.adapter = async config => ({ config, status: 200, headers: {}, data: new ArrayBuffer(10) })
  const canvas = { style: {}, getContext: () => ({}) }
  let r
  await act(async () => { r = TestRenderer.create(React.createElement(Viewer, { companyId: 1, document: { id: 7, original_file_name: 'test.pdf' }, onClose() {}, loadPdf }), { createNodeMock: element => element.type === 'canvas' ? canvas : { clientWidth: 632 } }); await tick() })
  await act(tick)
  try {
    assert.equal(r.root.findAllByType('canvas').length, 1)
    assert.ok(rendered.length > 0)
    assert.equal(requested.at(-1), 1)
    assert.equal(button(r, 'Previous page').props.disabled, true)
    await act(async () => { button(r, 'Next page').props.onClick(); await tick() })
    assert.equal(requested.at(-1), 2)
    assert.equal(button(r, 'Next page').props.disabled, true)
    const fitWidth = canvas.width
    await act(async () => { button(r, 'Zoom in').props.onClick(); await tick() })
    assert.ok(canvas.width > fitWidth)
    await act(async () => { button(r, 'Fit width').props.onClick(); await tick() })
    assert.equal(canvas.width, fitWidth)
    assert.equal(r.root.findAllByType('iframe').length, 0)
  } finally { await act(async () => r.unmount()) }
  assert.equal(destroyed, 1)
  assert.ok(cancelled > 0)
})
