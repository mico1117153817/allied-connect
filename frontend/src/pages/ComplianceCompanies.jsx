import React from 'react'
import CorporateDocuments from '../components/CorporateDocuments'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import { logout } from '../lib/auth'
import { COMPLIANCE_COMPANY_FIELDS, complianceCompanyPayload, complianceError } from '../lib/compliance'
import { formatDateTime12Hour } from '../lib/time'

const inputClass = 'w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500'
const buttonClass = 'px-3 py-2 border rounded-lg text-sm hover:bg-blue-50 disabled:opacity-50'
export const COMPANY_METRICS = [
  ['total', 'All Jurisdictions', 'all'], ['active', 'Active', 'active'],
  ['needs_review', 'Needs Review', 'needs review'], ['not_authorized', 'Not Authorized', 'not authorized'],
  ['licenses_expiring_30', 'Licenses expiring · 30 days', 'licenses_expiring_30'],
  ['licenses_expiring_60', 'Licenses expiring · 60 days', 'licenses_expiring_60'],
  ['licenses_expiring_90', 'Licenses expiring · 90 days', 'licenses_expiring_90'],
  ['bonds_expiring_soon', 'Bonds expiring · 90 days', 'bonds_expiring_soon'],
  ['annual_reports_due_soon', 'Reports due · 90 days', 'annual_reports_due_soon'],
  ['open_issues', 'States with open issues', 'open_issues'],
  ['expiring_soon', 'Expiring soon · 90 days', 'expiring_soon'],
]

export function CompanyLogo({ company }) {
  const [src, setSrc] = React.useState('')
  const [failed, setFailed] = React.useState(false)
  React.useEffect(() => {
    let cancelled = false
    let objectUrl
    setSrc('')
    setFailed(false)
    if (company.logo_path) api.get(`/api/compliance/companies/${company.id}/logo`, { responseType: 'blob' }).then(response => {
      if (cancelled) return
      objectUrl = URL.createObjectURL(response.data)
      setSrc(objectUrl)
    }).catch(() => { if (!cancelled) setFailed(true) })
    return () => { cancelled = true; if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [company.id, company.logo_path, company.updated_at])
  return src ? <img src={src} alt={`${company.legal_name} logo`} className="h-14 max-w-40 object-contain rounded" /> : <span className="rounded-lg bg-blue-50 text-blue-700 p-3 text-sm" aria-label={failed ? 'Company logo unavailable' : 'Company logo'}>{failed ? 'Logo unavailable' : 'Company'}</span>
}

export default function ComplianceCompanies({ children }) {
  const [selectedId, setSelectedId] = React.useState('')
  const [initialMetric, setInitialMetric] = React.useState('all')
  const [selectionRevision, setSelectionRevision] = React.useState(0)
  const [managing, setManaging] = React.useState(false)
  const companiesQuery = useQuery({ queryKey: ['compliance-companies'], queryFn: () => api.get('/api/compliance/companies').then(r => r.data) })
  const companies = companiesQuery.data?.companies || []
  const companyId = selectedId || String(companies.find(company => company.is_active)?.id || companies[0]?.id || '')
  const company = companies.find(item => String(item.id) === companyId)
  const select = (id, metric = 'all') => { setSelectedId(String(id)); setInitialMetric(metric); setSelectionRevision(value => value + 1); setManaging(false) }
  return <div className="min-h-screen bg-gray-50">
    <header className="bg-white shadow-sm"><div className="max-w-7xl mx-auto px-4 py-4 flex flex-col gap-3 sm:flex-row sm:justify-between sm:items-center">
      <div className="flex items-center gap-3"><img src="/allied-logo.jpg" alt="Allied" className="h-10 w-auto rounded" /><div><h1 className="text-xl font-bold">Compliance Register</h1><p className="text-xs text-gray-500">State licensing, COA, and bond tracking</p></div></div>
      <div className="flex flex-wrap gap-4"><a href="/dashboard" className="text-sm text-blue-600 hover:underline">← Dashboard</a><a href="/compliance" className="text-sm text-blue-600 hover:underline">State Licensing</a><a href="/company-tasks" className="text-sm text-blue-600 hover:underline">Company Tasks</a><button onClick={logout} className="text-sm text-red-600 hover:underline">Logout</button></div>
    </div></header>
    <section className="max-w-7xl mx-auto px-4 pt-6 space-y-4">
      <div className="bg-white rounded-xl shadow-sm p-4 flex flex-col sm:flex-row sm:items-end gap-3">
        <label className="flex-1"><span className="block text-xs font-medium text-gray-600 mb-1">Compliance company</span><select aria-label="Compliance company" className={inputClass} value={companyId} onChange={e => select(e.target.value)} disabled={companiesQuery.isLoading || companiesQuery.isError}>
          {!companies.length && <option value="">Select a company</option>}
          {companiesQuery.data?.is_super_admin && <option value="all">All Companies — overview</option>}
          {companies.map(item => <option key={item.id} value={item.id}>{item.legal_name}{item.is_active === false ? ' (Archived)' : ''}</option>)}
        </select></label>
        <button className={buttonClass} onClick={() => setManaging(true)} disabled={companiesQuery.isLoading || companiesQuery.isError}>{companiesQuery.data?.can_manage ? 'Manage Companies' : 'View Companies'}</button>
      </div>
      {companiesQuery.isLoading && <p className="text-gray-500">Loading companies…</p>}
      {companiesQuery.isError && <p role="alert" className="text-red-700">{complianceError(companiesQuery.error)}</p>}
      {!companiesQuery.isLoading && !companiesQuery.isError && !companies.length && <p className="text-gray-500">No accessible companies. {companiesQuery.data?.can_manage ? 'Use Manage Companies to add one.' : 'Contact a compliance administrator.'}</p>}
      {companyId === 'all' && companiesQuery.data?.is_super_admin && <section className="bg-white rounded-xl shadow-sm p-5"><h2 className="text-lg font-semibold">All Companies</h2><p className="text-sm text-gray-500 mb-4">Company summaries only. Select any count to open that company’s filtered matrix. “Soon” includes today through 90 days.</p><div className="overflow-x-auto"><table className="w-full text-sm"><thead><tr className="border-b text-left"><th className="p-3">Company</th>{COMPANY_METRICS.map(([key, label]) => <th className="p-3 min-w-28" key={key}>{label}</th>)}</tr></thead><tbody>{companies.map(item => <tr className="border-b" key={item.id}><th className="p-3 text-left"><button className="text-blue-700 hover:underline" onClick={() => select(item.id)}>{item.legal_name}</button>{item.is_active === false && <span className="block text-xs text-gray-500">Archived · Read-only</span>}</th>{COMPANY_METRICS.map(([key, label, metric]) => <td className="p-3" key={key}><button className="text-blue-700 underline px-2 py-1" aria-label={`${item.legal_name}: ${label}`} onClick={() => select(item.id, metric)}>{item.summary?.[key] ?? '—'}</button></td>)}</tr>)}</tbody></table></div></section>}
    </section>
    {company && !companiesQuery.isError && children(company, initialMetric, selectionRevision)}
    {managing && <CompanyManager companies={companies} canManage={companiesQuery.data?.can_manage === true} onClose={() => setManaging(false)} onSelect={select} />}
  </div>
}

function CompanyManager({ companies, canManage, onClose, onSelect }) {
  const [editingId, setEditingId] = React.useState(null)
  const company = companies.find(item => item.id === editingId)
  return <div className="fixed inset-0 z-50 bg-black/50 overflow-y-auto p-4" onClick={onClose}><section role="dialog" aria-modal="true" aria-label="Manage compliance companies" onClick={e => e.stopPropagation()} className="bg-white max-w-5xl mx-auto my-6 p-6 rounded-2xl shadow-2xl space-y-5">
    <div className="flex justify-between items-center"><h2 className="text-xl font-bold">{canManage ? 'Manage Companies' : 'Company Directory'}</h2><button onClick={onClose} className={buttonClass}>Close</button></div>
    <div className="flex flex-wrap gap-2">{canManage && <button onClick={() => setEditingId('new')} className="px-3 py-2 bg-blue-600 text-white rounded-lg text-sm">Add Company</button>}{companies.map(item => <button key={item.id} onClick={() => setEditingId(item.id)} className={`${buttonClass} ${editingId === item.id ? 'ring-2 ring-blue-500' : ''}`}>{item.legal_name}{item.is_active === false ? ' (Archived)' : ''}</button>)}</div>
    {editingId === null && <p className="text-sm text-gray-500">Select a company to view its complete profile, or add a new company.</p>}
    {editingId === 'new' && <CompanyForm key="new" company={{ legal_name: '', is_active: true }} companies={companies} canManage={canManage} onSaved={item => setEditingId(item.id)} onSelect={onSelect} />}
    {company && <CompanyProfile key={company.id} company={company} companies={companies} canManage={canManage && company.can_manage !== false} onSelect={onSelect} />}
  </section></div>
}

function CompanyProfile({ company, ...props }) {
  const detail = useQuery({ queryKey: ['compliance-company', company.id], queryFn: () => api.get(`/api/compliance/companies/${company.id}`).then(r => r.data) })
  if (detail.isLoading) return <p>Loading company profile…</p>
  if (detail.isError) return <p role="alert" className="text-red-700">{complianceError(detail.error)}</p>
  const current = { ...company, ...(detail.data?.company || detail.data) }
  return <><CompanyForm key={`${current.id}:${current.updated_at}:${current.is_active}`} {...props} company={current} />
    <CorporateDocuments company={current} /></>
}

function CompanyForm({ company, companies, canManage, onSaved, onSelect }) {
  const qc = useQueryClient()
  const [form, setForm] = React.useState(company)
  const [copyFrom, setCopyFrom] = React.useState('')
  const [logoFile, setLogoFile] = React.useState(null)
  const [notice, setNotice] = React.useState('')
  const mounted = React.useRef(true)
  React.useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  const isNew = !company.id
  const editable = canManage && company.is_active !== false
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['compliance-companies'] })
    if (company.id) {
      qc.invalidateQueries({ queryKey: ['compliance-company', company.id] })
      qc.invalidateQueries({ queryKey: ['compliance', company.id] })
    }
  }
  const save = useMutation({
    mutationFn: () => isNew ? api.post('/api/compliance/companies', complianceCompanyPayload(form, copyFrom || null)) : api.put(`/api/compliance/companies/${company.id}`, complianceCompanyPayload(form)),
    onSuccess: response => { refresh(); if (mounted.current) { setNotice('Company saved.'); if (isNew) onSaved?.(response.data.company || response.data) } },
  })
  const archive = useMutation({ mutationFn: () => api.put(`/api/compliance/companies/${company.id}`, { is_active: false }), onSuccess: refresh })
  const logo = useMutation({ mutationFn: () => { const body = new FormData(); body.append('file', logoFile); return api.post(`/api/compliance/companies/${company.id}/logo`, body) }, onSuccess: () => { refresh(); if (mounted.current) { setLogoFile(null); setNotice('Logo uploaded.') } } })
  const busy = save.isPending || archive.isPending || logo.isPending
  return <form onSubmit={event => { event.preventDefault(); if (editable && !busy) save.mutate() }} className="space-y-5">
    <div className="flex items-center gap-4">{!isNew && <CompanyLogo company={company} />}<div><h3 className="text-lg font-semibold">{isNew ? 'Add Company' : company.legal_name}</h3><p className="text-sm text-gray-500">{company.is_active === false ? 'Archived · Read-only. Compliance records and history are retained.' : 'Company profile'}</p></div></div>
    {!isNew && <section aria-label="Company compliance summary" className="grid grid-cols-2 md:grid-cols-4 gap-2">{COMPANY_METRICS.map(([key, label, metric]) => <button type="button" key={key} className="rounded-lg bg-blue-50 p-3 text-left hover:bg-blue-100" aria-label={`${company.legal_name}: ${label}`} onClick={() => onSelect(company.id, metric)}><span className="block text-xs text-gray-600">{label}</span><span className="block text-lg font-semibold text-blue-700">{company.summary?.[key] ?? '—'}</span></button>)}</section>}
    <fieldset disabled={!editable || busy} className="space-y-4">
      {isNew && <div className="border border-blue-200 bg-blue-50 rounded-xl p-4 space-y-2"><label className="block text-sm font-medium">Starting requirements<select className={`${inputClass} mt-1`} value={copyFrom} onChange={e => setCopyFrom(e.target.value)}><option value="">Start blank — no company requirements copied</option>{companies.map(item => <option key={item.id} value={item.id}>Copy requirements from {item.legal_name}</option>)}</select></label><p className="text-sm text-blue-900">Copy requirements only — never credentials, license or bond numbers, issued dates, PDFs, completion records, or company-specific notes. Review all copied requirements for the new entity.</p></div>}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">{COMPLIANCE_COMPANY_FIELDS.map(([key, label, type = 'text']) => <label key={key} className="block"><span className="block text-xs font-medium text-gray-600 mb-1">{label}{key === 'legal_name' ? ' *' : ''}</span>{type === 'textarea' ? <textarea rows="3" className={inputClass} value={form[key] || ''} onChange={e => setForm(current => ({ ...current, [key]: e.target.value }))} /> : <input required={key === 'legal_name'} type={type} className={inputClass} value={form[key] || ''} onChange={e => setForm(current => ({ ...current, [key]: e.target.value }))} />}</label>)}</div>
    </fieldset>
    {!isNew && <div className="text-xs text-gray-500 space-y-1"><p>Company ID: {company.id} · Status: {company.is_active === false ? 'Archived' : 'Active'}</p><p>Created: {formatDateTime12Hour(company.created_at)} · Updated: {formatDateTime12Hour(company.updated_at)}</p><p>Logo: {company.logo_path || 'Not uploaded'}</p></div>}
    {editable && <div className="flex flex-wrap gap-2"><button type="submit" disabled={busy} className="px-4 py-2 rounded-lg bg-blue-600 text-white disabled:opacity-50">{save.isPending ? 'Saving…' : isNew ? 'Create Company' : 'Save Company'}</button>{!isNew && <button type="button" disabled={busy} className={`${buttonClass} text-red-700`} onClick={() => { if (window.confirm(`Archive ${company.legal_name}? Its records, PDFs, and audit history will be retained as read-only.`)) archive.mutate() }}>Archive Company</button>}</div>}
    {isNew && <p className="text-xs text-gray-500">Create the company first, then upload its logo.</p>}
    {!isNew && editable && <fieldset disabled={busy} className="border rounded-xl p-4 space-y-2"><label className="block text-sm font-medium">Company logo<input type="file" accept="image/png,image/jpeg" className="block mt-2 text-sm" onChange={e => setLogoFile(e.target.files?.[0] || null)} /></label><button type="button" className={buttonClass} disabled={!logoFile || busy} onClick={() => logo.mutate()}>{logo.isPending ? 'Uploading…' : 'Upload Logo'}</button></fieldset>}
    {(save.error || archive.error || logo.error) && <p role="alert" className="text-red-700 text-sm">{complianceError(save.error || archive.error || logo.error)}</p>}
    {notice && <p role="status" className="text-green-700 text-sm">{notice}</p>}
    {!isNew && <button type="button" className={buttonClass} onClick={() => onSelect(company.id)}>Open company compliance matrix</button>}
  </form>
}

export function ComplianceAudit({ companyId, state }) {
  const query = useQuery({ queryKey: ['compliance-audit', companyId, state], queryFn: () => api.get(`/api/compliance/companies/${companyId}/audit`, { params: { state } }).then(r => r.data) })
  if (query.isLoading) return <p className="text-gray-500">Loading audit history…</p>
  if (query.isError) return <p role="alert" className="text-red-700">{complianceError(query.error)}</p>
  const events = query.data?.events || []
  return <section className="space-y-3"><h3 className="font-semibold">{state} — Audit History</h3>{events.length === 0 ? <p className="text-gray-500 text-sm">No recorded changes.</p> : <div className="overflow-x-auto"><table className="w-full text-sm"><thead><tr className="text-left border-b"><th className="p-2">When / Who</th><th className="p-2">Field</th><th className="p-2">Previous value</th><th className="p-2">New value</th></tr></thead><tbody>{events.map(event => <tr className="border-b align-top" key={event.id}><td className="p-2 whitespace-nowrap">{formatDateTime12Hour(event.created_at)}<span className="block text-gray-500">{event.user_name || 'Unknown user'}</span></td><td className="p-2">{event.field}</td><td className="p-2 break-words max-w-xs">{typeof event.old_value === 'object' ? JSON.stringify(event.old_value) : String(event.old_value ?? '—')}</td><td className="p-2 break-words max-w-xs">{typeof event.new_value === 'object' ? JSON.stringify(event.new_value) : String(event.new_value ?? '—')}</td></tr>)}</tbody></table></div>}</section>
}
