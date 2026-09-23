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
const bundle = `${directory}/company-calendar-test-${process.pid}.mjs`
buildSync({ stdin: { contents: "export { default as Calendar } from './src/pages/CompanyCalendar.jsx'; export { api } from './src/lib/api.js'", resolveDir: fileURLToPath(new URL('../../', import.meta.url)), loader: 'jsx' }, bundle: true, platform: 'node', format: 'esm', packages: 'external', define: { 'import.meta.env.VITE_API_URL': '""' }, outfile: bundle })
const { Calendar, api } = await import(pathToFileURL(bundle).href)
after(() => rmSync(bundle, { force: true }))
globalThis.localStorage = { getItem: () => null, removeItem: () => {} }
const tick = () => new Promise(resolve => setTimeout(resolve, 15))

async function renderCalendar(t) {
  const calls = []
  api.defaults.adapter = async config => {
    calls.push(config)
    const data = config.url === '/api/tasks/companies'
      ? { companies: [{ id: 4, legal_name: 'Fixture Company' }] }
      : { events: [{ id: 'task-9', source_type: 'task', source_id: 9, title: 'File annual report', start_at: new Date().toISOString(), all_day: false, color: '#dc2626' }] }
    return { data, config, status: 200, headers: {} }
  }
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  let renderer
  await act(async () => { renderer = TestRenderer.create(React.createElement(QueryClientProvider, { client }, React.createElement(Calendar))); await tick() })
  await act(tick)
  t.after(async () => { await act(async () => renderer.unmount()); client.clear() })
  return { renderer, calls }
}

test('calendar DOM selects a company, fetches its bounded event range and exposes all views', async t => {
  const { renderer, calls } = await renderCalendar(t)
  assert.equal(renderer.root.findByProps({ 'aria-label': 'Company' }).props.value, '4')
  const request = calls.find(call => call.url === '/api/company-calendar')
  assert.equal(request.params.company_id, '4')
  assert.ok(request.params.start && request.params.end)
  for (const label of ['Month', 'Week', 'Day', 'Today']) assert.ok(renderer.root.findAllByType('button').some(button => button.children.join('') === label))
})

test('task deadline click opens a source-date editor instead of standalone event detail', async t => {
  const { renderer } = await renderCalendar(t)
  const task = renderer.root.findAllByType('button').find(button => button.children.join('').includes('Task deadline: File annual report'))
  await act(async () => task.props.onClick())
  assert.equal(renderer.root.findByProps({ role: 'dialog' }).props['aria-label'], 'Edit Task Deadline')
  assert.match(renderer.root.findByProps({ role: 'dialog' }).findAllByType('p')[0].children.join(''), /source task/)
})
