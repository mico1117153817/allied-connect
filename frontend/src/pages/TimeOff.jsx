import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import { logout, getEmployee, isManager } from '../lib/auth'

export default function TimeOff() {
  const employee = getEmployee()
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [formData, setFormData] = useState({
    request_type: 'vacation',
    start_date: '',
    end_date: '',
    reason: '',
  })
  const [error, setError] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['my-time-off'],
    queryFn: () => api.get('/api/time-off').then(r => r.data),
  })

  const createMutation = useMutation({
    mutationFn: (data) => api.post('/api/time-off', data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['my-time-off'] })
      setShowForm(false)
      setFormData({ request_type: 'vacation', start_date: '', end_date: '', reason: '' })
    },
    onError: (err) => setError(err.response?.data?.detail || 'Failed to submit request'),
  })

  const handleSubmit = (e) => {
    e.preventDefault()
    setError('')
    if (formData.end_date < formData.start_date) {
      setError('End date must be after start date')
      return
    }
    createMutation.mutate(formData)
  }

  const statusColor = (status) => ({
    pending: 'bg-yellow-100 text-yellow-800',
    approved: 'bg-green-100 text-green-800',
    denied: 'bg-red-100 text-red-800',
  }[status] || 'bg-gray-100 text-gray-800')

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white shadow-sm">
        <div className="max-w-4xl mx-auto px-4 py-4 flex justify-between items-center">
          <h1 className="text-xl font-bold">Time Off Requests</h1>
          <div className="flex items-center gap-4">
            <a href="/dashboard" className="text-sm text-blue-600 hover:underline">← Dashboard</a>
            <button onClick={logout} className="text-sm text-red-600 hover:underline">Logout</button>
          </div>
        </div>
      </header>

      <div className="max-w-4xl mx-auto px-4 py-6">
        <button
          onClick={() => setShowForm(!showForm)}
          className="mb-4 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium"
        >
          {showForm ? 'Cancel' : '+ New Time Off Request'}
        </button>

        {showForm && (
          <form onSubmit={handleSubmit} className="bg-white p-6 rounded-xl shadow-sm mb-6 space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Type</label>
              <select
                value={formData.request_type}
                onChange={(e) => setFormData({ ...formData, request_type: e.target.value })}
                className="w-full px-3 py-2 border rounded-lg"
              >
                <option value="vacation">Vacation</option>
                <option value="sick">Sick</option>
                <option value="personal">Personal</option>
                <option value="unpaid">Unpaid</option>
              </select>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Start Date</label>
                <input
                  type="date"
                  required
                  value={formData.start_date}
                  onChange={(e) => setFormData({ ...formData, start_date: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">End Date</label>
                <input
                  type="date"
                  required
                  value={formData.end_date}
                  onChange={(e) => setFormData({ ...formData, end_date: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg"
                />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Reason (optional)</label>
              <textarea
                value={formData.reason}
                onChange={(e) => setFormData({ ...formData, reason: e.target.value })}
                className="w-full px-3 py-2 border rounded-lg"
                rows="2"
              />
            </div>
            {error && <p className="text-red-500 text-sm">{error}</p>}
            <button
              type="submit"
              disabled={createMutation.isPending}
              className="px-6 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 font-medium"
            >
              {createMutation.isPending ? 'Submitting...' : 'Submit Request'}
            </button>
          </form>
        )}

        <div className="bg-white rounded-xl shadow-sm p-6">
          <h2 className="text-lg font-semibold mb-4">Your Requests</h2>
          {isLoading ? (
            <p className="text-gray-500">Loading...</p>
          ) : data?.requests?.length === 0 ? (
            <p className="text-gray-500 text-center py-4">No time-off requests yet.</p>
          ) : (
            <div className="space-y-3">
              {data?.requests?.map(r => (
                <div key={r.id} className="flex justify-between items-center p-4 border rounded-lg">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-medium capitalize">{r.type}</span>
                      <span className={`text-xs px-2 py-1 rounded-full font-medium ${statusColor(r.status)}`}>
                        {r.status}
                      </span>
                    </div>
                    <p className="text-sm text-gray-600 mt-1">
                      {r.start_date} → {r.end_date}
                      {r.reason && ` · ${r.reason}`}
                    </p>
                    {r.reviewed_at && <p className="text-xs text-gray-400 mt-1">Reviewed: {new Date(r.reviewed_at).toLocaleDateString()}</p>}
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
