import React from 'react'
import CorporatePdfViewer from './CorporatePdfViewer'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import { complianceError } from '../lib/compliance'
import { formatDateTime12Hour } from '../lib/time'

export const CORPORATE_CATEGORIES = ['EIN', 'Articles of Incorporation', 'Operating Agreement', 'Bylaws', 'Certificate of Good Standing', 'Other Corporate Document']
const buttonClass = 'px-3 py-2 border rounded-lg text-sm hover:bg-blue-50 disabled:opacity-50'
export default function CorporateDocuments({ company }) {
  return company.id ? <CompanyDocuments key={`${company.id}:${company.can_edit}:${company.is_active}`} company={company} /> : null
}
function CompanyDocuments({ company }) {
  const qc = useQueryClient()
  const [viewing, setViewing] = React.useState(null)
  const downloads = React.useRef(new Map())
  React.useEffect(() => () => { downloads.current.forEach((timer, url) => { clearTimeout(timer); URL.revokeObjectURL(url) }); downloads.current.clear() }, [])
  const [editor, setEditor] = React.useState(null)
  const [file, setFile] = React.useState(null)
  const [notes, setNotes] = React.useState('')
  const [busy, setBusy] = React.useState(false)
  const [error, setError] = React.useState('')
  const [notice, setNotice] = React.useState('')
  const operation = React.useRef(null)
  const mounted = React.useRef(false)
  React.useEffect(() => { mounted.current = true; return () => { mounted.current = false; operation.current?.abort() } }, [])
  const companyId = company.id
  const prefix = `/api/compliance/companies/${companyId}/corporate-documents`
  const query = useQuery({ queryKey: ['corporate-documents', companyId], queryFn: ({ signal }) => api.get(prefix, { signal }).then(r => r.data) })
  const editable = company.can_edit === true && company.is_active !== false && query.data?.can_edit === true
  const edit = (category, doc = null) => { setEditor({ category, doc }); setFile(null); setNotes(''); setError(''); setNotice('') }
  const run = async task => {
    if (operation.current) return
    const controller = new AbortController()
    operation.current = controller
    setBusy(true); setError(''); setNotice('')
    try { await task(controller.signal) }
    catch (err) { if (mounted.current && !controller.signal.aborted) setError(complianceError(err)) }
    finally { if (mounted.current) { operation.current = null; setBusy(false) } }
  }
  const save = () => {
    if (!editable || !file || !editor) return
    if (editor.doc && !window.confirm(`Replace ${editor.doc.original_file_name}? The old PDF will remain in replaced history.`)) return
    const body = new FormData()
    body.append('file', file); body.append('notes', notes)
    if (!editor.doc) body.append('document_type', editor.category)
    const url = editor.doc ? `${prefix}/${editor.doc.id}/replace` : prefix
    run(async signal => {
      await api.post(url, body, { signal })
      await qc.invalidateQueries({ queryKey: ['corporate-documents', companyId] })
      if (mounted.current && !signal.aborted) { setEditor(null); setFile(null); setNotes(''); setNotice('PDF saved.') }
    })
  }
  const remove = doc => {
    if (!editable || operation.current || !window.confirm(`Delete ${doc.original_file_name}? This removes this document from the company.`)) return
    run(async signal => {
      await api.delete(`${prefix}/${doc.id}`, { signal })
      await qc.invalidateQueries({ queryKey: ['corporate-documents', companyId] })
      if (mounted.current && !signal.aborted) setNotice('PDF deleted.')
    })
  }
  const download = doc => run(async signal => {
    const response = await api.get(`${prefix}/${doc.id}/download`, { responseType: 'blob', signal })
    if (!mounted.current || signal.aborted) return
    const url = URL.createObjectURL(new Blob([response.data], { type: 'application/pdf' }))
    const timer = setTimeout(() => { URL.revokeObjectURL(url); downloads.current.delete(url) }, 60000)
    downloads.current.set(url, timer)
    const link = document.createElement('a')
    link.href = url; link.download = doc.original_file_name
    document.body.appendChild(link); link.click(); link.remove()
  })
  const row = doc => <li key={doc.id} className="border rounded-lg p-3 space-y-2">
    <p className="font-medium break-all">{doc.original_file_name}</p>
    <p className="text-xs text-gray-500">{formatDateTime12Hour(doc.uploaded_at)} · Uploaded by user {doc.uploaded_by_user_id ?? '—'} · {doc.status}</p>
    {doc.notes && <p className="text-sm whitespace-pre-wrap break-words">{doc.notes}</p>}
    <div className="flex flex-wrap gap-2"><button type="button" disabled={busy} className={buttonClass} onClick={() => setViewing(doc)}>View PDF</button><button type="button" disabled={busy} className={buttonClass} onClick={() => download(doc)}>Download</button>
      {editable && <>{doc.status === 'active' && <button type="button" disabled={busy} className={buttonClass} onClick={() => edit(doc.document_type, doc)}>Replace</button>}<button type="button" disabled={busy} className={buttonClass} onClick={() => remove(doc)}>Delete</button></>}
    </div>
  </li>
  return <section aria-label="Corporate Documents" className="border-t pt-5 space-y-4">
    <h3 className="text-lg font-semibold">Corporate Documents</h3>
    {viewing && <CorporatePdfViewer key={viewing.id} companyId={companyId} document={viewing} onClose={() => setViewing(null)} />}
    {error && <p role="alert" className="text-red-700">{error}</p>}
    {notice && <p role="status" className="text-green-700">{notice}</p>}
    {busy && <p role="status">Working…</p>}
    {editor && editable && <fieldset disabled={busy} className="p-4 border rounded-xl space-y-3">
      <legend>{editor.doc ? 'Replace' : 'Upload'} — {editor.category}</legend>
      <label className="block text-sm">PDF file<input aria-label="Corporate PDF file" type="file" accept="application/pdf,.pdf" className="block mt-2 max-w-full" onChange={e => setFile(e.target.files?.[0] || null)} /></label>
      <label className="block text-sm">Notes (optional)<textarea aria-label="Corporate PDF notes" value={notes} onChange={e => setNotes(e.target.value)} className="block border rounded-lg p-2 w-full" /></label>
      <div className="flex gap-2"><button type="button" disabled={busy || !file} className={buttonClass} onClick={save}>Save PDF</button><button type="button" disabled={busy} className={buttonClass} onClick={() => { setEditor(null); setFile(null); setNotes('') }}>Cancel upload</button></div>
    </fieldset>}
    {query.isLoading && <p role="status">Loading corporate documents…</p>}
    {query.isError && <p role="alert">{complianceError(query.error)}</p>}
    {query.isSuccess && CORPORATE_CATEGORIES.map(category => {
      const documents = (query.data.documents || []).filter(doc => doc.document_type === category)
      const active = documents.filter(doc => doc.status === 'active')
      const history = documents.filter(doc => doc.status === 'replaced')
      return <section key={category} aria-label={category} className="border rounded-xl p-4 space-y-3">
        <div className="flex flex-wrap justify-between gap-2"><h4 className="font-semibold">{category}</h4><span className={active.length ? 'text-green-700 text-sm' : 'text-gray-500 text-sm'}>{active.length ? 'Uploaded' : 'Not uploaded'}</span></div>
        {editable && <button type="button" disabled={busy} className={buttonClass} onClick={() => edit(category)}>Upload PDF</button>}
        <ul className="space-y-2">{active.map(row)}</ul>
        {history.length > 0 && <details><summary className="cursor-pointer text-sm">Replaced history ({history.length})</summary><ul className="space-y-2 mt-2">{history.map(row)}</ul></details>}
      </section>
    })}
  </section>
}
