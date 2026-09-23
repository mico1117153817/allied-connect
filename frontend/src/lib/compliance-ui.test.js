import test, { after } from 'node:test'
import assert from 'node:assert/strict'
import { mkdirSync, rmSync } from 'node:fs'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { buildSync } from 'esbuild'
import React from 'react'
import TestRenderer, { act } from 'react-test-renderer'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

// Local React runtime tests only: every HTTP request is handled by this fixture adapter.
const directory = fileURLToPath(new URL('../../node_modules/.cache/', import.meta.url))
mkdirSync(directory, { recursive: true })
const bundle = `${directory}/compliance-ui-test-${process.pid}.mjs`
buildSync({ stdin: { contents: "export { default as Compliance } from './src/pages/Compliance.jsx'; export { api } from './src/lib/api.js'", resolveDir: fileURLToPath(new URL('../../', import.meta.url)), loader: 'jsx' }, bundle: true, platform: 'node', format: 'esm', packages: 'external', define: { 'import.meta.env.VITE_API_URL': '""' }, outfile: bundle })
const { Compliance, api } = await import(pathToFileURL(bundle).href)
after(() => rmSync(bundle, { force: true }))
globalThis.localStorage = { getItem: () => null, removeItem: () => {} }
globalThis.window = { confirm: () => true, open: () => {}, location: {} }
const companies = [
  { id: 1, legal_name: 'Company Alpha', is_active: true, can_edit: true, can_manage: true, summary: { total: 1, active: 1 } },
  { id: 2, legal_name: 'Company Beta', is_active: true, can_edit: true, can_manage: true, summary: { total: 1, active: 1 } },
  { id: 3, legal_name: 'Archived Company', is_active: false, can_edit: false, can_manage: true, summary: { total: 1, active: 1 } },
]
const state = { state: 'Colorado', jurisdiction: 'Colorado', overall_status: 'Active', collection_license_requirement: 'Required', coa_requirement: 'Required', bond_requirement: 'Required', license_status: 'Active', coa_status: 'Active', bond_status: 'Active', annual_report_requirement: 'Annual', attachments: {}, issues: [] }
const tick = () => new Promise(resolve => setTimeout(resolve, 15))
const text = node => JSON.stringify(node.toJSON ? node.toJSON() : node.findAll(item => typeof item.type === 'string').map(item => ({ type: item.type, props: { ...item.props, children: undefined }, text: item.children.filter(child => typeof child === 'string') })))
const button = (renderer, label) => renderer.root.findAllByType('button').find(item => item.children.join('') === label)

async function setup(t, overrides = {}) {
  const calls = []
  api.defaults.adapter = async config => {
    const url = new URL(config.url, 'http://fixture.invalid')
    calls.push({ method: config.method, url, params: config.params, data: typeof config.data === 'string' ? JSON.parse(config.data) : config.data })
    if (overrides.request) {
      const response = await overrides.request(config, url)
      if (response) return { config, status: 200, headers: {}, ...response }
    }
    let data
    if (url.pathname === '/api/compliance/companies') data = { companies, can_manage: true, is_super_admin: true }
    else if (url.pathname === '/api/compliance') {
      const company = companies.find(item => String(item.id) === url.searchParams.get('company_id'))
      data = { company, can_edit: company.can_edit, states: [{ ...state, notes: company.legal_name }] }
    } else if (url.pathname.endsWith('/audit')) data = { events: [{ id: 1, user_name: 'Fixture reviewer', field: 'notes', old_value: null, new_value: 'Updated', created_at: '2026-09-20T16:30:00Z' }] }
    else if (/\/companies\/\d+$/.test(url.pathname)) data = companies.find(item => item.id === Number(url.pathname.split('/').at(-1)))
    else if (url.pathname.endsWith('/attachments')) data = { attachments: [] }
    else throw new Error(`Unexpected fixture request: ${config.method} ${url}`)
    return { data, config, status: 200, headers: {} }
  }
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 60000 }, mutations: { retry: false, gcTime: 0 } } })
  let renderer
  await act(async () => { renderer = TestRenderer.create(React.createElement(QueryClientProvider, { client }, React.createElement(Compliance))); await tick() })
  await act(tick)
  t.after(async () => { await act(async () => renderer.unmount()); client.clear() })
  return { renderer, calls, client }
}

async function selectCompany(renderer, id) {
  await act(async () => { renderer.root.findByProps({ 'aria-label': 'Compliance company' }).props.onChange({ target: { value: String(id) } }); await tick() })
  await act(tick)
}

async function openState(renderer) {
  await act(async () => renderer.root.findByProps({ 'aria-label': 'Edit Colorado compliance record' }).props.onClick())
}

test('company switching closes the editor and late Alpha save cannot close or relabel Beta editor', async t => {
  let release
  const pending = new Promise(resolve => { release = resolve })
  const { renderer, calls } = await setup(t, { request: async config => config.method === 'put' ? pending : null })
  await openState(renderer)
  await act(async () => { renderer.root.findByType('form').props.onSubmit({ preventDefault() {} }); await tick() })
  assert.equal(calls.find(call => call.method === 'put').url.searchParams.get('company_id'), '1')
  await selectCompany(renderer, 2)
  assert.equal(renderer.root.findAllByType('form').length, 0)
  await openState(renderer)
  await act(async () => { release({ data: {} }); await tick() })
  assert.equal(renderer.root.findAllByType('form').length, 1)
  assert.match(text(renderer), /Company Beta/)
  assert.doesNotMatch(text(renderer.root.findByType('form')), /Company Alpha/)
})

test('archived company renders read-only form and scoped audit history', async t => {
  const { renderer, calls } = await setup(t)
  await selectCompany(renderer, 3)
  await openState(renderer)
  assert.equal(renderer.root.findByType('fieldset').props.disabled, true)
  await act(async () => { button(renderer, 'Audit History').props.onClick(); await tick() })
  await act(tick)
  assert.match(text(renderer), /Fixture reviewer/)
  assert.match(text(renderer), /[AP]M/)
  assert.ok(calls.some(call => call.url.pathname === '/api/compliance/companies/3/audit' && call.params.state === 'Colorado'))
  await act(async () => button(renderer, 'PDF Files').props.onClick())
  assert.ok(renderer.root.findAllByType('button').filter(item => item.children.join('') === 'Upload PDF').every(item => item.props.disabled))
})

test('All Companies is a summary table and its counts open a single-company matrix', async t => {
  const { renderer } = await setup(t)
  await selectCompany(renderer, 'all')
  assert.doesNotMatch(text(renderer), /50-State Compliance Matrix/)
  await act(async () => { renderer.root.findByProps({ 'aria-label': 'Company Beta: Licenses expiring · 30 days' }).props.onClick(); await tick() })
  await act(tick)
  assert.match(text(renderer), /Company Beta/)
  assert.equal(renderer.root.findByProps({ 'aria-label': 'Filter deadlines and issues' }).props.value, 'licenses_expiring_30')
})

test('company creation presents blank/copy requirements choice and safely renders validation errors', async t => {
  const { renderer, calls } = await setup(t, { request: async config => {
    if (config.method === 'post') throw { response: { status: 422, data: { detail: [{ loc: ['body', 'legal_name'], msg: 'Name already exists' }] } } }
    return null
  } })
  await act(async () => button(renderer, 'Manage Companies').props.onClick())
  await act(async () => button(renderer, 'Add Company').props.onClick())
  assert.match(text(renderer), /never credentials/)
  const form = renderer.root.findByType('form')
  const copy = form.findByType('select')
  assert.equal(copy.props.value, '')
  await act(async () => copy.props.onChange({ target: { value: '2' } }))
  await act(async () => { form.props.onSubmit({ preventDefault() {} }); await tick() })
  await act(tick)
  assert.equal(calls.find(call => call.method === 'post').data.copy_from_company_id, 2)
  assert.match(text(renderer), /legal_name: Name already exists/)
})

test('managed company overview counts open its filtered matrix and logo chooser matches server formats', async t => {
  const { renderer } = await setup(t)
  await act(async () => button(renderer, 'Manage Companies').props.onClick())
  await act(async () => { button(renderer, 'Company Beta').props.onClick(); await tick() })
  await act(tick)
  assert.equal(renderer.root.findByProps({ type: 'file' }).props.accept, 'image/png,image/jpeg')
  const count = renderer.root.findByProps({ 'aria-label': 'Company Beta: Reports due · 90 days' })
  await act(async () => { count.props.onClick(); await tick() })
  await act(tick)
  assert.equal(renderer.root.findAllByProps({ role: 'dialog' }).length, 0)
  assert.equal(renderer.root.findByProps({ 'aria-label': 'Compliance company' }).props.value, '2')
  assert.equal(renderer.root.findByProps({ 'aria-label': 'Filter deadlines and issues' }).props.value, 'annual_reports_due_soon')
})


test('same-company All Jurisdictions summary resets prior matrix filters', async t => {
  const { renderer } = await setup(t)
  await act(async () => renderer.root.findByProps({ 'aria-label': 'Filter compliance status' }).props.onChange({ target: { value: 'active' } }))
  await act(async () => button(renderer, 'Manage Companies').props.onClick())
  await act(async () => { button(renderer, 'Company Alpha').props.onClick(); await tick() })
  await act(tick)
  await act(async () => renderer.root.findByProps({ 'aria-label': 'Company Alpha: All Jurisdictions' }).props.onClick())
  assert.equal(renderer.root.findByProps({ 'aria-label': 'Filter compliance status' }).props.value, 'all')
})

test('state edits invalidate the independent company-profile summary cache', async t => {
  const { renderer, client } = await setup(t, { request: async config => config.method === 'put' ? { data: {} } : null })
  client.setQueryData(['compliance-company', 1], companies[0])
  await openState(renderer)
  await act(async () => { renderer.root.findByType('form').props.onSubmit({ preventDefault() {} }); await tick() })
  await act(tick)
  assert.equal(client.getQueryState(['compliance-company', 1]).isInvalidated, true)
})


test('mounted logo refetches when a replacement changes its content revision', async t => {
  let profile = { ...companies[0], logo_path: '/api/compliance/companies/1/logo?v=first' }
  const { renderer, client, calls } = await setup(t, { request: async (config, url) => {
    if (url.pathname === '/api/compliance/companies') return { data: { companies: [profile], can_manage: true, is_super_admin: true } }
    if (url.pathname.endsWith('/logo')) return { data: new Blob([profile.logo_path], { type: 'image/png' }) }
    return null
  } })
  await act(tick)
  const oldSource = renderer.root.findByProps({ alt: 'Company Alpha logo' }).props.src
  profile = { ...profile, logo_path: '/api/compliance/companies/1/logo?v=replaced' }
  await act(async () => { await client.invalidateQueries({ queryKey: ['compliance-companies'] }); await tick() })
  await act(tick)
  assert.notEqual(renderer.root.findByProps({ alt: 'Company Alpha logo' }).props.src, oldSource)
  assert.equal(calls.filter(call => call.url.pathname.endsWith('/logo')).length, 2)
})
