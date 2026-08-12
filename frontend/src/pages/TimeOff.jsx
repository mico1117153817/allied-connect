import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { api } from '../lib/api'
import { logout, getEmployee, isManager } from '../lib/auth'

export default function TimeOff() {
  const employee = getEmployee()
  const qc = useQueryClient()
  const [searchParams] = useSearchParams()
  const selectedEmployeeId = isManager() ? (searchParams.get('employee') || '') : ''
  const viewingEmployee = !!selectedEmployeeId
  const [showForm, setShowForm] = useState(false)
  const [formData, setFormData] = useState({
    request_type: 'vacation',
    start_date: '',
    end_date: '',
    reason: '',
    hour_type: null,
    hours_requested: null,
    pay_period_id: null,
  })
  const [error, setError] = useState('')

  const { data: selectedEmployee } = useQuery({
    queryKey: ['employee-view-selected', selectedEmployeeId],
    queryFn: () => api.get('/api/manager/employees').then(r => r.data.employees.find(item => item.timestation_id === selectedEmployeeId)),
    enabled: viewingEmployee,
  })

  const { data, isLoading } = useQuery({
    queryKey: ['time-off-history', selectedEmployeeId || 'self'],
    queryFn: () => viewingEmployee
      ? api.get(`/api/manager/employee/${selectedEmployeeId}/time-off`).then(r => r.data)
      : api.get('/api/time-off/').then(r => {
          const d = r.data
          return Array.isArray(d) ? { requests: d } : d
        }),
  })

  const { data: ppList } = useQuery({
    queryKey: ['pay-periods', viewingEmployee ? 'management' : 'self'],
    queryFn: () => api.get(viewingEmployee ? '/api/manager/pay-periods' : '/api/me/pay-periods').then(r => r.data),
  })

  const createMutation = useMutation({
    mutationFn: (requestData) => viewingEmployee
      ? api.post(`/api/manager/employee/${selectedEmployeeId}/time-off`, requestData)
      : api.post('/api/time-off/', requestData),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['time-off-history', selectedEmployeeId || 'self'] })
      setShowForm(false)
      setFormData({ request_type: 'vacation', start_date: '', end_date: '', reason: '', hour_type: null, hours_requested: null, pay_period_id: null })
    },
    onError: (err) => setError(err.response?.data?.detail || 'Failed to submit request'),
  })

  const handleSubmit = (e) => {
    e.preventDefault()
    setError('')
    if (formData.request_type !== 'back_hours') {
      if (!formData.start_date || !formData.end_date) {
        setError('Start date and end date are required')
        return
      }
      if (formData.end_date < formData.start_date) {
        setError('End date must be after start date')
        return
      }
    }
    if (formData.hour_type && !formData.pay_period_id) {
      setError('Please select a pay period when using hours')
      return
    }
    createMutation.mutate(formData)
  }

  const statusColor = (status) => ({
    pending: 'bg-yellow-100 text-yellow-800',
    approved: 'bg-green-100 text-green-800',
    denied: 'bg-red-100 text-red-800',
    voided: 'bg-orange-100 text-orange-800',
  }[status] || 'bg-gray-100 text-gray-800')

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white shadow-sm">
        <div className="max-w-4xl mx-auto px-4 py-4 flex justify-between items-center">
          <div className="flex items-center gap-3">
            <img src="/allied-logo.jpg" alt="Allied" className="h-10 w-auto rounded" />
            <h1 className="text-xl font-bold">Time Off Requests</h1>
          </div>
          <div className="flex items-center gap-4">
            <a href={viewingEmployee ? `/dashboard?employee=${selectedEmployeeId}` : '/dashboard'} className="text-sm text-blue-600 hover:underline">← Dashboard</a>
            <button onClick={logout} className="text-sm text-red-600 hover:underline">Logout</button>
          </div>
        </div>
      </header>

      <div className="max-w-4xl mx-auto px-4 py-6">
        {viewingEmployee && (
          <div className="mb-4 bg-blue-50 border border-blue-200 rounded-lg p-3 text-sm text-blue-800">
            Submitting and viewing requests as <span className="font-semibold">{selectedEmployee?.name || selectedEmployeeId}</span>. Requests still enter the normal approval process.
          </div>
        )}
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
                onChange={(e) => {
                  const newType = e.target.value
                  if (newType === 'back_hours') {
                    setFormData({ ...formData, request_type: newType, hour_type: 'back_hours', start_date: '', end_date: '' })
                  } else {
                    setFormData({ ...formData, request_type: newType })
                  }
                }}
                className="w-full px-3 py-2 border rounded-lg"
              >
                <option value="vacation">Vacation</option>
                <option value="sick">Sick</option>
                <option value="personal">Personal</option>
                <option value="unpaid">Unpaid</option>
                <option value="back_hours">Back Hours</option>
              </select>
            </div>

            {/* Hour usage selector */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Use Hours From (optional)</label>
              <select
                value={formData.hour_type || ''}
                onChange={(e) => setFormData({ ...formData, hour_type: e.target.value || null, hours_requested: e.target.value ? formData.hours_requested : null })}
                className="w-full px-3 py-2 border rounded-lg"
              >
                <option value="">No — unpaid time off</option>
                <option value="vacation_hours">Use Vacation Hours</option>
                <option value="back_hours">Use Back Hours</option>
                <option value="sick_hours">Use Sick Hours</option>
              </select>
            </div>

            {formData.hour_type && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Hours to Use</label>
                <input
                  type="number"
                  step="0.25"
                  min="0.25"
                  value={formData.hours_requested || ''}
                  onChange={(e) => setFormData({ ...formData, hours_requested: parseFloat(e.target.value) })}
                  className="w-full px-3 py-2 border rounded-lg"
                  placeholder="8"
                />
              </div>
            )}

            {formData.hour_type && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Pay Period to Apply To *</label>
                <select
                  value={formData.pay_period_id || ''}
                  onChange={(e) => setFormData({ ...formData, pay_period_id: e.target.value ? parseInt(e.target.value) : null })}
                  className="w-full px-3 py-2 border rounded-lg"
                >
                  <option value="">Select a pay period...</option>
                  {ppList?.pay_periods?.map(pp => (
                    <option key={pp.id} value={pp.id}>
                      {pp.label} — {pp.start_date} → {pp.end_date}
                    </option>
                  ))}
                </select>
              </div>
            )}
            <div className="grid grid-cols-2 gap-4">
              {formData.request_type !== 'back_hours' && (
                <>
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
                </>
              )}
            </div>
            {formData.request_type === 'back_hours' && (
              <div className="bg-blue-50 p-3 rounded-lg text-sm text-blue-700">
                Back hours requests don't require dates — just enter the hours and select a pay period below.
              </div>
            )}
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
                      <span className="font-medium capitalize">{(r.request_type || r.type || '').replace('_', ' ')}</span>
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
