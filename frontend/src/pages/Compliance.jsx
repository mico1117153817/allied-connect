import React from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import { logout } from '../lib/auth'
import { COMPLIANCE_REQUIREMENTS, COMPLIANCE_STATUSES, complianceIndicator, compliancePayload, complianceSummary, filterComplianceRows, normalizeComplianceEditor } from '../lib/compliance'

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
  const rows = data?.states || []
  const summary = complianceSummary(rows)
  const visibleRows = filterComplianceRows(rows, status, search)

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
              <select aria-label="Filter compliance status" value={status} onChange={e => setStatus(e.target.value)} className={inputClass}>
                <option value="all">All statuses</option><option value="active">Active</option><option value="needs review">Needs Review</option><option value="not authorized">Not Authorized</option>
              </select>
              {status !== 'all' && <button type="button" onClick={() => setStatus('all')} className="px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-700 hover:bg-gray-50 whitespace-nowrap">Clear filter</button>}
            </div>
          </div>
          {isLoading && <p className="text-gray-500 py-8 text-center">Loading all 50 states...</p>}
          {isError && <p className="text-red-600 py-8 text-center">Unable to load compliance data: {error?.response?.data?.detail || error.message}</p>}
          {!isLoading && !isError && <div className="overflow-x-auto"><table className="w-full min-w-[1050px] text-sm"><thead><tr className="border-b text-left text-gray-500"><th className="p-3">State</th><th className="p-3">Overall</th><th className="p-3">Confidence</th><th className="p-3">License</th><th className="p-3">COA</th><th className="p-3">Bond</th><th className="p-3">State Portal</th><th className="p-3">Issues</th><th className="p-3">Action</th></tr></thead><tbody>{visibleRows.map(row => <ComplianceRow key={row.state} row={row} onEdit={() => setSelected(row)} />)}</tbody></table>{visibleRows.length === 0 && <p className="text-gray-500 text-center py-8">No states match the current filters.</p>}</div>}
        </section>
      </main>
      {selected && <ComplianceEditor row={selected} saving={save.isPending} error={save.error} onClose={() => setSelected(null)} onSave={payload => save.mutate({ state: selected.state, payload })} />}
    </div>
  )
}

function SummaryCard({ label, value, color, active, onClick }) {
  const colors = { blue: 'bg-blue-50 text-blue-700', green: 'bg-green-50 text-green-700', yellow: 'bg-yellow-50 text-yellow-700', red: 'bg-red-50 text-red-700', gray: 'bg-gray-100 text-gray-700' }
  return <button type="button" onClick={onClick} aria-pressed={active} aria-label={`Show ${label}: ${value}`} className={`rounded-xl p-4 text-left transition hover:-translate-y-0.5 hover:shadow-md focus:outline-none focus:ring-2 focus:ring-blue-500 ${colors[color]} ${active ? 'ring-2 ring-offset-2 ring-blue-600 shadow-md' : ''}`}><p className="text-xs opacity-75">{label}</p><p className="text-2xl font-bold">{value}</p><p className="text-[11px] mt-1 opacity-70">Click to filter</p></button>
}

function statusClass(indicator) { return ({ green: 'bg-green-100 text-green-800', yellow: 'bg-yellow-100 text-yellow-800', red: 'bg-red-100 text-red-800', gray: 'bg-gray-100 text-gray-700' })[indicator] || 'bg-gray-100 text-gray-700' }
function ComplianceRow({ row, onEdit }) {
  const marker = complianceIndicator(row)
  const markerStyles = {
    green: 'bg-green-600 text-white ring-green-200',
    red: 'bg-red-600 text-white ring-red-200',
    yellow: 'bg-yellow-400 text-yellow-950 ring-yellow-200',
    gray: 'bg-gray-500 text-white ring-gray-200',
  }
  return <tr className="border-b hover:bg-blue-50"><td className="p-3"><div className="flex items-center gap-3"><span title={marker.label} aria-label={`${row.state}: ${marker.label}`} className={`inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-sm font-black ring-4 ${markerStyles[marker.tone]}`}>{marker.symbol}</span><div><div className="font-semibold">{row.state}</div><div className={`text-xs font-medium ${marker.tone === 'green' ? 'text-green-700' : marker.tone === 'red' ? 'text-red-700' : marker.tone === 'yellow' ? 'text-yellow-700' : 'text-gray-600'}`}>{marker.label}</div></div></div></td><td className="p-3"><span className={`inline-block px-2 py-1 rounded-full text-xs font-medium ${statusClass(row.indicator)}`}>{row.overall_status === 'Unknown' ? 'Needs Review' : row.overall_status}</span></td><td className="p-3">{row.data_confidence}</td><td className="p-3"><div>{row.collection_license_requirement === 'Not Required' ? 'Not Required' : row.license_status}</div><div className="text-xs text-gray-500">{row.collection_license_requirement === 'Not Required' ? 'No license details required' : `${row.license_number || 'No number'}${row.license_expiration ? ` · exp ${row.license_expiration}` : ''}`}</div></td><td className="p-3"><div>{row.coa_requirement}</div><div className="text-xs text-gray-500">{row.coa_requirement === 'Not Required' ? 'No COA details required' : `${row.coa_status}${row.coa_number ? ` · ${row.coa_number}` : ''}`}</div></td><td className="p-3"><div>{row.bond_requirement}</div><div className="text-xs text-gray-500">{row.bond_requirement === 'Not Required' ? 'No bond details required' : `${row.bond_status}${row.bond_amount != null ? ` · $${Number(row.bond_amount).toLocaleString()}` : ''}`}</div></td><td className="p-3">{row.state_portal_url ? <a href={row.state_portal_url} target="_blank" rel="noreferrer" className="text-blue-600 hover:underline">Open portal ↗</a> : '—'}</td><td className="p-3">{row.issues?.length ? <ul className="text-xs text-yellow-800 list-disc pl-4">{row.issues.map(issue => <li key={issue}>{issue}</li>)}</ul> : '—'}</td><td className="p-3"><button onClick={onEdit} className="px-3 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">Edit</button></td></tr>
}

function Field({ label, children }) { return <label className="block"><span className="block text-xs font-medium text-gray-600 mb-1">{label}</span>{children}</label> }
function SelectField({ label, value, options, onChange }) { return <Field label={label}><select required value={value || ''} onChange={e => onChange(e.target.value)} className={inputClass}><option value="" disabled>Select...</option>{options.map(option => <option key={option}>{option}</option>)}</select></Field> }
function ComplianceEditor({ row, onClose, onSave, saving, error }) {
  const [form, setForm] = React.useState({ ...normalizeComplianceEditor(row), portal_password: '', clear_portal_password: false, source_urls_text: (row.source_urls || []).join('\n'), document_paths_text: (row.document_paths || []).join('\n') })
  const [credentialMessage, setCredentialMessage] = React.useState('')
  const [showPassword, setShowPassword] = React.useState(false)
  const update = (field, value) => setForm(current => ({ ...current, [field]: value }))
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
  const submit = e => { e.preventDefault(); onSave(compliancePayload({ ...form, source_urls: form.source_urls_text.split('\n'), document_paths: form.document_paths_text.split('\n') })) }
  return <div className="fixed inset-0 z-50 bg-black/50 overflow-y-auto p-4" onClick={onClose}><form onSubmit={submit} onClick={e => e.stopPropagation()} className="bg-white rounded-2xl shadow-2xl max-w-5xl mx-auto my-6 p-6 space-y-6"><div className="flex justify-between items-start"><div><h2 className="text-xl font-bold">Edit {row.state}</h2><p className="text-sm text-gray-500">{form.jurisdiction || row.state}</p></div><button type="button" onClick={onClose} className="text-gray-500 text-xl" aria-label="Close">✕</button></div>
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4"><Field label="Jurisdiction"><input value={form.jurisdiction || ''} onChange={e => update('jurisdiction', e.target.value)} className={inputClass} /></Field><Field label="State Portal"><input type="url" placeholder="https://state.gov/portal" value={form.state_portal_url || ''} onChange={e => update('state_portal_url', e.target.value)} className={inputClass} /></Field><SelectField label="Data confidence" value={form.data_confidence} options={CONFIDENCE_LEVELS} onChange={v => update('data_confidence', v)} /></div>
    <div><h3 className="font-semibold mb-3">Collection License</h3><div className="grid grid-cols-1 md:grid-cols-4 gap-4"><SelectField label="Requirement" value={form.collection_license_requirement} options={REQUIREMENTS} onChange={v => update('collection_license_requirement', v)} />{form.collection_license_requirement === 'Required' && <><SelectField label="Status" value={form.license_status} options={LICENSE_STATUSES} onChange={v => update('license_status', v)} /><Field label="License number"><input value={form.license_number || ''} onChange={e => update('license_number', e.target.value)} className={inputClass} /></Field><Field label="Issue date"><input type="date" value={form.license_issue_date || ''} onChange={e => update('license_issue_date', e.target.value || null)} className={inputClass} /></Field><Field label="Expiration"><input type="date" value={form.license_expiration || ''} onChange={e => update('license_expiration', e.target.value || null)} className={inputClass} /></Field><Field label="Renewal due"><input type="date" value={form.license_renewal_due || ''} onChange={e => update('license_renewal_due', e.target.value || null)} className={inputClass} /></Field></>}</div>{form.collection_license_requirement === 'Not Required' && <p className="text-sm text-gray-500 mt-2">No license status or details are required.</p>}</div>
    <div><h3 className="font-semibold mb-3">Certificate of Authority</h3><div className="grid grid-cols-1 md:grid-cols-4 gap-4"><SelectField label="Requirement" value={form.coa_requirement} options={REQUIREMENTS} onChange={v => update('coa_requirement', v)} />{form.coa_requirement === 'Required' && <><SelectField label="Status" value={form.coa_status} options={COA_STATUSES} onChange={v => update('coa_status', v)} /><Field label="COA number"><input value={form.coa_number || ''} onChange={e => update('coa_number', e.target.value)} className={inputClass} /></Field><Field label="Issue date"><input type="date" value={form.coa_issue_date || ''} onChange={e => update('coa_issue_date', e.target.value || null)} className={inputClass} /></Field></>}</div>{form.coa_requirement === 'Not Required' && <p className="text-sm text-gray-500 mt-2">No certificate of authority status or details are required.</p>}</div>
    <div><h3 className="font-semibold mb-3">Surety Bond</h3><div className="grid grid-cols-1 md:grid-cols-4 gap-4"><SelectField label="Requirement" value={form.bond_requirement} options={REQUIREMENTS} onChange={v => update('bond_requirement', v)} />{form.bond_requirement === 'Required' && <><SelectField label="Status" value={form.bond_status} options={BOND_STATUSES} onChange={v => update('bond_status', v)} /><Field label="Bond number"><input value={form.bond_number || ''} onChange={e => update('bond_number', e.target.value)} className={inputClass} /></Field><Field label="Bond amount"><input type="number" min="0" step="0.01" value={form.bond_amount ?? ''} onChange={e => update('bond_amount', e.target.value)} className={inputClass} /></Field><Field label="Bond expiration"><input type="date" value={form.bond_expiration || ''} onChange={e => update('bond_expiration', e.target.value || null)} className={inputClass} /></Field></>}</div>{form.bond_requirement === 'Not Required' && <p className="text-sm text-gray-500 mt-2">No bond status or details are required.</p>}</div>
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4"><Field label="Notes"><textarea rows="4" value={form.notes || ''} onChange={e => update('notes', e.target.value)} className={inputClass} /></Field><Field label="Username"><input autoComplete="off" value={form.portal_username || ''} onChange={e => update('portal_username', e.target.value)} className={inputClass} /></Field><Field label="Password"><input type={showPassword ? 'text' : 'password'} autoComplete="new-password" placeholder={row.has_portal_password ? 'Stored — use Load credentials to view' : ''} value={form.portal_password || ''} onChange={e => update('portal_password', e.target.value)} className={inputClass} /><div className="mt-2 flex flex-wrap items-center gap-2">{row.has_portal_password && <button type="button" onClick={loadCredentials} className="text-xs px-2 py-1 border rounded hover:bg-gray-50">Load credentials</button>}{form.portal_password && <button type="button" onClick={() => setShowPassword(current => !current)} className="text-xs px-2 py-1 border rounded hover:bg-gray-50">{showPassword ? 'Hide password' : 'Show password'}</button>}{row.has_portal_password && <label className="flex items-center gap-2 text-xs text-gray-600"><input type="checkbox" checked={form.clear_portal_password} onChange={e => update('clear_portal_password', e.target.checked)} /> Remove stored password</label>}</div>{credentialMessage && <p className="mt-1 text-xs text-gray-600">{credentialMessage}</p>}</Field></div>
    {error && <p className="text-sm text-red-600">Save failed: {error.response?.data?.detail || error.message}</p>}<div className="flex justify-end gap-3 border-t pt-4"><button type="button" onClick={onClose} className="px-4 py-2 border rounded-lg">Cancel</button><button type="submit" disabled={saving} className="px-4 py-2 bg-blue-600 text-white rounded-lg disabled:opacity-50">{saving ? 'Saving...' : 'Save compliance record'}</button></div>
  </form></div>
}
