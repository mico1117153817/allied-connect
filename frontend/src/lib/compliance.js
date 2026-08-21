export const COMPLIANCE_ATTACHMENT_TYPES = [
  { value: 'license', label: 'Licenses' },
  { value: 'certificate_of_authority', label: 'Certificate of Authority' },
  { value: 'bond', label: 'Bonds' },
]

export const COMPLIANCE_REQUIREMENTS = ['Required', 'Not Required']
export const COMPLIANCE_STATUSES = ['Active', 'Pending', 'Not Held']

const EDITABLE_FIELDS = [
  'jurisdiction', 'collection_license_requirement', 'license_status', 'license_number',
  'license_issue_date', 'license_expiration', 'license_renewal_due', 'coa_requirement',
  'coa_status', 'coa_number', 'coa_issue_date', 'certificate_of_authority',
  'bond_requirement', 'bond_status', 'bond_number', 'bond_amount', 'bond_expiration',
  'regulator', 'state_portal_url', 'portal_username', 'portal_password', 'clear_portal_password', 'notes', 'source_urls', 'document_paths', 'data_confidence',
]

export function complianceSummary(rows = []) {
  const summary = { total: rows.length, active: 0, needsReview: 0, notAuthorized: 0 }
  for (const row of rows) {
    if (row.overall_status === 'Active') summary.active += 1
    else if (row.overall_status === 'Not Authorized') summary.notAuthorized += 1
    else summary.needsReview += 1
  }
  return summary
}

export function filterComplianceRows(rows = [], status = 'all', search = '') {
  const normalizedSearch = search.trim().toLowerCase()
  return rows.filter(row => {
    const normalizedStatus = row.overall_status === 'Unknown' ? 'needs review' : row.overall_status?.toLowerCase()
    const statusMatches = status === 'all' || normalizedStatus === status.toLowerCase()
    const haystack = [row.state, row.jurisdiction, row.state_portal_url, row.regulator, row.license_number, row.coa_number, row.bond_number]
      .filter(Boolean).join(' ').toLowerCase()
    return statusMatches && (!normalizedSearch || haystack.includes(normalizedSearch))
  })
}

export function complianceIndicator(row) {
  if (row.overall_status === 'Active') return { symbol: '✓', label: 'In Compliance', tone: 'green' }
  if (row.overall_status === 'Not Authorized') return { symbol: '✕', label: 'Not In Compliance', tone: 'red' }
  if (row.overall_status === 'Unknown' || row.overall_status === 'Needs Review') return { symbol: '!', label: 'Needs Review', tone: 'yellow' }
  return { symbol: '!', label: 'Needs Review', tone: 'yellow' }
}

export function normalizeComplianceEditor(row) {
  const normalized = { ...row }
  for (const field of ['collection_license_requirement', 'coa_requirement', 'bond_requirement']) {
    if (!COMPLIANCE_REQUIREMENTS.includes(normalized[field])) normalized[field] = ''
  }
  for (const field of ['license_status', 'coa_status', 'bond_status']) {
    if (!COMPLIANCE_STATUSES.includes(normalized[field])) normalized[field] = ''
  }
  return normalized
}

export function compliancePayload(row) {
  const payload = {}
  for (const field of EDITABLE_FIELDS) payload[field] = row[field] ?? null
  payload.bond_amount = row.bond_amount === '' || row.bond_amount == null ? null : Number(row.bond_amount)
  if (row.collection_license_requirement === 'Not Required') {
    payload.license_status = 'Not Held'
    payload.license_number = null
    payload.license_issue_date = null
    payload.license_expiration = null
    payload.license_renewal_due = null
  }
  if (row.coa_requirement === 'Not Required') {
    payload.coa_status = 'Not Held'
    payload.coa_number = null
    payload.coa_issue_date = null
  }
  if (row.bond_requirement === 'Not Required') {
    payload.bond_status = 'Not Held'
    payload.bond_number = null
    payload.bond_amount = null
    payload.bond_expiration = null
  }
  payload.certificate_of_authority = row.coa_requirement === 'Required' && row.coa_status === 'Active'
  payload.state_portal_url = row.state_portal_url || null
  payload.source_urls = (row.source_urls || []).map(value => value.trim()).filter(Boolean)
  payload.document_paths = (row.document_paths || []).map(value => value.trim()).filter(Boolean)
  return payload
}
