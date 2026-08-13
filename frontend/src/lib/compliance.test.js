import test from 'node:test'
import assert from 'node:assert/strict'

import { complianceSummary, filterComplianceRows, compliancePayload } from './compliance.js'

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
