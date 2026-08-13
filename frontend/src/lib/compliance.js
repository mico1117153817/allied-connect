const EDITABLE_FIELDS = [
  'jurisdiction', 'collection_license_requirement', 'license_status', 'license_number',
  'license_issue_date', 'license_expiration', 'license_renewal_due', 'coa_requirement',
  'coa_status', 'coa_number', 'coa_issue_date', 'certificate_of_authority',
  'bond_requirement', 'bond_status', 'bond_number', 'bond_amount', 'bond_expiration',
  'regulator', 'notes', 'source_urls', 'document_paths', 'data_confidence',
]

export function complianceSummary(rows = []) {
  const summary = { total: rows.length, active: 0, needsReview: 0, notAuthorized: 0, unknown: 0 }
  for (const row of rows) {
    if (row.overall_status === 'Active') summary.active += 1
    else if (row.overall_status === 'Needs Review') summary.needsReview += 1
    else if (row.overall_status === 'Not Authorized') summary.notAuthorized += 1
    else summary.unknown += 1
  }
  return summary
}

export function filterComplianceRows(rows = [], status = 'all', search = '') {
  const normalizedSearch = search.trim().toLowerCase()
  return rows.filter(row => {
    const statusMatches = status === 'all' || row.overall_status?.toLowerCase() === status.toLowerCase()
    const haystack = [row.state, row.jurisdiction, row.regulator, row.license_number, row.coa_number, row.bond_number]
      .filter(Boolean).join(' ').toLowerCase()
    return statusMatches && (!normalizedSearch || haystack.includes(normalizedSearch))
  })
}

export function complianceIndicator(row) {
  if (row.overall_status === 'Active') return { symbol: '✓', label: 'In Compliance', tone: 'green' }
  if (row.overall_status === 'Not Authorized') return { symbol: '✕', label: 'Not In Compliance', tone: 'red' }
  if (row.overall_status === 'Needs Review') return { symbol: '!', label: 'Needs Review', tone: 'yellow' }
  return { symbol: '?', label: 'Unknown', tone: 'gray' }
}

export function compliancePayload(row) {
  const payload = {}
  for (const field of EDITABLE_FIELDS) payload[field] = row[field] ?? null
  payload.bond_amount = row.bond_amount === '' || row.bond_amount == null ? null : Number(row.bond_amount)
  payload.certificate_of_authority = ['Active', 'Perpetual'].includes(row.coa_status)
  payload.source_urls = (row.source_urls || []).map(value => value.trim()).filter(Boolean)
  payload.document_paths = (row.document_paths || []).map(value => value.trim()).filter(Boolean)
  return payload
}
