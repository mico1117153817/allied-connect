import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { buildSync } from 'esbuild'
import { fileURLToPath, pathToFileURL } from 'node:url'

const root = fileURLToPath(new URL('../../', import.meta.url))
const out = fileURLToPath(new URL('../../node_modules/.cache/vault-contract.mjs', import.meta.url))
buildSync({ entryPoints: [`${root}/src/pages/PasswordVault.jsx`], bundle: true, platform: 'node', format: 'esm', packages: 'external', loader: { '.jsx': 'jsx' }, define: { 'import.meta.env.VITE_API_URL': '""' }, outfile: out })
const vault = await import(`${pathToFileURL(out).href}?${Date.now()}`)
const source = readFileSync(`${root}/src/pages/PasswordVault.jsx`, 'utf8')

test('vault groups and filters masked records by company', () => {
  const companies = [{ id: 1, legal_name: 'Alpha' }, { id: 2, legal_name: 'Beta' }]
  const entries = [{ id: 1, company_id: 2, name: 'Bank', password_masked: '••••••••' }, { id: 2, company_id: 1, name: 'Email', password_masked: '••••••••' }]
  assert.deepEqual(Object.keys(vault.groupVaultEntries(entries, companies, '')), ['Alpha', 'Beta'])
  assert.deepEqual(vault.filterVaultEntries(entries, '2', 'bank'), [entries[0]])
})

test('vault contract keeps secrets ephemeral and requires explicit copy', () => {
  assert.doesNotMatch(source, /localStorage|sessionStorage|console\./)
  assert.ok(source.includes('navigator.clipboard.writeText'))
  assert.ok(source.includes('Copy password'))
  assert.ok(source.includes('Lock Now'))
  assert.ok(source.includes('15'))
})

test('activity list covers interaction events used to reset auto-lock', () => {
  assert.ok(vault.VAULT_ACTIVITY_EVENTS.includes('keydown'))
  assert.ok(vault.VAULT_ACTIVITY_EVENTS.includes('pointerdown'))
})
