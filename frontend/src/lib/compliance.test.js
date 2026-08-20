import test from 'node:test'
import assert from 'node:assert/strict'

import { complianceSummary, filterComplianceRows, compliancePayload, complianceIndicator, COMPLIANCE_REQUIREMENTS, COMPLIANCE_STATUSES, normalizeComplianceEditor } from './compliance.js'

const rows = [
  { state: 'Alabama', overall_status: 'Active', data_confidence: 'Verified', regulator: 'Secretary of State' },
  { state: 'New York', overall_status: 'Not Authorized', data_confidence: 'High', regulator: 'DCWP' },
  { state: 'Wyoming', overall_status: 'Needs Review', data_confidence: 'Low', regulator: null },
  { state: 'Texas', overall_status: 'Unknown', data_confidence: 'Unverified', regulator: null },
]

test('complianceSummary counts each decision state', () => {
  assert.deepEqual(complianceSummary(rows), { total: 4, active: 1, needsReview: 1, notAuthorized: 1, unknown: 1 })
})

test('filterComplianceRows applies status and case-insensitive search', () => {
  assert.deepEqual(filterComplianceRows(rows, 'not authorized', 'new').map(row => row.state), ['New York'])
  assert.deepEqual(filterComplianceRows(rows, 'all', 'dcwp').map(row => row.state), ['New York'])
})

test('summary-card status filters select the correct category', () => {
  assert.deepEqual(filterComplianceRows(rows, 'active', '').map(row => row.state), ['Alabama'])
  assert.deepEqual(filterComplianceRows(rows, 'needs review', '').map(row => row.state), ['Wyoming'])
  assert.deepEqual(filterComplianceRows(rows, 'not authorized', '').map(row => row.state), ['New York'])
  assert.deepEqual(filterComplianceRows(rows, 'unknown', '').map(row => row.state), ['Texas'])
  assert.deepEqual(filterComplianceRows(rows, 'all', '').map(row => row.state), ['Alabama', 'New York', 'Wyoming', 'Texas'])
})

test('complianceIndicator returns explicit state compliance labels', () => {
  assert.deepEqual(complianceIndicator({ overall_status: 'Active' }), { symbol: '✓', label: 'In Compliance', tone: 'green' })
  assert.deepEqual(complianceIndicator({ overall_status: 'Not Authorized' }), { symbol: '✕', label: 'Not In Compliance', tone: 'red' })
  assert.deepEqual(complianceIndicator({ overall_status: 'Needs Review' }), { symbol: '!', label: 'Needs Review', tone: 'yellow' })
  assert.deepEqual(complianceIndicator({ overall_status: 'Unknown' }), { symbol: '?', label: 'Unknown', tone: 'gray' })
})

test('compliance editor choices are restricted to binary requirements and current statuses', () => {
  assert.deepEqual(COMPLIANCE_REQUIREMENTS, ['Required', 'Not Required'])
  assert.deepEqual(COMPLIANCE_STATUSES, ['Active', 'Pending', 'Not Held'])
})

test('legacy values require an explicit supported selection before save', () => {
  const normalized = normalizeComplianceEditor({
    collection_license_requirement: 'Conditional', coa_requirement: 'Unknown', bond_requirement: 'Local Only',
    license_status: 'Perpetual', coa_status: 'Revoked', bond_status: 'Unknown',
  })
  assert.equal(normalized.collection_license_requirement, '')
  assert.equal(normalized.coa_requirement, '')
  assert.equal(normalized.bond_requirement, '')
  assert.equal(normalized.license_status, '')
  assert.equal(normalized.coa_status, '')
  assert.equal(normalized.bond_status, '')
})

test('compliancePayload strips computed audit fields and normalizes editable values', () => {
  const payload = compliancePayload({
    ...rows[0],
    overall_status: 'Active', indicator: 'green', updated_by: 'ADMIN', updated_at: '2026-08-13',
    bond_amount: '', source_urls: [' https://example.gov ', ''], document_paths: [' License.pdf ', ''],
  })
  assert.equal(payload.overall_status, undefined)
  assert.equal(payload.updated_by, undefined)
  assert.equal(payload.bond_amount, null)
  assert.deepEqual(payload.source_urls, ['https://example.gov'])
  assert.deepEqual(payload.document_paths, ['License.pdf'])
})
