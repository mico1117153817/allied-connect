import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import { logout } from '../lib/auth'

const errorText = (err) => {
  const detail = err.response?.data?.detail
  if (typeof detail === 'string') return detail
  return err.message || 'Request failed'
}

export default function ManageDocuments() {
  const qc = useQueryClient()
  const [showUpload, setShowUpload] = useState(false)
  const [uploadForm, setUploadForm] = useState({ title: '', version: '1.0', requires_signature: true, file: null })
  const [selectedIds, setSelectedIds] = useState([])
  const [templateName, setTemplateName] = useState('')
  const [uploadMsg, setUploadMsg] = useState('')
  const [sigViewDoc, setSigViewDoc] = useState(null)
  const [busy, setBusy] = useState(false)

  const { data, isLoading } = useQuery({ queryKey: ['all-docs'], queryFn: () => api.get('/api/documents/all/list').then(r => r.data) })
  const { data: employeesData } = useQuery({ queryKey: ['manager-employees'], queryFn: () => api.get('/api/manager/employees').then(r => r.data) })
  const { data: templatesData } = useQuery({ queryKey: ['recipient-templates'], queryFn: () => api.get('/api/documents/templates').then(r => r.data) })
  const { data: sigData, isLoading: sigLoading } = useQuery({
    queryKey: ['signatures', sigViewDoc], queryFn: () => api.get(`/api/documents/${sigViewDoc}/signatures`).then(r => r.data), enabled: !!sigViewDoc,
  })

  const employees = employeesData?.employees || []
  const templates = templatesData?.templates || []
  const toggleEmployee = (id) => setSelectedIds(current => current.includes(id) ? current.filter(item => item !== id) : [...current, id])

  const saveTemplate = async () => {
    if (!templateName.trim() || selectedIds.length === 0) return setUploadMsg('Enter a template name and select employees first.')
    setBusy(true)
    try {
      await api.post('/api/documents/templates', { name: templateName, employee_ids: selectedIds })
      setTemplateName('')
      setUploadMsg('Recipient template saved.')
      qc.invalidateQueries({ queryKey: ['recipient-templates'] })
    } catch (err) { setUploadMsg(`Template failed: ${errorText(err)}`) } finally { setBusy(false) }
  }

  const handleUpload = async (e) => {
    e.preventDefault()
    if (selectedIds.length === 0) return setUploadMsg('Select at least one employee.')
    setBusy(true); setUploadMsg('')
    const formData = new FormData()
    formData.append('title', uploadForm.title)
    formData.append('version', uploadForm.version)
    formData.append('requires_signature', uploadForm.requires_signature)
    formData.append('employee_ids', JSON.stringify(selectedIds))
    formData.append('file', uploadForm.file)
    try {
      const response = await api.post('/api/documents', formData, { headers: { 'Content-Type': 'multipart/form-data' } })
      setUploadMsg(`Document sent to ${response.data.recipient_count} employee(s).`)
      setShowUpload(false); setUploadForm({ title: '', version: '1.0', requires_signature: true, file: null }); setSelectedIds([])
      qc.invalidateQueries({ queryKey: ['all-docs'] })
    } catch (err) { setUploadMsg(`Upload failed: ${errorText(err)}`) } finally { setBusy(false) }
  }

  const voidDocument = async (doc) => {
    if (!window.confirm(`Void “${doc.title}”? Recipients will lose access and receive an email.`)) return
    try {
      await api.put(`/api/documents/${doc.id}/void`)
      setUploadMsg('Document voided and recipients notified.')
      qc.invalidateQueries({ queryKey: ['all-docs'] }); qc.invalidateQueries({ queryKey: ['signatures'] })
    } catch (err) { setUploadMsg(`Void failed: ${errorText(err)}`) }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white shadow-sm"><div className="max-w-6xl mx-auto px-4 py-4 flex justify-between items-center">
        <div className="flex items-center gap-3"><img src="/allied-logo.jpg" alt="Allied" className="h-10 w-auto rounded" /><h1 className="text-xl font-bold">Manage Documents</h1></div>
        <div className="flex items-center gap-4"><a href="/manager" className="text-sm text-blue-600 hover:underline">← Manager</a><button onClick={logout} className="text-sm text-red-600 hover:underline">Logout</button></div>
      </div></header>

      <div className="max-w-6xl mx-auto px-4 py-6">
        <button onClick={() => setShowUpload(!showUpload)} className="mb-4 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium">{showUpload ? 'Cancel' : '+ Send New Document'}</button>
        {uploadMsg && <p className={`mb-4 text-sm ${uploadMsg.includes('failed') || uploadMsg.includes('Select') || uploadMsg.includes('Enter') ? 'text-red-600' : 'text-green-700'}`}>{uploadMsg}</p>}

        {showUpload && (
          <form onSubmit={handleUpload} className="bg-white p-6 rounded-xl shadow-sm mb-6 space-y-5">
            <div className="grid md:grid-cols-2 gap-4">
              <div><label className="block text-sm font-medium mb-1">Title</label><input required value={uploadForm.title} onChange={e => setUploadForm({...uploadForm,title:e.target.value})} className="w-full px-3 py-2 border rounded-lg" placeholder="Updated Employee Handbook" /></div>
              <div><label className="block text-sm font-medium mb-1">Version</label><input value={uploadForm.version} onChange={e => setUploadForm({...uploadForm,version:e.target.value})} className="w-full px-3 py-2 border rounded-lg" /></div>
            </div>
            <div className="grid md:grid-cols-2 gap-4">
              <div><label className="block text-sm font-medium mb-1">Requires Signature</label><select value={String(uploadForm.requires_signature)} onChange={e => setUploadForm({...uploadForm,requires_signature:e.target.value==='true'})} className="w-full px-3 py-2 border rounded-lg"><option value="true">Yes — block portal until signed</option><option value="false">No — notification only</option></select></div>
              <div><label className="block text-sm font-medium mb-1">File</label><input type="file" required accept=".pdf,.docx,.doc,.txt" onChange={e => setUploadForm({...uploadForm,file:e.target.files[0]})} className="w-full px-3 py-2 border rounded-lg" /></div>
            </div>

            <section className="border rounded-xl p-4">
              <div className="flex flex-wrap justify-between gap-3 mb-3"><div><h3 className="font-semibold">Select Recipients</h3><p className="text-sm text-gray-500">{selectedIds.length} employee(s) selected</p></div><div className="flex gap-2"><button type="button" onClick={() => setSelectedIds(employees.map(e => e.timestation_id))} className="text-sm text-blue-600">Select all</button><button type="button" onClick={() => setSelectedIds([])} className="text-sm text-gray-600">Clear</button></div></div>
              <div className="mb-4"><label className="block text-sm font-medium mb-1">Load Recipient Template</label><select onChange={e => { const t=templates.find(x=>String(x.id)===e.target.value); if(t)setSelectedIds(t.employee_ids) }} className="w-full px-3 py-2 border rounded-lg"><option value="">Choose a saved template...</option>{templates.map(t=><option key={t.id} value={t.id}>{t.name} ({t.employee_ids.length})</option>)}</select></div>
              <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2 max-h-64 overflow-y-auto border rounded-lg p-3">
                {employees.map(emp => <label key={emp.timestation_id} className={`flex gap-2 p-2 rounded cursor-pointer ${selectedIds.includes(emp.timestation_id)?'bg-blue-50 border border-blue-300':'border border-gray-200'}`}><input type="checkbox" checked={selectedIds.includes(emp.timestation_id)} onChange={() => toggleEmployee(emp.timestation_id)} /><span><span className="block text-sm font-medium">{emp.name}</span><span className="text-xs text-gray-500">{emp.email || 'No email — in-app notice only'}</span></span></label>)}
              </div>
              <div className="flex gap-2 mt-4"><input value={templateName} onChange={e=>setTemplateName(e.target.value)} placeholder="Template name, e.g. Monthly handbook" className="flex-1 px-3 py-2 border rounded-lg" /><button type="button" disabled={busy} onClick={saveTemplate} className="px-4 py-2 bg-indigo-600 text-white rounded-lg disabled:opacity-50">Save Template</button></div>
            </section>
            <button type="submit" disabled={busy} className="px-6 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 font-medium">{busy?'Sending...':`Send to ${selectedIds.length} Employee(s)`}</button>
          </form>
        )}

        <div className="bg-white rounded-xl shadow-sm p-6"><h2 className="text-lg font-semibold mb-4">Document History</h2>
          {isLoading ? <p className="text-gray-500">Loading...</p> : <div className="space-y-3">{data?.documents?.map(doc => (
            <div key={doc.id} className="border rounded-lg p-4"><div className="flex flex-wrap justify-between items-start gap-3"><div><div className="flex items-center gap-2"><span className="font-medium">{doc.title}</span><span className="text-xs text-gray-400">v{doc.version}</span>{doc.is_voided && <span className="text-xs px-2 py-1 bg-red-100 text-red-700 rounded-full">VOIDED</span>}</div><p className="text-xs text-gray-500 mt-1">{doc.file_type?.toUpperCase()} · {new Date(doc.created_at).toLocaleDateString()} · {doc.recipient_count} recipient(s)</p></div><div className="flex gap-2"><button onClick={()=>setSigViewDoc(sigViewDoc===doc.id?null:doc.id)} className="px-3 py-1 border rounded text-sm">{sigViewDoc===doc.id?'Hide':'Signatures'}</button>{!doc.is_voided&&<button onClick={()=>voidDocument(doc)} className="px-3 py-1 bg-red-600 text-white rounded text-sm">Void</button>}</div></div>
              {sigViewDoc===doc.id&&<div className="mt-4 border-t pt-3">{sigLoading?<p>Loading...</p>:<div className="grid grid-cols-2 gap-4"><div><p className="text-sm font-medium text-green-700">Signed ({sigData?.total_signed||0})</p>{sigData?.signed?.map(s=><p key={s.employee_id} className="text-sm">{s.employee_name}</p>)}</div><div><p className="text-sm font-medium text-red-700">Not Signed ({sigData?.total_not_signed||0})</p>{sigData?.not_signed?.map(s=><p key={s.employee_id} className="text-sm">{s.employee_name}</p>)}</div></div>}</div>}
            </div>))}{data?.documents?.length===0&&<p className="text-gray-400 text-center py-4">No documents sent.</p>}</div>}
        </div>
      </div>
    </div>
  )
}
