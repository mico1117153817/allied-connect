import React from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import { logout } from '../lib/auth'
import { ANNUAL_REPORT_REQUIREMENTS, COMPLIANCE_ATTACHMENT_TYPES, COMPLIANCE_REQUIREMENTS, COMPLIANCE_STATUSES, complianceDocumentView, complianceIndicator, compliancePayload, complianceSummary, filterComplianceRows, normalizeComplianceEditor } from '../lib/compliance'

const REQUIREMENTS = COMPLIANCE_REQUIREMENTS
const LICENSE_STATUSES = COMPLIANCE_STATUSES
const COA_STATUSES = COMPLIANCE_STATUSES
const BOND_STATUSES = COMPLIANCE_STATUSES
const CONFIDENCE_LEVELS = ['Verified', 'High', 'Medium', 'Low', 'Unverified']

const inputClass = 'w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500'

export default function Compliance() {
  const qc = useQueryClient()
  const [status, setStatus] = React.useState('all')
  const [search, setSearch] = React.useState('')
  const [selected, setSelected] = React.useState(null)
  const [selectedAttachmentType, setSelectedAttachmentType] = React.useState('all')
  const [selectedUploadType, setSelectedUploadType] = React.useState('license')
  const [selectedEditorTab, setSelectedEditorTab] = React.useState('details')
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['compliance'],
    queryFn: () => api.get('/api/compliance').then(r => r.data),
  })
  const save = useMutation({
    mutationFn: ({ state, payload }) => api.put(`/api/compliance/${encodeURIComponent(state)}`, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['compliance'] })
      setSelected(null)
    },
  })
  React.useEffect(() => {
    const refresh = () => qc.invalidateQueries({ queryKey: ['compliance'] })
    window.addEventListener('compliance-attachments-updated', refresh)
    return () => window.removeEventListener('compliance-attachments-updated', refresh)
  }, [qc])
  const rows = data?.states || []
  const summary = complianceSummary(rows)
  const documentView = complianceDocumentView(filterComplianceRows(rows, status, search), selectedAttachmentType)
  const visibleRows = documentView.rows

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white shadow-sm">
        <div className="max-w-7xl mx-auto px-4 py-4 flex flex-col gap-3 sm:flex-row sm:justify-between sm:items-center">
          <div className="flex items-center gap-3"><img src="/allied-logo.jpg" alt="Allied" className="h-10 w-auto rounded" /><div><h1 className="text-xl font-bold">Compliance Register</h1><p className="text-xs text-gray-500">State licensing, COA, and bond tracking</p></div></div>
          <div className="flex gap-4"><a href="/dashboard" className="text-sm text-blue-600 hover:underline">← Dashboard</a><button onClick={logout} className="text-sm text-red-600 hover:underline">Logout</button></div>
        </div>
      </header>
      <main className="max-w-7xl mx-auto px-4 py-6 space-y-6">
        <section className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <SummaryCard label="All Jurisdictions" value={summary.total} color="blue" active={status === 'all'} onClick={() => setStatus('all')} />
          <SummaryCard label="Active" value={summary.active} color="green" active={status === 'active'} onClick={() => setStatus('active')} />
          <SummaryCard label="Needs Review" value={summary.needsReview} color="yellow" active={status === 'needs review'} onClick={() => setStatus('needs review')} />
          <SummaryCard label="Not Authorized" value={summary.notAuthorized} color="red" active={status === 'not authorized'} onClick={() => setStatus('not authorized')} />
        </section>
        <section className="bg-white rounded-xl shadow-sm p-5">
          <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-4 mb-5">
            <div><h2 className="text-lg font-semibold">50-State Compliance Matrix</h2><p className="text-sm text-gray-500">Compliance admin and super-admin access. Select a state to edit the complete compliance record.</p></div>
            <div className="flex flex-col sm:flex-row gap-2">
              <input aria-label="Search compliance states" value={search} onChange={e => setSearch(e.target.value)} placeholder="Search state, regulator, number..." className={`${inputClass} sm:w-64`} />
              <select aria-label="Show compliance type" value={selectedAttachmentType} onChange={e => setSelectedAttachmentType(e.target.value)} className={inputClass}>
                <option value="all">All compliance types</option>
                {COMPLIANCE_ATTACHMENT_TYPES.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
              <select aria-label="Filter compliance status" value={status} onChange={e => setStatus(e.target.value)} className={inputClass}>
                <option value="all">All statuses</option>
                <option value="active">Active</option>
                <option value="needs review">Needs Review</option>
                <option value="not authorized">Not Authorized</option>
              </select>
              {status !== 'all' && <button type="button" onClick={() => setStatus('all')} className="px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-700 hover:bg-gray-50 whitespace-nowrap">Clear filter</button>}
            </div>
          </div>
          {isLoading && <p className="text-gray-500 py-8 text-center">Loading all 50 states...</p>}
          {isError && <p className="text-red-600 py-8 text-center">Unable to load compliance data: {error?.response?.data?.detail || error.message}</p>}
          {!isLoading && !isError && <div className="overflow-x-auto"><table className="w-full min-w-[850px] text-sm"><thead><tr className="border-b text-left text-gray-500"><th className="p-3">State</th><th className="p-3">Overall</th><th className="p-3">Confidence</th>{documentView.showLicense && <th className="p-3">License</th>}{documentView.showCoa && <th className="p-3">COA</th>}{documentView.showBond && <th className="p-3">Bond</th>}{documentView.showAnnualReport && <th className="p-3">Annual Report</th>}{documentView.showFilingReceipt && <th className="p-3">Filing Receipts</th>}<th className="p-3">State Portal</th><th className="p-3">Issues</th><th className="p-3">Action</th></tr></thead><tbody>{visibleRows.map(row => <ComplianceRow key={row.state} row={row} showLicense={documentView.showLicense} showCoa={documentView.showCoa} showBond={documentView.showBond} showAnnualReport={documentView.showAnnualReport} showFilingReceipt={documentView.showFilingReceipt} uploadType={documentView.uploadType} onEdit={() => { setSelectedUploadType(documentView.uploadType); setSelectedEditorTab('details'); setSelected(row) }} onUpload={type => { setSelectedUploadType(type); setSelectedEditorTab('files'); setSelected(row) }} />)}</tbody></table>{visibleRows.length === 0 && <p className="text-gray-500 text-center py-8">No states match the current status or search filters.</p>}</div>}
        </section>
      </main>
      {selected && <ComplianceEditor row={selected} initialUploadType={selectedUploadType} initialTab={selectedEditorTab} saving={save.isPending} error={save.error} onClose={() => setSelected(null)} onSave={payload => save.mutate({ state: selected.state, payload })} />}
    </div>
  )
}

function SummaryCard({ label, value, color, active, onClick }) {
  const colors = { blue: 'bg-blue-50 text-blue-700', green: 'bg-green-50 text-green-700', yellow: 'bg-yellow-50 text-yellow-700', red: 'bg-red-50 text-red-700', gray: 'bg-gray-100 text-gray-700' }
  return <button type="button" onClick={onClick} aria-pressed={active} aria-label={`Show ${label}: ${value}`} className={`rounded-xl p-4 text-left transition hover:-translate-y-0.5 hover:shadow-md focus:outline-none focus:ring-2 focus:ring-blue-500 ${colors[color]} ${active ? 'ring-2 ring-offset-2 ring-blue-600 shadow-md' : ''}`}><p className="text-xs opacity-75">{label}</p><p className="text-2xl font-bold">{value}</p><p className="text-[11px] mt-1 opacity-70">Click to filter</p></button>
}

function statusClass(indicator) { return ({ green: 'bg-green-100 text-green-800', yellow: 'bg-yellow-100 text-yellow-800', red: 'bg-red-100 text-red-800', gray: 'bg-gray-100 text-gray-700' })[indicator] || 'bg-gray-100 text-gray-700' }
function AttachmentLinks({ attachments = [] }) {
  const openAttachment = async (attachment) => {
    const response = await api.get(attachment.view_url, { responseType: 'blob' })
    const url = URL.createObjectURL(new Blob([response.data], { type: 'application/pdf' }))
    window.open(url, '_blank', 'noopener,noreferrer')
    setTimeout(() => URL.revokeObjectURL(url), 60000)
  }
  if (!attachments.length) return null
  return <div className="mt-1 flex flex-wrap gap-1">{attachments.map(attachment => <button type="button" key={attachment.id} onClick={() => openAttachment(attachment)} className="inline-flex items-center gap-1 text-xs text-blue-600 hover:underline" title={`View ${attachment.label} PDF`}>PDF ↗</button>)}</div>
}

function ComplianceRow({ row, onEdit, onUpload, showLicense, showCoa, showBond, showAnnualReport, showFilingReceipt, uploadType }) {
  const marker = complianceIndicator(row)
  const uploadLabel = COMPLIANCE_ATTACHMENT_TYPES.find(option => option.value === uploadType)?.label || 'License'
  const markerStyles = {
    green: 'bg-green-600 text-white ring-green-200',
    red: 'bg-red-600 text-white ring-red-200',
    yellow: 'bg-yellow-400 text-yellow-950 ring-yellow-200',
    gray: 'bg-gray-500 text-white ring-gray-200',
  }
  return <tr className="border-b hover:bg-blue-50"><td className="p-0"><button type="button" onClick={onEdit} className="w-full p-3 text-left hover:bg-blue-100 focus:outline-none focus:ring-2 focus:ring-inset focus:ring-blue-500" aria-label={`Edit ${row.state} compliance record`}><div className="flex items-center gap-3"><span title={marker.label} aria-label={`${row.state}: ${marker.label}`} className={`inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-sm font-black ring-4 ${markerStyles[marker.tone]}`}>{marker.symbol}</span><div><div className="font-semibold text-blue-700 hover:underline">{row.state}</div><div className={`text-xs font-medium ${marker.tone === 'green' ? 'text-green-700' : marker.tone === 'red' ? 'text-red-700' : marker.tone === 'yellow' ? 'text-yellow-700' : 'text-gray-600'}`}>{marker.label}</div></div></div></button></td><td className="p-3"><span className={`inline-block px-2 py-1 rounded-full text-xs font-medium ${statusClass(row.indicator)}`}>{row.overall_status === 'Unknown' ? 'Needs Review' : row.overall_status}</span></td><td className="p-3">{row.data_confidence}</td>{showLicense && <td className="p-3"><div>{row.collection_license_requirement === 'Not Required' ? 'Not Required' : row.license_status}</div><div className="text-xs text-gray-500">{row.collection_license_requirement === 'Not Required' ? 'No license details required' : `${row.license_number || 'No number'}${row.license_expiration ? ` · exp ${row.license_expiration}` : ''}`}</div><AttachmentLinks attachments={row.attachments?.license} /></td>}{showCoa && <td className="p-3"><div>{row.coa_requirement}</div><div className="text-xs text-gray-500">{row.coa_requirement === 'Not Required' ? 'No COA details required' : `${row.coa_status}${row.coa_number ? ` · ${row.coa_number}` : ''}`}</div><AttachmentLinks attachments={row.attachments?.certificate_of_authority} /></td>}{showBond && <td className="p-3"><div>{row.bond_requirement}</div><div className="text-xs text-gray-500">{row.bond_requirement === 'Not Required' ? 'No bond details required' : `${row.bond_status}${row.bond_amount != null ? ` · $${Number(row.bond_amount).toLocaleString()}` : ''}`}</div><AttachmentLinks attachments={row.attachments?.bond} /></td>}{showAnnualReport && <td className="p-3"><div>{row.attachments?.annual_report?.length ? `${row.attachments.annual_report.length} PDF${row.attachments.annual_report.length === 1 ? '' : 's'}` : 'No annual report uploaded'}</div><AttachmentLinks attachments={row.attachments?.annual_report} /></td>}{showFilingReceipt && <td className="p-3"><div>{row.attachments?.filing_receipt?.length ? `${row.attachments.filing_receipt.length} PDF${row.attachments.filing_receipt.length === 1 ? '' : 's'}` : 'No filing receipt uploaded'}</div><AttachmentLinks attachments={row.attachments?.filing_receipt} /></td>}{row.state_portal_url ? <td className="p-3"><a href={row.state_portal_url} target="_blank" rel="noreferrer" className="text-blue-600 hover:underline">Open portal ↗</a></td> : <td className="p-3 text-gray-400">—</td>}<td className="p-3 text-xs text-yellow-700">{row.issues?.length ? row.issues.join('; ') : '—'}</td><td className="p-3"><div className="flex flex-col items-start gap-1"><button onClick={onEdit} className="text-blue-600 hover:underline">Edit</button><button type="button" onClick={() => onUpload(uploadType)} className="text-xs text-blue-600 hover:underline">Upload {uploadLabel} PDF</button></div></td></tr>
}

function Field({ label, children }) { return <label className="block"><span className="block text-xs font-medium text-gray-600 mb-1">{label}</span>{children}</label> }
function SelectField({ label, value, options, onChange }) { return <Field label={label}><select required value={value || ''} onChange={e => onChange(e.target.value)} className={inputClass}><option value="" disabled>Select...</option>{options.map(option => <option key={option}>{option}</option>)}</select></Field> }
function ComplianceEditor({ row, onClose, onSave, saving, error, initialUploadType = 'license', initialTab = 'details' }) {
  const [form, setForm] = React.useState({ ...normalizeComplianceEditor(row), portal_password: '', clear_portal_password: false, source_urls_text: (row.source_urls || []).join('\n'), document_paths_text: (row.document_paths || []).join('\n') })
  const [credentialMessage, setCredentialMessage] = React.useState('')
  const [showPassword, setShowPassword] = React.useState(false)
  const [uploadItemType, setUploadItemType] = React.useState(initialUploadType)
  const [uploadFile, setUploadFile] = React.useState(null)
  const [uploadMessage, setUploadMessage] = React.useState('')
  const [activeTab, setActiveTab] = React.useState(initialTab)
  const [attachments, setAttachments] = React.useState(row.attachments || {})
  const [completionMessage, setCompletionMessage] = React.useState('')
  const [completingAnnualReport, setCompletingAnnualReport] = React.useState(false)
  const update = (field, value) => setForm(current => ({ ...current, [field]: value }))
  const uploadAttachment = async () => {
    if (!uploadFile) return
    const body = new FormData()
    body.append('item_type', uploadItemType)
    body.append('file', uploadFile)
    try {
      await api.post(`/api/compliance/${encodeURIComponent(row.state)}/attachments`, body)
      setUploadFile(null)
      setUploadMessage(`${COMPLIANCE_ATTACHMENT_TYPES.find(option => option.value === uploadItemType)?.label || 'Compliance'} PDF uploaded.`)
      document.getElementById('compliance-pdf-upload').value = ''
      const refreshed = await api.get(`/api/compliance/${encodeURIComponent(row.state)}/attachments`)
      setAttachments(COMPLIANCE_ATTACHMENT_TYPES.reduce((groups, option) => ({ ...groups, [option.value]: refreshed.data.attachments.filter(item => item.item_type === option.value) }), {}))
      window.dispatchEvent(new CustomEvent('compliance-attachments-updated'))
    } catch (err) {
      setUploadMessage(err.response?.data?.detail || 'Unable to upload PDF.')
    }
  }
  const deleteAttachment = async (attachment) => {
    if (!window.confirm(`Delete ${attachment.filename}? This cannot be undone.`)) return
    try {
      await api.delete(`/api/compliance/${encodeURIComponent(row.state)}/attachments/${attachment.id}`)
      setAttachments(current => ({ ...current, [attachment.item_type]: (current[attachment.item_type] || []).filter(item => item.id !== attachment.id) }))
      setUploadMessage(`${attachment.filename} deleted.`)
      window.dispatchEvent(new CustomEvent('compliance-attachments-updated'))
    } catch (err) {
      setUploadMessage(err.response?.data?.detail || 'Unable to delete PDF.')
    }
  }
  const loadCredentials = async () => {
    try {
      const response = await api.get(`/api/compliance/${encodeURIComponent(row.state)}/portal-credentials`)
      setForm(current => ({ ...current, portal_username: response.data.username || '', portal_password: response.data.password || '', clear_portal_password: false }))
      setShowPassword(true)
      setCredentialMessage('Stored credentials loaded.')
    } catch (err) {
      setCredentialMessage(err.response?.data?.detail || 'Unable to load stored credentials.')
    }
  }
  const completeAnnualReport = async () => {
    setCompletingAnnualReport(true)
    setCompletionMessage('')
    try {
      const response = await api.post(`/api/compliance/${encodeURIComponent(row.state)}/annual-report/complete`)
      setForm(current => ({
        ...current,
        annual_report_completed_at: response.data.annual_report_completed_at,
        annual_report_completed_by: response.data.annual_report_completed_by,
        annual_report_completed_by_name: response.data.annual_report_completed_by_name,
      }))
      setCompletionMessage('Annual report marked completed.')
      window.dispatchEvent(new CustomEvent('compliance-attachments-updated'))
    } catch (err) {
      setCompletionMessage(err.response?.data?.detail || 'Unable to mark annual report completed.')
    } finally {
      setCompletingAnnualReport(false)
    }
  }
  const submit = e => { e.preventDefault(); onSave(compliancePayload({ ...form, source_urls: form.source_urls_text.split('\n'), document_paths: form.document_paths_text.split('\n') })) }
  return <div className="fixed inset-0 z-50 bg-black/50 overflow-y-auto p-4" onClick={onClose}><form onSubmit={submit} onClick={e => e.stopPropagation()} className="bg-white rounded-2xl shadow-2xl max-w-5xl mx-auto my-6 p-6 space-y-6"><div className="flex justify-between items-start"><div><h2 className="text-xl font-bold">Edit {row.state}</h2><p className="text-sm text-gray-500">{form.jurisdiction || row.state}</p></div><button type="button" onClick={onClose} className="text-gray-500 text-xl" aria-label="Close">✕</button></div>
    <div className="flex gap-2 border-b" role="tablist"><button type="button" role="tab" aria-selected={activeTab === 'details'} onClick={() => setActiveTab('details')} className={`px-4 py-2 text-sm font-medium border-b-2 ${activeTab === 'details' ? 'border-blue-600 text-blue-700' : 'border-transparent text-gray-500'}`}>Compliance Details</button><button type="button" role="tab" aria-selected={activeTab === 'files'} onClick={() => setActiveTab('files')} className={`px-4 py-2 text-sm font-medium border-b-2 ${activeTab === 'files' ? 'border-blue-600 text-blue-700' : 'border-transparent text-gray-500'}`}>PDF Files</button></div>
    {activeTab === 'details' && <>
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4"><Field label="Jurisdiction"><input value={form.jurisdiction || ''} onChange={e => update('jurisdiction', e.target.value)} className={inputClass} /></Field><Field label="State Portal"><input type="url" placeholder="https://state.gov/portal" value={form.state_portal_url || ''} onChange={e => update('state_portal_url', e.target.value)} className={inputClass} /></Field><SelectField label="Data confidence" value={form.data_confidence} options={CONFIDENCE_LEVELS} onChange={v => update('data_confidence', v)} /></div>
    <div><h3 className="font-semibold mb-3">Collection License</h3><div className="grid grid-cols-1 md:grid-cols-4 gap-4"><SelectField label="Requirement" value={form.collection_license_requirement} options={REQUIREMENTS} onChange={v => update('collection_license_requirement', v)} />{form.collection_license_requirement === 'Required' && <><SelectField label="Status" value={form.license_status} options={LICENSE_STATUSES} onChange={v => update('license_status', v)} /><Field label="License number"><input value={form.license_number || ''} onChange={e => update('license_number', e.target.value)} className={inputClass} /></Field><Field label="Issue date"><input type="date" value={form.license_issue_date || ''} onChange={e => update('license_issue_date', e.target.value || null)} className={inputClass} /></Field><Field label="Expiration"><input type="date" value={form.license_expiration || ''} onChange={e => update('license_expiration', e.target.value || null)} className={inputClass} /></Field><Field label="Renewal due"><input type="date" value={form.license_renewal_due || ''} onChange={e => update('license_renewal_due', e.target.value || null)} className={inputClass} /></Field></>}</div>{form.collection_license_requirement === 'Not Required' && <p className="text-sm text-gray-500 mt-2">No license status or details are required.</p>}</div>
    <div><h3 className="font-semibold mb-3">Certificate of Authority</h3><div className="grid grid-cols-1 md:grid-cols-4 gap-4"><SelectField label="Requirement" value={form.coa_requirement} options={REQUIREMENTS} onChange={v => update('coa_requirement', v)} />{form.coa_requirement === 'Required' && <><SelectField label="Status" value={form.coa_status} options={COA_STATUSES} onChange={v => update('coa_status', v)} /><Field label="COA number"><input value={form.coa_number || ''} onChange={e => update('coa_number', e.target.value)} className={inputClass} /></Field><Field label="Issue date"><input type="date" value={form.coa_issue_date || ''} onChange={e => update('coa_issue_date', e.target.value || null)} className={inputClass} /></Field></>}</div>{form.coa_requirement === 'Not Required' && <p className="text-sm text-gray-500 mt-2">No certificate of authority status or details are required.</p>}</div>
    <div><h3 className="font-semibold mb-3">Surety Bond</h3><div className="grid grid-cols-1 md:grid-cols-4 gap-4"><SelectField label="Requirement" value={form.bond_requirement} options={REQUIREMENTS} onChange={v => update('bond_requirement', v)} />{form.bond_requirement === 'Required' && <><SelectField label="Status" value={form.bond_status} options={BOND_STATUSES} onChange={v => update('bond_status', v)} /><Field label="Bond number"><input value={form.bond_number || ''} onChange={e => update('bond_number', e.target.value)} className={inputClass} /></Field><Field label="Bond amount"><input type="number" min="0" step="0.01" value={form.bond_amount ?? ''} onChange={e => update('bond_amount', e.target.value)} className={inputClass} /></Field><Field label="Bond expiration"><input type="date" value={form.bond_expiration || ''} onChange={e => update('bond_expiration', e.target.value || null)} className={inputClass} /></Field></>}</div>{form.bond_requirement === 'Not Required' && <p className="text-sm text-gray-500 mt-2">No bond status or details are required.</p>}</div>
    <div className="rounded-xl border border-purple-200 bg-purple-50 p-4 space-y-3"><h3 className="font-semibold text-purple-950">Annual Reports</h3><div className="grid grid-cols-1 md:grid-cols-3 gap-4"><SelectField label="Requirement" value={form.annual_report_requirement || 'Not Required'} options={ANNUAL_REPORT_REQUIREMENTS} onChange={v => update('annual_report_requirement', v)} />{form.annual_report_requirement !== 'Not Required' && <Field label="Due Date"><input type="date" value={form.annual_report_due_date || ''} onChange={e => update('annual_report_due_date', e.target.value || null)} className={inputClass} /></Field>}</div><div className="rounded-lg bg-white border p-3"><div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3"><div><p className="text-sm font-medium">Completion</p>{form.annual_report_completed_at ? <p className="text-xs text-gray-600">Completed {new Date(form.annual_report_completed_at).toLocaleString()} by {form.annual_report_completed_by_name || form.annual_report_completed_by || 'Unknown user'}</p> : <p className="text-xs text-gray-500">Not completed yet.</p>}</div><button type="button" disabled={completingAnnualReport} onClick={completeAnnualReport} className="px-3 py-2 rounded-lg bg-purple-700 text-white text-sm disabled:opacity-50">{completingAnnualReport ? 'Marking...' : 'Mark Completed'}</button></div>{completionMessage && <p className="mt-2 text-xs text-purple-800">{completionMessage}</p>}</div></div>
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4"><Field label="Notes"><textarea rows="4" value={form.notes || ''} onChange={e => update('notes', e.target.value)} className={inputClass} /></Field><Field label="Username"><input autoComplete="off" value={form.portal_username || ''} onChange={e => update('portal_username', e.target.value)} className={inputClass} /></Field><Field label="Password"><input type={showPassword ? 'text' : 'password'} autoComplete="new-password" placeholder={row.has_portal_password ? 'Stored — use Load credentials to view' : ''} value={form.portal_password || ''} onChange={e => update('portal_password', e.target.value)} className={inputClass} /><div className="mt-2 flex flex-wrap items-center gap-2">{row.has_portal_password && <button type="button" onClick={loadCredentials} className="text-xs px-2 py-1 border rounded hover:bg-gray-50">Load credentials</button>}{form.portal_password && <button type="button" onClick={() => setShowPassword(current => !current)} className="text-xs px-2 py-1 border rounded hover:bg-gray-50">{showPassword ? 'Hide password' : 'Show password'}</button>}{row.has_portal_password && <label className="flex items-center gap-2 text-xs text-gray-600"><input type="checkbox" checked={form.clear_portal_password} onChange={e => update('clear_portal_password', e.target.checked)} /> Remove stored password</label>}</div>{credentialMessage && <p className="mt-1 text-xs text-gray-600">{credentialMessage}</p>}</Field></div>
    {error && <p className="text-sm text-red-600">Save failed: {error.response?.data?.detail || error.message}</p>}<div className="flex justify-end gap-3 border-t pt-4"><button type="button" onClick={onClose} className="px-4 py-2 border rounded-lg">Cancel</button><button type="submit" disabled={saving} className="px-4 py-2 bg-blue-600 text-white rounded-lg disabled:opacity-50">{saving ? 'Saving...' : 'Save compliance record'}</button></div></>}
    {activeTab === 'files' && <div className="space-y-5"><div className="rounded-lg border border-blue-200 bg-blue-50 p-4"><h3 className="font-semibold text-blue-900 mb-2">Upload Compliance PDF</h3><div className="flex flex-col sm:flex-row gap-2"><select aria-label="PDF item type" value={uploadItemType} onChange={e => setUploadItemType(e.target.value)} className={inputClass}>{COMPLIANCE_ATTACHMENT_TYPES.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</select><input id="compliance-pdf-upload" type="file" accept="application/pdf,.pdf" onChange={e => setUploadFile(e.target.files?.[0] || null)} className={`${inputClass} bg-white`} /><button type="button" disabled={!uploadFile} onClick={uploadAttachment} className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm disabled:opacity-50">Upload PDF</button></div>{uploadMessage && <p className="mt-2 text-xs text-blue-800">{uploadMessage}</p>}</div><div className="grid grid-cols-1 md:grid-cols-2 gap-4">{COMPLIANCE_ATTACHMENT_TYPES.map(option => <section key={option.value} className="rounded-lg border p-4"><h3 className="font-semibold mb-3">{option.label}</h3>{(attachments[option.value] || []).length === 0 ? <p className="text-sm text-gray-500">No PDFs uploaded.</p> : <ul className="space-y-2">{attachments[option.value].map(attachment => <li key={attachment.id} className="flex items-center justify-between gap-3 rounded bg-gray-50 p-2"><button type="button" onClick={() => api.get(attachment.view_url, { responseType: 'blob' }).then(response => window.open(URL.createObjectURL(new Blob([response.data], { type: 'application/pdf' })), '_blank', 'noopener,noreferrer'))} className="text-sm text-blue-600 hover:underline truncate" title={attachment.filename}>{attachment.filename}</button><button type="button" onClick={() => deleteAttachment(attachment)} className="text-xs text-red-600 hover:underline">Delete</button></li>)}</ul>}</section>)}</div><div className="flex justify-end border-t pt-4"><button type="button" onClick={onClose} className="px-4 py-2 border rounded-lg">Close</button></div></div>}
  </form></div>
}
