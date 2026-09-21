import test from 'node:test'
import assert from 'node:assert/strict'
import * as compliance from './compliance.js'

test('annual report filters follow the server renewal-date precedence and include reports in expiring soon', () => {
  const rows = [
    { annual_report_requirement: 'Annual', annual_report_due_date: '2026-01-01', annual_report_renewal_date: '2026-10-01', annual_report_completed_at: '2026-01-01' },
    { annual_report_requirement: 'Bi-Annual', annual_report_due_date: '2026-10-01', annual_report_renewal_date: '2027-10-01' },
  ]
  assert.deepEqual(compliance.filterComplianceMetric(rows, 'annual_reports_due_soon', '2026-09-20'), [rows[0]])
  assert.deepEqual(compliance.filterComplianceMetric(rows, 'expiring_soon', '2026-09-20'), [rows[0]])
})

test('scoped clients capture company identity for every action and fail closed for read-only companies', async () => {
  const calls = []
  const api = Object.fromEntries(['get', 'put', 'post', 'delete'].map(method => [method, async (...args) => { calls.push([method, ...args]); return { data: {} } }]))
  let selected = 1
  const first = compliance.createComplianceClient(api, selected, true)
  selected = 2
  const second = compliance.createComplianceClient(api, selected, false)
  await first.post('/api/compliance/Colorado/attachments', 'file')
  await first.put('/api/compliance/Colorado', { notes: 'A' })
  await first.delete('/api/compliance/Colorado/attachments/3')
  await second.get('/api/compliance/Colorado/portal-credentials')
  assert.ok(calls.slice(0, 3).every(call => call[1].endsWith('company_id=1')))
  assert.ok(calls[3][1].endsWith('company_id=2'))
  await assert.rejects(second.post('/api/compliance/Colorado/annual-report/complete'), /read.only/i)
  assert.equal(calls.length, 4)
})

test('state payload retains copy-safe requirement fields without mixing issued bond amount', () => {
  const payload = compliance.compliancePayload({ bond_requirement: 'Not Required', bond_amount: '9', bond_requirement_amount: '25000', renewal_structure: 'Annual', general_requirement_notes: 'Confirm with regulator' })
  assert.equal(payload.bond_requirement_amount, 25000)
  assert.equal(payload.bond_amount, null)
  assert.equal(payload.renewal_structure, 'Annual')
  assert.equal(payload.general_requirement_notes, 'Confirm with regulator')
  assert.equal(compliance.compliancePayload({ bond_requirement_amount: '' }).bond_requirement_amount, null)
})

test('company payload allows company fields only and explicitly chooses blank or requirement-only copy', () => {
  const source = { legal_name: ' New Company ', formation_date: '', id: 2, logo_path: '/old', summary: {}, portal_password: 'never copy', is_active: true }
  const blank = compliance.complianceCompanyPayload(source, null)
  assert.equal(blank.legal_name, 'New Company')
  assert.equal(blank.formation_date, null)
  assert.equal(blank.copy_from_company_id, null)
  assert.equal(blank.portal_password, undefined)
  assert.equal(blank.id, undefined)
  assert.equal(blank.logo_path, undefined)
  assert.equal(compliance.complianceCompanyPayload(source, '8').copy_from_company_id, 8)
  assert.equal(compliance.complianceCompanyPayload(source).copy_from_company_id, undefined)
})

test('API errors are safe text for validation arrays, objects and network failures', () => {
  assert.equal(compliance.complianceError({ response: { data: { detail: [{ loc: ['body', 'legal_name'], msg: 'Required' }] } } }), 'legal_name: Required')
  assert.equal(compliance.complianceError({ response: { data: { detail: 'Forbidden' } } }), 'Forbidden')
  assert.equal(typeof compliance.complianceError({ response: { data: { detail: { unexpected: true } } } }), 'string')
  assert.equal(compliance.complianceError(new Error('Network Error')), 'Network Error')
})

test('deadline filters include today and day 30/60/90, exclude past and ignore non-required items', () => {
  const rows = ['2026-09-19', '2026-09-20', '2026-10-20', '2026-11-19', '2026-12-19', '2026-12-20', null].map(license_expiration => ({ collection_license_requirement: 'Required', license_expiration }))
  rows.push({ collection_license_requirement: 'Not Required', license_expiration: '2026-09-20' })
  assert.equal(compliance.filterComplianceMetric(rows, 'licenses_expiring_30', '2026-09-20').length, 2)
  assert.equal(compliance.filterComplianceMetric(rows, 'licenses_expiring_60', '2026-09-20').length, 3)
  assert.equal(compliance.filterComplianceMetric(rows, 'licenses_expiring_90', '2026-09-20').length, 4)
  assert.equal(compliance.filterComplianceMetric([{ bond_requirement: 'Required', bond_expiration: '2026-12-19' }], 'bonds_expiring_soon', '2026-09-20').length, 1)
  assert.equal(compliance.filterComplianceMetric([{ annual_report_requirement: 'Annual', annual_report_due_date: '2026-09-20' }, { annual_report_requirement: 'Not Required', annual_report_due_date: '2026-09-20' }], 'annual_reports_due_soon', '2026-09-20').length, 1)
  assert.equal(compliance.filterComplianceMetric([{ issues: ['A', 'B'] }, { issues: [] }], 'open_issues').length, 1)
  assert.equal(compliance.filterComplianceMetric(rows, 'all').length, rows.length)
})

test('company request scope replaces stale IDs and preserves other query parameters', () => {
  assert.equal(compliance.companyComplianceUrl('/api/compliance', 7), '/api/compliance?company_id=7')
  assert.equal(compliance.companyComplianceUrl('/api/compliance/Colorado/attachments/2/view?company_id=3&history=true', 7), '/api/compliance/Colorado/attachments/2/view?company_id=7&history=true')
  assert.throws(() => compliance.companyComplianceUrl('/api/compliance', null), /company/i)
})
