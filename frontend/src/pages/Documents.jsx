import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import { logout, isManager } from '../lib/auth'

const apiError = (err) => typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'Unable to complete this action.'

export default function Documents() {
  const qc = useQueryClient()
  const [message, setMessage] = useState('')
  const [activeDoc, setActiveDoc] = useState(null)
  const [pdfUrl, setPdfUrl] = useState(null)
  const [acknowledged, setAcknowledged] = useState(false)
  const [loadingDoc, setLoadingDoc] = useState(false)

  const { data, isLoading } = useQuery({ queryKey: ['documents'], queryFn: () => api.get('/api/documents').then(r => r.data) })

  const refresh = () => Promise.all([
    qc.invalidateQueries({ queryKey: ['documents'] }),
    qc.invalidateQueries({ queryKey: ['document-requirements'] }),
  ])

  const closeViewer = () => {
    if (pdfUrl) URL.revokeObjectURL(pdfUrl)
    setActiveDoc(null); setPdfUrl(null); setAcknowledged(false); setMessage('')
  }

  const openDocument = async (doc) => {
    setMessage(''); setLoadingDoc(true)
    try {
      await api.post(`/api/documents/${doc.id}/review`)
      const response = await api.get(`/api/documents/${doc.id}/download`, { responseType: 'blob' })
      if (pdfUrl) URL.revokeObjectURL(pdfUrl)
      setPdfUrl(URL.createObjectURL(new Blob([response.data], { type: 'application/pdf' })))
      setActiveDoc({ ...doc, viewed: true })
      await refresh()
    } catch (err) { setMessage(apiError(err)) } finally { setLoadingDoc(false) }
  }

  const signDocument = async () => {
    if (!activeDoc || !acknowledged) return
    setLoadingDoc(true); setMessage('')
    try {
      await api.post(`/api/documents/${activeDoc.id}/sign`, { acknowledged: true })
      setMessage('Document signed successfully. You can view it any time from this page.')
      await refresh()
      setActiveDoc({ ...activeDoc, signed: true })
    } catch (err) { setMessage(apiError(err)) } finally { setLoadingDoc(false) }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white shadow-sm"><div className="max-w-5xl mx-auto px-4 py-4 flex justify-between items-center">
        <div className="flex items-center gap-3"><img src="/allied-logo.jpg" alt="Allied" className="h-10 w-auto rounded" /><h1 className="text-xl font-bold">Documents & Handbooks</h1></div>
        <div className="flex items-center gap-4"><a href={isManager() ? '/manager' : '/dashboard'} className="text-sm text-blue-600 hover:underline">← Back</a>{isManager() && <a href="/manage-documents" className="text-sm text-blue-600 hover:underline">Manage</a>}<button onClick={logout} className="text-sm text-red-600 hover:underline">Logout</button></div>
      </div></header>

      <div className="max-w-5xl mx-auto px-4 py-6">
        <div className="bg-white rounded-xl shadow-sm p-6"><h2 className="text-lg font-semibold">Your Documents</h2><p className="text-sm text-gray-500 mt-1 mb-4">Required documents must be reviewed, acknowledged, and signed before other portal features are available.</p>
          {isLoading ? <p className="text-gray-500">Loading...</p> : data?.documents?.length === 0 ? <p className="text-gray-400 text-center py-8">No documents assigned to you.</p> : <div className="space-y-3">{data.documents.map(doc => (
            <div key={doc.id} className={`p-4 border rounded-lg ${doc.requires_signature && !doc.signed ? 'border-amber-400 bg-amber-50' : 'border-gray-200'}`}>
              <div className="flex flex-wrap justify-between items-center gap-3"><div><div className="flex items-center gap-2"><span className="font-medium">{doc.title}</span><span className="text-xs text-gray-400">v{doc.version}</span>{!doc.viewed && <span className="text-xs px-2 py-1 bg-blue-100 text-blue-700 rounded-full">NEW</span>}</div><p className="text-sm text-gray-600 mt-1">{doc.requires_signature ? (doc.signed ? 'Signed and available to view' : 'Signature required') : 'Available to view'}</p>{doc.signed && <p className="text-xs text-green-700 mt-1">Signed {new Date(doc.signed_at).toLocaleDateString()}</p>}</div>
                <button onClick={() => openDocument(doc)} disabled={loadingDoc} className="px-3 py-2 bg-gray-700 text-white rounded text-sm disabled:opacity-50">{doc.signed ? 'View PDF' : doc.viewed ? 'Continue Review' : 'View PDF'}</button>
              </div>
            </div>))}</div>}
        </div>
      </div>

      {activeDoc && <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-3"><div className="bg-white w-full max-w-6xl h-[92vh] rounded-xl shadow-2xl flex flex-col"><div className="p-4 border-b flex justify-between items-center"><div><h2 className="font-semibold">{activeDoc.title}</h2><p className="text-xs text-gray-500">Scroll through the PDF, then acknowledge it before signing.</p></div><button onClick={closeViewer} className="text-gray-600 text-sm">Close</button></div>
        <div className="flex-1 min-h-0 bg-gray-100">{pdfUrl && <iframe title={activeDoc.title} src={pdfUrl} className="w-full h-full" />}</div>
        <div className="p-4 border-t bg-white"><p className="text-sm text-green-700 mb-2">{message}</p>{activeDoc.requires_signature && !activeDoc.signed ? <div className="flex flex-wrap items-center justify-between gap-3"><label className="flex gap-2 items-start text-sm"><input type="checkbox" checked={acknowledged} onChange={e => setAcknowledged(e.target.checked)} className="mt-1" /><span>I have read and acknowledge this document.</span></label><button onClick={signDocument} disabled={!acknowledged || loadingDoc} className="px-5 py-2 bg-blue-600 text-white rounded-lg disabled:opacity-40">{loadingDoc ? 'Signing...' : 'Acknowledge & Sign'}</button></div> : <p className="text-sm text-gray-600">This signed document remains available here for future viewing.</p>}</div>
      </div></div>}
    </div>
  )
}
