// Each client closes over one company. An in-flight action never follows the selector.
export function createComplianceClient(api, companyId, canEdit = false) {
  return Object.fromEntries(['get', 'post', 'put', 'delete'].map(method => [method, async (path, ...args) => {
    if (method !== 'get' && !canEdit) throw new Error('This company is read-only.')
    return api[method](companyComplianceUrl(path, companyId), ...args)
  }]))
}

export const COMPLIANCE_COMPANY_FIELDS = [
  ['legal_name', 'Legal name'], ['dba_name', 'DBA name'], ['entity_type', 'Entity type'],
  ['ein', 'EIN'], ['formation_state', 'Formation state'], ['formation_date', 'Formation date', 'date'],
  ['business_address', 'Business address', 'textarea'], ['mailing_address', 'Mailing address', 'textarea'],
  ['phone', 'Phone', 'tel'], ['email', 'Email', 'email'], ['website', 'Website', 'url'],
  ['registered_agent', 'Registered agent'], ['registered_agent_address', 'Registered agent address', 'textarea'],
  ['notes', 'Notes', 'textarea'],
]

export function complianceCompanyPayload(company, copyFrom) {
  const payload = Object.fromEntries(COMPLIANCE_COMPANY_FIELDS.map(([field]) => [field, typeof company[field] === 'string' ? company[field].trim() || null : company[field] ?? null]))
  payload.is_active = company.is_active !== false
  if (copyFrom !== undefined) payload.copy_from_company_id = copyFrom ? Number(copyFrom) : null
  return payload
}

export function complianceError(error) {
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map(item => {
    if (typeof item === 'string') return item
    const field = Array.isArray(item?.loc) ? item.loc.filter(part => part !== 'body').join('.') : ''
    return `${field ? `${field}: ` : ''}${typeof item?.msg === 'string' ? item.msg : 'Invalid value'}`
  }).join('; ')
  return typeof error?.message === 'string' ? error.message : 'Unable to complete request. Please try again.'
}

export function companyComplianceUrl(path, companyId) {
  if (companyId == null || companyId === '') throw new Error('Select a company before continuing.')
  const [pathname, query = ''] = path.split('?')
  const params = new URLSearchParams(query)
  params.set('company_id', String(companyId))
  return `${pathname}?${params}`
}

export function filterComplianceMetric(rows = [], metric = 'all', today) {
  const now = new Date()
  const start = today || `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
  const within = (value, days) => {
    if (!value) return false
    const diff = (Date.parse(`${value}T00:00:00Z`) - Date.parse(`${start}T00:00:00Z`)) / 86400000
    return Number.isFinite(diff) && diff >= 0 && diff <= days
  }
  const license = (row, days) => row.collection_license_requirement === 'Required' && within(row.license_expiration, days)
  const bond = row => row.bond_requirement === 'Required' && within(row.bond_expiration, 90)
  const annual = row => row.annual_report_requirement !== 'Not Required' && within(row.annual_report_renewal_date || row.annual_report_due_date, 90)
  return rows.filter(row => {
    if (metric === 'open_issues') return (row.issues || []).length > 0
    if (metric === 'bonds_expiring_soon') return bond(row)
    if (metric === 'annual_reports_due_soon') return annual(row)
    if (metric === 'expiring_soon') return license(row, 90) || bond(row) || annual(row)
    const days = { licenses_expiring_30: 30, licenses_expiring_60: 60, licenses_expiring_90: 90 }[metric]
    return days ? license(row, days) : true
  })
}

export const COMPLIANCE_REGISTER_TYPES = [
  { value: 'license', label: 'Licenses' },
  { value: 'certificate_of_authority', label: 'Certificate of Authority' },
  { value: 'bond', label: 'Bonds' },
]

export const COMPLIANCE_ATTACHMENT_TYPES = [
  ...COMPLIANCE_REGISTER_TYPES,
  { value: 'annual_report', label: 'Annual Reports' },
  { value: 'filing_receipt', label: 'Filing Receipts' },
]

export const COMPLIANCE_REQUIREMENTS = ['Required', 'Not Required']
export const COMPLIANCE_STATUSES = ['Active', 'Pending', 'Not Held']
export const ANNUAL_REPORT_REQUIREMENTS = ['Not Required', 'Annual', 'Bi-Annual']

const EDITABLE_FIELDS = [
  'bond_requirement_amount', 'renewal_structure', 'general_requirement_notes',
  'jurisdiction', 'collection_license_requirement', 'license_status', 'license_number',
  'license_issue_date', 'license_expiration', 'license_renewal_due', 'coa_requirement',
  'coa_status', 'coa_number', 'coa_issue_date', 'certificate_of_authority',
  'bond_requirement', 'bond_status', 'bond_number', 'bond_amount', 'bond_expiration',
  'annual_report_requirement', 'annual_report_due_date', 'annual_report_renewal_date',
  'regulator', 'state_portal_url', 'portal_username', 'portal_password', 'clear_portal_password', 'notes', 'source_urls', 'document_paths',
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

export function complianceDocumentView(rows = [], selectedType = 'all') {
  const requirementField = {
    license: 'collection_license_requirement',
    certificate_of_authority: 'coa_requirement',
    bond: 'bond_requirement',
  }[selectedType]
  const visibleRows = requirementField
    ? rows.filter(row => row[requirementField] === 'Required')
    : rows
  const uploadType = COMPLIANCE_REGISTER_TYPES.some(option => option.value === selectedType) ? selectedType : 'license'
  return {
    rows: visibleRows,
    showLicense: selectedType === 'all' || selectedType === 'license',
    showCoa: selectedType === 'all' || selectedType === 'certificate_of_authority',
    showBond: selectedType === 'all' || selectedType === 'bond',
    showAnnualReport: selectedType === 'all',
    showFilingReceipt: selectedType === 'all',
    uploadType,
  }
}

export function complianceRequirementDisplay(requirement, primary, secondary) {
  if (requirement === 'Not Required') {
    return { primary: 'Not Required', secondary: null, showAttachments: false }
  }
  if (primary === 'Not Held') {
    return { primary: 'Not Held', secondary: null, showAttachments: true }
  }
  return { primary, secondary, showAttachments: true }
}

export function complianceLicenseDetails(status, number, expiration) {
  if (status === 'Not Held') return null
  return `${number || 'No number'}${expiration ? ` · exp ${expiration}` : ''}`
}

export function complianceAttachmentLabel(attachments = []) {
  if (!attachments?.length) return 'NA'
  return `${attachments.length} PDF${attachments.length === 1 ? '' : 's'}`
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
  payload.bond_requirement_amount = row.bond_requirement_amount === '' || row.bond_requirement_amount == null ? null : Number(row.bond_requirement_amount)
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
  if (row.annual_report_requirement === 'Not Required') {
    payload.annual_report_due_date = null
    payload.annual_report_renewal_date = null
  }
  payload.certificate_of_authority = row.coa_requirement === 'Required' && row.coa_status === 'Active'
  payload.state_portal_url = row.state_portal_url || null
  payload.source_urls = (row.source_urls || []).map(value => value.trim()).filter(Boolean)
  payload.document_paths = (row.document_paths || []).map(value => value.trim()).filter(Boolean)
  return payload
}
