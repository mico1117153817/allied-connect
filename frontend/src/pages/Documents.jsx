import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import { logout, isManager } from '../lib/auth'

export default function Documents() {
  const qc = useQueryClient()
  const [message, setMessage] = useState('')
  const { data, isLoading } = useQuery({ queryKey: ['documents'], queryFn: () => api.get('/api/documents').then(r => r.data) })

  const downloadAndReview = async (doc) => {
    setMessage('')
    try {
      await api.post(`/api/documents/${doc.id}/review`)
      const response = await api.get(`/api/documents/${doc.id}/download`, { responseType: 'blob' })
      const url = URL.createObjectURL(response.data)
      const a = document.createElement('a'); a.href = url; a.download = doc.title; a.click(); URL.revokeObjectURL(url)
      await Promise.all([
        qc.invalidateQueries({ queryKey: ['documents'] }),
        qc.invalidateQueries({ queryKey: ['document-requirements'] }),
      ])
    } catch (err) { setMessage(err.response?.data?.detail || 'Unable to open document') }
  }

  const signDocument = async (doc) => {
    setMessage('')
    try {
      await api.post(`/api/documents/${doc.id}/sign`)
      await Promise.all([
        qc.invalidateQueries({ queryKey: ['documents'] }),
        qc.invalidateQueries({ queryKey: ['document-requirements'] }),
      ])
      setMessage(`${doc.title} signed successfully.`)
    } catch (err) { setMessage(err.response?.data?.detail || 'Unable to sign document') }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white shadow-sm"><div className="max-w-4xl mx-auto px-4 py-4 flex justify-between items-center">
        <div className="flex items-center gap-3"><img src="/allied-logo.jpg" alt="Allied" className="h-10 w-auto rounded" /><h1 className="text-xl font-bold">Documents & Handbooks</h1></div>
        <div className="flex items-center gap-4"><a href={isManager()?'/manager':'/dashboard'} className="text-sm text-blue-600 hover:underline">← Back</a>{isManager()&&<a href="/manage-documents" className="text-sm text-blue-600 hover:underline">Manage</a>}<button onClick={logout} className="text-sm text-red-600 hover:underline">Logout</button></div>
      </div></header>
      <div className="max-w-4xl mx-auto px-4 py-6">
        {message&&<p className="mb-4 p-3 bg-blue-50 text-blue-800 rounded-lg text-sm">{message}</p>}
        <div className="bg-white rounded-xl shadow-sm p-6"><h2 className="text-lg font-semibold mb-1">Your Documents</h2><p className="text-sm text-gray-500 mb-4">Review each required document before signing it.</p>
          {isLoading?<p className="text-gray-500">Loading...</p>:data?.documents?.length===0?<p className="text-gray-400 text-center py-8">No documents assigned to you.</p>:<div className="space-y-3">{data.documents.map(doc=>(
            <div key={doc.id} className={`p-4 border rounded-lg ${doc.requires_signature&&!doc.signed?'border-amber-400 bg-amber-50':'border-gray-200'}`}>
              <div className="flex flex-wrap justify-between items-center gap-3"><div><div className="flex items-center gap-2"><span className="font-medium">{doc.title}</span><span className="text-xs text-gray-400">v{doc.version}</span><span className="text-xs text-gray-400 uppercase">{doc.file_type}</span>{!doc.viewed&&<span className="text-xs px-2 py-1 bg-blue-100 text-blue-700 rounded-full">NEW</span>}</div><p className="text-sm text-gray-600 mt-1">{doc.requires_signature?(doc.signed?'Signature complete':'Signature required — portal access is limited until signed'):'Review requested'}</p>{doc.signed&&<p className="text-xs text-green-700 mt-1">✓ Signed {new Date(doc.signed_at).toLocaleDateString()}</p>}</div>
                <div className="flex gap-2"><button onClick={()=>downloadAndReview(doc)} className="px-3 py-2 bg-gray-700 text-white rounded text-sm">{doc.viewed?'Download Again':'Review & Download'}</button>{doc.requires_signature&&!doc.signed&&<button onClick={()=>signDocument(doc)} disabled={!doc.viewed} title={!doc.viewed?'Review the document first':''} className="px-3 py-2 bg-blue-600 text-white rounded text-sm disabled:opacity-40">Sign</button>}</div>
              </div>
            </div>))}</div>}
        </div>
      </div>
    </div>
  )
}
