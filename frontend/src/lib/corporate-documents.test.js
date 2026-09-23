import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const profile = readFileSync(new URL('../pages/ComplianceCompanies.jsx', import.meta.url), 'utf8')
test('saved profiles mount corporate documents outside the company form', () => {
  assert.match(profile, /import CorporateDocuments/)
  assert.match(profile, /<CompanyForm[^\n]+\/>\s*<CorporateDocuments/)
  const form = profile.slice(profile.indexOf('function CompanyForm'))
  assert.doesNotMatch(form, /<CorporateDocuments/)
})
