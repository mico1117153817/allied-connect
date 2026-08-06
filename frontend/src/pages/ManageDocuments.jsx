import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import { logout } from '../lib/auth'

export default function ManageDocuments() {
  const qc = useQueryClient()
  const [showUpload, setShowUpload] = useState(false)
  const [uploadForm, setUploadForm] = useState({ title: '', version: '1.0', requires_signature: true, file: null })
  const [uploadMsg, setUploadMsg] = useState('')
  const [sigViewDoc, setSigViewDoc] = useState(null)

  const { data, isLoading } = useQuery({
    queryKey: ['all-docs'],
    queryFn: () => api.get('/api/documents/all/list').then(r => r.data),
  })

  const { data: sigData, isLoading: sigLoading } = useQuery({
    queryKey: ['signatures', sigViewDoc],
    queryFn: () => api.get(`/api/documents/${sigViewDoc}/signatures`).then(r => r.data),
    enabled: !!sigViewDoc,
  })

  const handleUpload = async (e) => {
    e.preventDefault()
    setUploadMsg('')
    const formData = new FormData()
    formData.append('title', uploadForm.title)
    formData.append('version', uploadForm.version)
    formData.append('requires_signature', uploadForm.requires_signature)
    formData.append('file', uploadForm.file)

    try {
      await api.post('/api/documents', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setUploadMsg('Document uploaded successfully!')
      setShowUpload(false)
      setUploadForm({ title: '', version: '1.0', requires_signature: true, file: null })
      qc.invalidateQueries({ queryKey: ['all-docs'] })
    } catch (err) {
      setUploadMsg(`Upload failed: ${err.response?.data?.detail || err.message}`)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white shadow-sm">
        <div className="max-w-4xl mx-auto px-4 py-4 flex justify-between items-center">
          <div className="flex items-center gap-3">
            <img src="/allied-logo.jpg" alt="Allied" className="h-10 w-auto rounded" />
            <h1 className="text-xl font-bold">Manage Documents</h1>
          </div>
          <div className="flex items-center gap-4">
            <a href="/manager" className="text-sm text-blue-600 hover:underline">← Manager</a>
            <button onClick={logout} className="text-sm text-red-600 hover:underline">Logout</button>
          </div>
        </div>
      </header>

      <div className="max-w-4xl mx-auto px-4 py-6">
        <button
          onClick={() => setShowUpload(!showUpload)}
          className="mb-4 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium"
        >
          {showUpload ? 'Cancel' : '+ Upload New Document'}
        </button>

        {showUpload && (
          <form onSubmit={handleUpload} className="bg-white p-6 rounded-xl shadow-sm mb-6 space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1">Title</label>
              <input
                type="text"
                required
                value={uploadForm.title}
                onChange={(e) => setUploadForm({ ...uploadForm, title: e.target.value })}
                className="w-full px-3 py-2 border rounded-lg"
                placeholder="Employee Handbook 2025"
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium mb-1">Version</label>
                <input
                  type="text"
                  value={uploadForm.version}
                  onChange={(e) => setUploadForm({ ...uploadForm, version: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Requires Signature</label>
                <select
                  value={uploadForm.requires_signature}
                  onChange={(e) => setUploadForm({ ...uploadForm, requires_signature: e.target.value === 'true' })}
                  className="w-full px-3 py-2 border rounded-lg"
                >
                  <option value="true">Yes</option>
                  <option value="false">No</option>
                </select>
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">File (PDF, DOCX)</label>
              <input
                type="file"
                required
                onChange={(e) => setUploadForm({ ...uploadForm, file: e.target.files[0] })}
                className="w-full px-3 py-2 border rounded-lg"
                accept=".pdf,.docx,.doc,.txt"
              />
            </div>
            {uploadMsg && <p className={`text-sm ${uploadMsg.includes('success') ? 'text-green-600' : 'text-red-500'}`}>{uploadMsg}</p>}
            <button type="submit" className="px-6 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 font-medium">
              Upload
            </button>
          </form>
        )}

        <div className="bg-white rounded-xl shadow-sm p-6">
          <h2 className="text-lg font-semibold mb-4">All Documents</h2>
          {isLoading ? <p className="text-gray-500">Loading...</p> : (
            <div className="space-y-3">
              {data?.documents?.map(doc => (
                <div key={doc.id} className="border rounded-lg p-4">
                  <div className="flex justify-between items-start">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-medium">{doc.title}</span>
                        <span className="text-xs text-gray-400">v{doc.version}</span>
                        {!doc.is_active && <span className="text-xs text-red-500">INACTIVE</span>}
                      </div>
                      <p className="text-xs text-gray-500 mt-1">{doc.file_type?.toUpperCase()} · {new Date(doc.created_at).toLocaleDateString()}</p>
                    </div>
                    <button
                      onClick={() => setSigViewDoc(sigViewDoc === doc.id ? null : doc.id)}
                      className="px-3 py-1 border rounded text-sm hover:bg-gray-50"
                    >
                      {sigViewDoc === doc.id ? 'Hide' : 'Signatures'}
                    </button>
                  </div>
                  {sigViewDoc === doc.id && (
                    <div className="mt-4 border-t pt-3">
                      {sigLoading ? <p className="text-sm text-gray-500">Loading signatures...</p> : (
                        <>
                          <div className="grid grid-cols-2 gap-4">
                            <div>
                              <p className="text-sm font-medium text-green-700 mb-1">Signed ({sigData?.total_signed || 0})</p>
                              <div className="space-y-1 max-h-40 overflow-y-auto">
                                {sigData?.signed?.map((s, i) => (
                                  <div key={i} className="text-sm text-gray-600">
                                    {s.employee_name} <span className="text-xs text-gray-400">{new Date(s.signed_at).toLocaleDateString()}</span>
                                  </div>
                                ))}
                                {sigData?.signed?.length === 0 && <p className="text-sm text-gray-400">No signatures yet.</p>}
                              </div>
                            </div>
                            <div>
                              <p className="text-sm font-medium text-red-700 mb-1">Not Signed ({sigData?.total_not_signed || 0})</p>
                              <div className="space-y-1 max-h-40 overflow-y-auto">
                                {sigData?.not_signed?.map((s, i) => (
                                  <div key={i} className="text-sm text-gray-600">{s.employee_name}</div>
                                ))}
                                {sigData?.not_signed?.length === 0 && <p className="text-sm text-gray-400">All signed!</p>}
                              </div>
                            </div>
                          </div>
                        </>
                      )}
                    </div>
                  )}
                </div>
              ))}
              {data?.documents?.length === 0 && <p className="text-gray-400 text-center py-4">No documents uploaded.</p>}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
