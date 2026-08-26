import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

import { complianceSummary, filterComplianceRows, compliancePayload, complianceIndicator, complianceDocumentView, complianceRequirementDisplay, complianceAttachmentLabel, ANNUAL_REPORT_REQUIREMENTS, COMPLIANCE_ATTACHMENT_TYPES, COMPLIANCE_REGISTER_TYPES, COMPLIANCE_REQUIREMENTS, COMPLIANCE_STATUSES, normalizeComplianceEditor } from './compliance.js'

const rows = [
  { state: 'Alabama', overall_status: 'Active', regulator: 'Secretary of State' },
  { state: 'New York', overall_status: 'Not Authorized', regulator: 'DCWP' },
  { state: 'Wyoming', overall_status: 'Needs Review', regulator: null },
  { state: 'Texas', overall_status: 'Unknown', regulator: null },
]

test('complianceSummary counts each decision state', () => {
  assert.deepEqual(complianceSummary(rows), { total: 4, active: 1, needsReview: 2, notAuthorized: 1 })
})

test('filterComplianceRows applies status and case-insensitive search', () => {
  assert.deepEqual(filterComplianceRows(rows, 'not authorized', 'new').map(row => row.state), ['New York'])
  assert.deepEqual(filterComplianceRows(rows, 'all', 'dcwp').map(row => row.state), ['New York'])
})

test('summary-card status filters select the correct category', () => {
  assert.deepEqual(filterComplianceRows(rows, 'active', '').map(row => row.state), ['Alabama'])
  assert.deepEqual(filterComplianceRows(rows, 'needs review', '').map(row => row.state), ['Wyoming', 'Texas'])
  assert.deepEqual(filterComplianceRows(rows, 'not authorized', '').map(row => row.state), ['New York'])
  assert.deepEqual(filterComplianceRows(rows, 'unknown', '').map(row => row.state), [])
  assert.deepEqual(filterComplianceRows(rows, 'all', '').map(row => row.state), ['Alabama', 'New York', 'Wyoming', 'Texas'])
})

test('summary and filters exclude Unknown as a separate category', () => {
  assert.deepEqual(complianceSummary(rows), { total: 4, active: 1, needsReview: 2, notAuthorized: 1 })
  assert.deepEqual(filterComplianceRows(rows, 'needs review', '').map(row => row.state), ['Wyoming', 'Texas'])
})

test('complianceIndicator returns explicit state compliance labels', () => {
  assert.deepEqual(complianceIndicator({ overall_status: 'Active' }), { symbol: '✓', label: 'In Compliance', tone: 'green' })
  assert.deepEqual(complianceIndicator({ overall_status: 'Not Authorized' }), { symbol: '✕', label: 'Not In Compliance', tone: 'red' })
  assert.deepEqual(complianceIndicator({ overall_status: 'Needs Review' }), { symbol: '!', label: 'Needs Review', tone: 'yellow' })
  assert.deepEqual(complianceIndicator({ overall_status: 'Unknown' }), { symbol: '!', label: 'Needs Review', tone: 'yellow' })
})

test('compliance editor choices are restricted to binary requirements and current statuses', () => {
  assert.deepEqual(COMPLIANCE_REQUIREMENTS, ['Required', 'Not Required'])
  assert.deepEqual(COMPLIANCE_STATUSES, ['Active', 'Pending', 'Not Held'])
})

test('annual report scheduling supports only the requested filing frequencies', () => {
  assert.deepEqual(ANNUAL_REPORT_REQUIREMENTS, ['Not Required', 'Annual', 'Bi-Annual'])
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

test('compliance type selection shows only states where the selected item is required', () => {
  const requirementRows = [
    { state: 'Alabama', collection_license_requirement: 'Required', coa_requirement: 'Not Required', bond_requirement: 'Not Required', attachments: {} },
    { state: 'New York', collection_license_requirement: 'Not Required', coa_requirement: 'Required', bond_requirement: 'Not Required', attachments: {} },
    { state: 'Wyoming', collection_license_requirement: 'Required', coa_requirement: 'Required', bond_requirement: 'Required', attachments: {} },
    { state: 'Texas', collection_license_requirement: 'Not Required', coa_requirement: 'Not Required', bond_requirement: 'Not Required', attachments: {} },
  ]

  assert.deepEqual(complianceDocumentView(requirementRows, 'license'), {
    rows: [requirementRows[0], requirementRows[2]],
    showLicense: true,
    showCoa: false,
    showBond: false,
    showAnnualReport: false,
    showFilingReceipt: false,
    uploadType: 'license',
  })
  assert.deepEqual(complianceDocumentView(requirementRows, 'certificate_of_authority'), {
    rows: [requirementRows[1], requirementRows[2]],
    showLicense: false,
    showCoa: true,
    showBond: false,
    showAnnualReport: false,
    showFilingReceipt: false,
    uploadType: 'certificate_of_authority',
  })
  assert.deepEqual(complianceDocumentView(requirementRows, 'bond'), {
    rows: [requirementRows[2]],
    showLicense: false,
    showCoa: false,
    showBond: true,
    showAnnualReport: false,
    showFilingReceipt: false,
    uploadType: 'bond',
  })
  assert.deepEqual(complianceDocumentView(requirementRows, 'all'), {
    rows: requirementRows,
    showLicense: true,
    showCoa: true,
    showBond: true,
    showAnnualReport: true,
    showFilingReceipt: true,
    uploadType: 'license',
  })
  assert.deepEqual(COMPLIANCE_REGISTER_TYPES, [
    { value: 'license', label: 'Licenses' },
    { value: 'certificate_of_authority', label: 'Certificate of Authority' },
    { value: 'bond', label: 'Bonds' },
  ])
  assert.ok(COMPLIANCE_ATTACHMENT_TYPES.some(option => option.value === 'annual_report' && option.label === 'Annual Reports'))
  assert.ok(COMPLIANCE_ATTACHMENT_TYPES.some(option => option.value === 'filing_receipt' && option.label === 'Filing Receipts'))
})

test('not-required compliance cells show only Not Required', () => {
  assert.deepEqual(complianceRequirementDisplay('Not Required', 'Not Held', 'No license details required'), {
    primary: 'Not Required',
    secondary: null,
    showAttachments: false,
  })
  assert.deepEqual(complianceRequirementDisplay('Required', 'Active', 'LIC-123'), {
    primary: 'Active',
    secondary: 'LIC-123',
    showAttachments: true,
  })
  assert.deepEqual(complianceRequirementDisplay('Required', 'Not Held', 'No number'), {
    primary: 'Not Held',
    secondary: null,
    showAttachments: true,
  })
})

test('Compliance UI does not expose confidence', () => {
  const source = readFileSync(new URL('../pages/Compliance.jsx', import.meta.url), 'utf8')
  assert.doesNotMatch(source, /Confidence|data_confidence/)
})

test('empty annual report and filing receipt cells display NA', () => {
  assert.equal(complianceAttachmentLabel([], 'annual report'), 'NA')
  assert.equal(complianceAttachmentLabel(null, 'annual report'), 'NA')
  assert.equal(complianceAttachmentLabel([], 'filing receipt'), 'NA')
  assert.equal(complianceAttachmentLabel([{}], 'annual report'), '1 PDF')
  assert.equal(complianceAttachmentLabel([{}, {}], 'filing receipt'), '2 PDFs')
})

test('compliancePayload strips computed audit fields and normalizes editable values', () => {
  const payload = compliancePayload({
    ...rows[0],
    overall_status: 'Active', indicator: 'green', updated_by: 'ADMIN', updated_at: '2026-08-13',
    data_confidence: 'High',
    bond_amount: '', annual_report_requirement: 'Not Required', annual_report_renewal_date: '2027-01-01', source_urls: [' https://example.gov ', ''], document_paths: [' License.pdf ', ''],
  })
  assert.equal(payload.overall_status, undefined)
  assert.equal(payload.updated_by, undefined)
  assert.equal(payload.data_confidence, undefined)
  assert.equal(payload.bond_amount, null)
  assert.deepEqual(payload.source_urls, ['https://example.gov'])
  assert.deepEqual(payload.document_paths, ['License.pdf'])
  assert.equal(payload.annual_report_requirement, 'Not Required')
  assert.equal(payload.annual_report_renewal_date, null)
})
