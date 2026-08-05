import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import { logout } from '../lib/auth'

export default function Manager() {
  const qc = useQueryClient()
  const [tab, setTab] = useState('today')
  const [payDate, setPayDate] = useState(new Date().toISOString().slice(0, 10))
  const [adjForm, setAdjForm] = useState({ employee_id: '', pay_date: '', type: 'back_hours', hours: 0, description: '' })

  // Today's status
  const { data: todayData, isLoading: todayLoading } = useQuery({
    queryKey: ['today'],
    queryFn: () => api.get('/api/manager/today').then(r => r.data),
    refetchInterval: 120_000,
  })

  // All employees
  const { data: empData } = useQuery({
    queryKey: ['all-employees'],
    queryFn: () => api.get('/api/manager/employees').then(r => r.data),
  })

  // Time off requests
  const { data: timeOffData, isLoading: timeOffLoading } = useQuery({
    queryKey: ['all-time-off'],
    queryFn: () => api.get('/api/time-off/all?status=all').then(r => {
      const d = r.data
      return Array.isArray(d) ? { requests: d } : d
    }),
  })

  // Pay adjustments
  const { data: payData, isLoading: payLoading } = useQuery({
    queryKey: ['pay-adjustments', payDate],
    queryFn: () => api.get('/api/manager/pay-adjustments', { params: { pay_date: payDate } }).then(r => r.data),
  })

  const reviewMutation = useMutation({
    mutationFn: ({ id, status }) => api.put(`/api/time-off/${id}/review`, { status }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['all-time-off'] }),
  })

  const adjMutation = useMutation({
    mutationFn: (data) => api.post('/api/manager/pay-adjustment', data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['pay-adjustments', payDate] })
      setAdjForm({ employee_id: '', pay_date: payDate, type: 'back_hours', hours: 0, description: '' })
    },
  })

  const statusColor = (status) => ({
    pending: 'bg-yellow-100 text-yellow-800',
    approved: 'bg-green-100 text-green-800',
    denied: 'bg-red-100 text-red-800',
  }[status] || 'bg-gray-100')

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white shadow-sm">
        <div className="max-w-7xl mx-auto px-4 py-4 flex justify-between items-center">
          <h1 className="text-xl font-bold">Allied Connect — Manager</h1>
          <div className="flex items-center gap-4">
            <a href="/dashboard" className="text-sm text-blue-600 hover:underline">Employee View</a>
            <a href="/manage-documents" className="text-sm text-blue-600 hover:underline">Documents</a>
            <a href="/settings" className="text-sm text-blue-600 hover:underline">Settings</a>
            <button onClick={logout} className="text-sm text-red-600 hover:underline">Logout</button>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 py-6">
        {/* Tabs */}
        <div className="flex gap-2 mb-6 border-b">
          {['today', 'timeoff', 'pay'].map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-4 py-2 text-sm font-medium border-b-2 transition ${
                tab === t ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              {t === 'today' ? 'Who\'s At Work' : t === 'timeoff' ? 'Time Off Requests' : 'Pay Adjustments'}
            </button>
          ))}
        </div>

        {/* Today tab */}
        {tab === 'today' && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="bg-white rounded-xl shadow-sm p-6">
              <h2 className="text-lg font-semibold text-green-700 mb-4">✅ At Work ({todayData?.at_work?.length || 0})</h2>
              {todayLoading ? <p className="text-gray-500">Loading...</p> : (
                <div className="space-y-2">
                  {todayData?.at_work?.map((e, i) => (
                    <div key={i} className="flex justify-between p-3 bg-green-50 rounded-lg">
                      <div>
                        <span className="font-medium">{e.name}</span>
                        <span className="text-xs text-gray-500 ml-2">{e.department}</span>
                      </div>
                      <span className="text-sm text-gray-600">Since {e.last_seen}</span>
                    </div>
                  ))}
                  {todayData?.at_work?.length === 0 && <p className="text-gray-400 text-center py-4">No one currently clocked in</p>}
                </div>
              )}
            </div>
            <div className="bg-white rounded-xl shadow-sm p-6">
              <h2 className="text-lg font-semibold text-red-700 mb-4">❌ Not At Work ({todayData?.not_at_work?.length || 0})</h2>
              {todayLoading ? <p className="text-gray-500">Loading...</p> : (
                <div className="space-y-2 max-h-96 overflow-y-auto">
                  {todayData?.not_at_work?.map((e, i) => (
                    <div key={i} className="flex justify-between p-3 bg-red-50 rounded-lg">
                      <div>
                        <span className="font-medium">{e.name}</span>
                        <span className="text-xs text-gray-500 ml-2">{e.department}</span>
                      </div>
                      <span className="text-sm text-gray-500">Last: {e.last_seen || 'Never'}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Time Off tab */}
        {tab === 'timeoff' && (
          <div className="bg-white rounded-xl shadow-sm p-6">
            <h2 className="text-lg font-semibold mb-4">Time Off Requests</h2>
            {timeOffLoading ? <p className="text-gray-500">Loading...</p> : (
              <div className="space-y-3">
                {timeOffData?.requests?.map(r => (
                  <div key={r.id} className="flex justify-between items-center p-4 border rounded-lg">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-medium">{r.employee_name}</span>
                        <span className={`text-xs px-2 py-1 rounded-full font-medium ${statusColor(r.status)}`}>{r.status}</span>
                        <span className="text-xs text-gray-500 capitalize">{r.type}</span>
                      </div>
                      <p className="text-sm text-gray-600 mt-1">{r.start_date} → {r.end_date}</p>
                      {r.reason && <p className="text-xs text-gray-500 mt-1">"{r.reason}"</p>}
                    </div>
                    {r.status === 'pending' && (
                      <div className="flex gap-2">
                        <button
                          onClick={() => reviewMutation.mutate({ id: r.id, status: 'approved' })}
                          className="px-3 py-1 bg-green-600 text-white rounded text-sm hover:bg-green-700"
                        >
                          Approve
                        </button>
                        <button
                          onClick={() => reviewMutation.mutate({ id: r.id, status: 'denied' })}
                          className="px-3 py-1 bg-red-600 text-white rounded text-sm hover:bg-red-700"
                        >
                          Deny
                        </button>
                      </div>
                    )}
                  </div>
                ))}
                {timeOffData?.requests?.length === 0 && <p className="text-gray-400 text-center py-4">No time-off requests.</p>}
              </div>
            )}
          </div>
        )}

        {/* Pay Adjustments tab */}
        {tab === 'pay' && (
          <div className="space-y-6">
            <div className="bg-white rounded-xl shadow-sm p-6">
              <h2 className="text-lg font-semibold mb-4">Add Pay Adjustment</h2>
              <form
                onSubmit={(e) => { e.preventDefault(); adjMutation.mutate({ ...adjForm, pay_date: adjForm.pay_date || payDate, hours: Number(adjForm.hours) }) }}
                className="grid grid-cols-1 md:grid-cols-5 gap-3"
              >
                <select
                  required
                  value={adjForm.employee_id}
                  onChange={(e) => setAdjForm({ ...adjForm, employee_id: e.target.value })}
                  className="px-3 py-2 border rounded-lg"
                >
                  <option value="">Select Employee...</option>
                  {empData?.employees?.map(e => (
                    <option key={e.timestation_id} value={e.timestation_id}>{e.name}</option>
                  ))}
                </select>
                <select
                  value={adjForm.type}
                  onChange={(e) => setAdjForm({ ...adjForm, type: e.target.value })}
                  className="px-3 py-2 border rounded-lg"
                >
                  <option value="back_hours">Back Hours</option>
                  <option value="vacation_hours">Vacation Hours</option>
                </select>
                <input
                  type="date"
                  value={adjForm.pay_date || payDate}
                  onChange={(e) => setAdjForm({ ...adjForm, pay_date: e.target.value })}
                  className="px-3 py-2 border rounded-lg"
                />
                <input
                  type="number"
                  step="0.25"
                  min="0"
                  required
                  placeholder="Hours"
                  value={adjForm.hours}
                  onChange={(e) => setAdjForm({ ...adjForm, hours: e.target.value })}
                  className="px-3 py-2 border rounded-lg"
                />
                <button type="submit" className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium">
                  {adjMutation.isPending ? 'Adding...' : 'Add'}
                </button>
              </form>
              <input
                type="text"
                placeholder="Description (optional)"
                value={adjForm.description}
                onChange={(e) => setAdjForm({ ...adjForm, description: e.target.value })}
                className="w-full mt-3 px-3 py-2 border rounded-lg"
              />
            </div>

            <div className="bg-white rounded-xl shadow-sm p-6">
              <div className="flex justify-between items-center mb-4">
                <h2 className="text-lg font-semibold">Adjustments for Pay Date</h2>
                <input
                  type="date"
                  value={payDate}
                  onChange={(e) => setPayDate(e.target.value)}
                  className="px-3 py-2 border rounded-lg"
                />
              </div>
              {payLoading ? <p className="text-gray-500">Loading...</p> : (
                <div className="space-y-2">
                  {payData?.adjustments?.map(a => (
                    <div key={a.id} className="flex justify-between p-3 border rounded-lg">
                      <div>
                        <span className="font-medium">{a.employee_name}</span>
                        <span className="ml-2 text-sm text-gray-500 capitalize">{a.type.replace('_', ' ')}</span>
                        {a.description && <span className="ml-2 text-sm text-gray-400">· {a.description}</span>}
                      </div>
                      <span className="font-bold text-blue-600">{a.hours}h</span>
                    </div>
                  ))}
                  {payData?.adjustments?.length === 0 && <p className="text-gray-400 text-center py-4">No adjustments for this date.</p>}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
