import test, { after } from 'node:test'
import assert from 'node:assert/strict'
import { mkdirSync, rmSync } from 'node:fs'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { buildSync } from 'esbuild'
import React from 'react'
import TestRenderer, { act } from 'react-test-renderer'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
const directory = fileURLToPath(new URL('../../node_modules/.cache/', import.meta.url))
mkdirSync(directory, { recursive: true })
const bundle = `${directory}/corporate-test-${process.pid}.mjs`
buildSync({ stdin: { contents: "export { default as CorporateDocuments } from './src/components/CorporateDocuments.jsx'; export { api } from './src/lib/api.js'", resolveDir: fileURLToPath(new URL('../../', import.meta.url)), loader: 'jsx' }, bundle: true, platform: 'node', format: 'esm', packages: 'external', external: ['*?url'], define: { 'import.meta.env.VITE_API_URL': '""' }, outfile: bundle })
const { CorporateDocuments, api } = await import(pathToFileURL(bundle).href)
after(() => rmSync(bundle, { force: true }))
globalThis.localStorage = { getItem: () => null }
globalThis.window = { confirm: () => true }
const tick = () => new Promise(resolve => setTimeout(resolve, 20))
const categories = ['EIN', 'Articles of Incorporation', 'Operating Agreement', 'Bylaws', 'Certificate of Good Standing', 'Other Corporate Document']
const docs = [1, 2, 3].map(id => ({ id, company_id: 1, document_type: 'EIN', original_file_name: `document-${id}.pdf`, status: id === 3 ? 'replaced' : 'active' }))
const buttons = (r, label) => r.root.findAllByType('button').filter(n => n.children.join('') === label)
async function setup(t, company = { id: 1, can_edit: true, is_active: true }, request) {
  const calls = []
  api.defaults.adapter = async config => {
    calls.push(config)
    const response = await request?.(config)
    return { status: 200, config, headers: {}, data: { documents: docs, categories, can_edit: true }, ...response }
  }
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  const tree = value => React.createElement(QueryClientProvider, { client }, React.createElement(CorporateDocuments, { company: value }))
  let r
  await act(async () => { r = TestRenderer.create(tree(company)); await tick() })
  await act(tick)
  t.after(async () => { await act(async () => r.unmount()); client.clear() })
  return { r, calls, client, switchCompany: async value => { await act(async () => { r.update(tree(value)); await tick() }); await act(tick) } }
}
test('six categories show active multiplicity and retained history without expiration or forms', async t => {
  const { r, calls } = await setup(t)
  assert.deepEqual(r.root.findAllByType('h4').map(n => n.children.join('')), categories)
  const text = JSON.stringify(r.toJSON())
  assert.match(text, /Uploaded/); assert.match(text, /Not uploaded/); assert.match(text, /Replaced history/)
  assert.equal(buttons(r, 'View PDF').length, 3)
  assert.equal(buttons(r, 'Download').length, 3)
  assert.equal(r.root.findAllByType('form').length, 0)
  assert.doesNotMatch(text, /expiration/i)
  assert.equal(calls[0].url, '/api/compliance/companies/1/corporate-documents')
})
test('uploads capture company and cannot submit company fields; switching clears pending selections and stale notices', async t => {
  let release
  const pending = new Promise(resolve => { release = resolve })
  const { r, calls, switchCompany } = await setup(t, undefined, config => config.method === 'post' ? pending : undefined)
  assert.equal(buttons(r, 'Upload PDF').length, 6)
  assert.equal(buttons(r, 'Replace').length, 2)
  assert.equal(buttons(r, 'Delete').length, 3)
  await act(async () => buttons(r, 'Upload PDF')[0].props.onClick())
  const file = new File(['%PDF-test'], 'ein.pdf', { type: 'application/pdf' })
  await act(async () => r.root.findByProps({ 'aria-label': 'Corporate PDF file' }).props.onChange({ target: { files: [file] } }))
  await act(async () => { buttons(r, 'Save PDF')[0].props.onClick(); await tick() })
  const post = calls.find(c => c.method === 'post')
  assert.equal(post.url, '/api/compliance/companies/1/corporate-documents')
  assert.equal(post.data.get('document_type'), 'EIN')
  assert.equal(post.data.get('file').name, 'ein.pdf')
  assert.ok(r.root.findAllByType('button').every(b => b.props.type === 'button'))
  assert.ok(!calls.some(c => c.method === 'put'))
  await switchCompany({ id: 2, can_edit: true, is_active: true })
  assert.equal(r.root.findAllByProps({ 'aria-label': 'Corporate PDF file' }).length, 0)
  await act(async () => { release({ data: { document: docs[0] } }); await tick() })
  assert.doesNotMatch(JSON.stringify(r.toJSON()), /PDF saved/)
})
test('delete and replacement require confirmation and use document-specific endpoints', async t => {
  const { r, calls } = await setup(t)
  window.confirm = () => false
  await act(async () => buttons(r, 'Delete')[0].props.onClick())
  assert.equal(calls.filter(c => c.method === 'delete').length, 0)
  window.confirm = () => true
  await act(async () => { buttons(r, 'Delete')[0].props.onClick(); await tick() }); await act(tick)
  assert.equal(calls.find(c => c.method === 'delete').url, '/api/compliance/companies/1/corporate-documents/1')
  await act(async () => buttons(r, 'Replace')[0].props.onClick())
  await act(async () => r.root.findByProps({ 'aria-label': 'Corporate PDF file' }).props.onChange({ target: { files: [new File(['%PDF'], 'replacement.pdf')] } }))
  window.confirm = () => false
  await act(async () => buttons(r, 'Save PDF')[0].props.onClick())
  assert.equal(calls.filter(c => c.method === 'post').length, 0)
  window.confirm = () => true
  await act(async () => { buttons(r, 'Save PDF')[0].props.onClick(); await tick() }); await act(tick)
  const post = calls.find(c => c.method === 'post')
  assert.equal(post.url, '/api/compliance/companies/1/corporate-documents/1/replace')
  assert.equal(post.data.has('document_type'), false)
})
test('view opens in-app immediately; closing/switching aborts bytes and discards late results', async t => {
  let release
  const pending = new Promise(resolve => { release = resolve })
  const { r, calls, switchCompany } = await setup(t, undefined, c => c.url.endsWith('/view') ? pending : undefined)
  await act(async () => { buttons(r, 'View PDF')[0].props.onClick(); await tick() })
  assert.equal(r.root.findAllByProps({ role: 'dialog' }).length, 1)
  const request = calls.find(c => c.url.endsWith('/view'))
  assert.equal(request.url, '/api/compliance/companies/1/corporate-documents/1/view')
  assert.equal(request.responseType, 'arraybuffer')
  await act(async () => buttons(r, 'Close PDF')[0].props.onClick())
  assert.equal(request.signal.aborted, true)
  await switchCompany({ id: 2, can_edit: true, is_active: true })
  await act(async () => { release({ data: new ArrayBuffer(5) }); await tick() })
  assert.equal(r.root.findAllByProps({ role: 'dialog' }).length, 0)
})
test('downloads authenticated bytes, revokes URLs on cleanup, and never follows server URLs', async t => {
  const created = [], revoked = [], links = []
  const originalCreate = URL.createObjectURL, originalRevoke = URL.revokeObjectURL
  URL.createObjectURL = blob => { created.push(blob); return 'blob:fixture' }
  URL.revokeObjectURL = url => revoked.push(url)
  globalThis.document = { createElement: () => { const link = { click() {}, remove() {} }; links.push(link); return link }, body: { appendChild() {} } }
  t.after(() => { URL.createObjectURL = originalCreate; URL.revokeObjectURL = originalRevoke; delete globalThis.document })
  const { r, calls, switchCompany } = await setup(t, undefined, c => c.url.endsWith('/download') ? { data: new Blob(['%PDF'], { type: 'application/pdf' }) } : undefined)
  await act(async () => { buttons(r, 'Download')[0].props.onClick(); await tick() })
  const request = calls.find(c => c.url.endsWith('/download'))
  assert.equal(request.url, '/api/compliance/companies/1/corporate-documents/1/download')
  assert.equal(request.responseType, 'blob')
  assert.equal(created.length, 1)
  assert.equal(links[0].download, 'document-1.pdf')
  await switchCompany({ id: 2, can_edit: true, is_active: true })
  assert.deepEqual(revoked, ['blob:fixture'])
})
test('late list responses stay in their company cache and cannot relabel the selected company', async t => {
  let release
  const pending = new Promise(resolve => { release = resolve })
  const { r, client, switchCompany } = await setup(t, undefined, c => c.url === '/api/compliance/companies/1/corporate-documents' ? pending : { data: { documents: [{ ...docs[0], company_id: 2, original_file_name: 'beta-only.pdf' }], can_edit: true } })
  assert.match(JSON.stringify(r.toJSON()), /Loading corporate documents/)
  await switchCompany({ id: 2, can_edit: true, is_active: true })
  await act(async () => { release({ data: { documents: docs, can_edit: true } }); await tick() })
  assert.match(JSON.stringify(r.toJSON()), /beta-only.pdf/)
  assert.doesNotMatch(JSON.stringify(r.toJSON()), /document-1.pdf/)
  assert.equal(client.getQueryData(['corporate-documents', 2]).documents[0].company_id, 2)
})
test('failed uploads show an error and release the busy safeguard for retry', async t => {
  const { r } = await setup(t, undefined, c => { if (c.method === 'post') throw new Error('Upload unavailable') })
  await act(async () => buttons(r, 'Upload PDF')[0].props.onClick())
  await act(async () => r.root.findByProps({ 'aria-label': 'Corporate PDF file' }).props.onChange({ target: { files: [new File(['%PDF'], 'file.pdf')] } }))
  await act(async () => { buttons(r, 'Save PDF')[0].props.onClick(); await tick() })
  assert.match(JSON.stringify(r.toJSON()), /Upload unavailable/)
  assert.equal(buttons(r, 'Save PDF')[0].props.disabled, false)
})
test('document editing follows can_edit and active, never can_manage', async t => {
  const { r, switchCompany } = await setup(t, { id: 1, can_edit: false, can_manage: true, is_active: true })
  for (const label of ['Upload PDF', 'Replace', 'Delete']) assert.equal(buttons(r, label).length, 0)
  await switchCompany({ id: 2, can_edit: true, can_manage: true, is_active: false })
  for (const label of ['Upload PDF', 'Replace', 'Delete']) assert.equal(buttons(r, label).length, 0)
  await switchCompany({ id: 3, can_edit: true, can_manage: false, is_active: true })
  assert.equal(buttons(r, 'Upload PDF').length, 6)
})
