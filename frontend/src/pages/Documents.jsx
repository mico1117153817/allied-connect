import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import { logout, isManager } from '../lib/auth'

export default function Documents() {
  const qc = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['documents'],
    queryFn: () => api.get('/api/documents').then(r => r.data),
  })

  const signMutation = useMutation({
    mutationFn: (docId) => api.post(`/api/documents/${docId}/sign`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['documents'] }),
  })

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white shadow-sm">
        <div className="max-w-4xl mx-auto px-4 py-4 flex justify-between items-center">
          <div className="flex items-center gap-3">
            <img src="/allied-logo.jpg" alt="Allied" className="h-10 w-auto rounded" />
            <h1 className="text-xl font-bold">Documents & Handbooks</h1>
          </div>
          <div className="flex items-center gap-4">
            <a href="/dashboard" className="text-sm text-blue-600 hover:underline">← Dashboard</a>
            {isManager() && <a href="/manage-documents" className="text-sm text-blue-600 hover:underline">Manage</a>}
            <button onClick={logout} className="text-sm text-red-600 hover:underline">Logout</button>
          </div>
        </div>
      </header>

      <div className="max-w-4xl mx-auto px-4 py-6">
        <div className="bg-white rounded-xl shadow-sm p-6">
          <h2 className="text-lg font-semibold mb-4">Active Documents</h2>
          {isLoading ? (
            <p className="text-gray-500">Loading...</p>
          ) : data?.documents?.length === 0 ? (
            <p className="text-gray-400 text-center py-8">No documents available.</p>
          ) : (
            <div className="space-y-3">
              {data?.documents?.map(doc => (
                <div key={doc.id} className="flex justify-between items-center p-4 border rounded-lg">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{doc.title}</span>
                      <span className="text-xs text-gray-400">v{doc.version}</span>
                      <span className="text-xs text-gray-400 uppercase">{doc.file_type}</span>
                    </div>
                    <p className="text-sm text-gray-500 mt-1">
                      {doc.requires_signature ? 'Signature required' : 'No signature required'}
                    </p>
                    {doc.signed && (
                      <p className="text-xs text-green-600 mt-1">✓ Signed on {new Date(doc.signed_at).toLocaleDateString()}</p>
                    )}
                  </div>
                  <div className="flex gap-2">
                    <a
                      href={`${import.meta.env.VITE_API_URL || ''}/api/documents/${doc.id}/download`}
                      onClick={(e) => {
                        e.preventDefault()
                        const token = localStorage.getItem('token')
                        fetch(`${import.meta.env.VITE_API_URL || ''}/api/documents/${doc.id}/download`, {
                          headers: { Authorization: `Bearer ${token}` },
                        })
                          .then(r => r.blob())
                          .then(b => {
                            const url = URL.createObjectURL(b)
                            const a = document.createElement('a')
                            a.href = url
                            a.download = doc.title
                            a.click()
                            URL.revokeObjectURL(url)
                          })
                      }}
                      className="px-3 py-1 bg-gray-600 text-white rounded text-sm hover:bg-gray-700"
                    >
                      Download
                    </a>
                    {doc.requires_signature && !doc.signed && (
                      <button
                        onClick={() => signMutation.mutate(doc.id)}
                        disabled={signMutation.isPending}
                        className="px-3 py-1 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 disabled:opacity-50"
                      >
                        Sign
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
