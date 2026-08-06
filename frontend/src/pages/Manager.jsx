import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import { logout } from '../lib/auth'

export default function Manager() {
  const qc = useQueryClient()
  const [tab, setTab] = useState('today')
  const [payDate, setPayDate] = useState(new Date().toISOString().slice(0, 10))
  const [adjForm, setAdjForm] = useState({ employee_id: '', pay_date: '', type: 'back_hours', hours: 0, description: '' })
  const [selectedEmpId, setSelectedEmpId] = useState('')
  const [empMonthOffset, setEmpMonthOffset] = useState(0)

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

  // Selected employee calendar
  const empNow = new Date()
  const empTarget = new Date(empNow.getFullYear(), empNow.getMonth() + empMonthOffset, 1)
  const empStart = new Date(empTarget.getFullYear(), empTarget.getMonth(), 1)
  const empEnd = new Date(empTarget.getFullYear(), empTarget.getMonth() + 1, 0)
  const empStartStr = empStart.toISOString().slice(0, 10)
  const empEndStr = empEnd.toISOString().slice(0, 10)
  const empMonthName = empTarget.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })

  const { data: empCalData, isLoading: empCalLoading } = useQuery({
    queryKey: ['emp-calendar', selectedEmpId, empStartStr, empEndStr],
    queryFn: () => api.get(`/api/manager/employee/${selectedEmpId}/calendar`, { params: { start: empStartStr, end: empEndStr } }).then(r => r.data),
    enabled: !!selectedEmpId,
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
          <div className="flex items-center gap-3">
            <img src="/allied-logo.jpg" alt="Allied" className="h-10 w-auto rounded" />
            <h1 className="text-xl font-bold">Allied Connect — Manager</h1>
          </div>
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
          {['today', 'timeoff', 'pay', 'empcal'].map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-4 py-2 text-sm font-medium border-b-2 transition ${
                tab === t ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              {t === 'today' ? 'Who\'s At Work' : t === 'timeoff' ? 'Time Off Requests' : t === 'pay' ? 'Pay Adjustments' : 'Employee Calendar'}
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

        {/* Employee Calendar tab */}
        {tab === 'empcal' && (
          <div className="space-y-6">
            <div className="bg-white rounded-xl shadow-sm p-6">
              <div className="flex flex-wrap gap-4 items-center mb-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Select Employee</label>
                  <select
                    value={selectedEmpId}
                    onChange={(e) => setSelectedEmpId(e.target.value)}
                    className="px-4 py-2 border rounded-lg min-w-64"
                  >
                    <option value="">Choose an employee...</option>
                    {empData?.employees?.map(e => (
                      <option key={e.timestation_id} value={e.timestation_id}>
                        {e.name} — {e.department}
                      </option>
                    ))}
                  </select>
                </div>
                {selectedEmpId && (
                  <div className="flex gap-2 items-end">
                    <button onClick={() => setEmpMonthOffset(m => m - 1)} className="px-3 py-2 border rounded hover:bg-gray-50 text-sm">← Prev</button>
                    <span className="px-3 py-2 text-sm font-medium">{empMonthName}</span>
                    <button onClick={() => setEmpMonthOffset(0)} className="px-3 py-2 border rounded hover:bg-gray-50 text-sm">Today</button>
                    <button onClick={() => setEmpMonthOffset(m => m + 1)} className="px-3 py-2 border rounded hover:bg-gray-50 text-sm">Next →</button>
                  </div>
                )}
              </div>

              {!selectedEmpId ? (
                <p className="text-gray-400 text-center py-8">Select an employee to view their calendar.</p>
              ) : empCalLoading ? (
                <p className="text-gray-500 text-center py-8">Loading calendar...</p>
              ) : (
                <>
                  {/* Stats */}
                  <div className="grid grid-cols-3 gap-4 mb-6">
                    {(() => {
                      const days = empCalData?.days || []
                      const workedDays = days.filter(d => d.worked)
                      const lateDays = days.filter(d => d.is_late)
                      const totalHours = workedDays.reduce((sum, d) => sum + d.total_hours, 0)
                      return (
                        <>
                          <div className="bg-blue-50 p-4 rounded-lg">
                            <p className="text-sm text-gray-500">Total Hours</p>
                            <p className="text-2xl font-bold text-blue-600">{totalHours.toFixed(2)}</p>
                          </div>
                          <div className="bg-green-50 p-4 rounded-lg">
                            <p className="text-sm text-gray-500">Days Worked</p>
                            <p className="text-2xl font-bold text-green-600">{workedDays.length}</p>
                          </div>
                          <div className="bg-red-50 p-4 rounded-lg">
                            <p className="text-sm text-gray-500">Late Arrivals</p>
                            <p className="text-2xl font-bold text-red-600">{lateDays.length}</p>
                          </div>
                        </>
                      )
                    })()}
                  </div>

                  {/* Calendar grid */}
                  {(() => {
                    const days = empCalData?.days || []
                    const firstDow = empStart.getDay()
                    const daysInMonth = empEnd.getDate()
                    const cells = []
                    for (let i = 0; i < firstDow; i++) cells.push(null)
                    for (let d = 1; d <= daysInMonth; d++) {
                      const dateStr = `${empStart.getFullYear()}-${String(empStart.getMonth() + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`
                      cells.push(days.find(day => day.date === dateStr) || { date: dateStr, worked: false })
                    }
                    return (
                      <>
                        <div className="grid grid-cols-7 gap-1 mb-1">
                          {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map(d => (
                            <div key={d} className="text-center text-xs font-medium text-gray-500 py-1">{d}</div>
                          ))}
                        </div>
                        <div className="grid grid-cols-7 gap-1">
                          {cells.map((cell, i) => (
                            <div key={i} className={[
                              'min-h-20 p-1 rounded border text-xs',
                              !cell && 'bg-gray-50 border-gray-100',
                              cell && !cell.worked && !cell.is_missed && 'bg-white border-gray-200',
                              cell?.worked && !cell.is_late && 'bg-green-50 border-green-200',
                              cell?.is_late && 'bg-red-50 border-red-200',
                              cell?.is_missed && 'bg-orange-50 border-orange-300',
                            ].filter(Boolean).join(' ')}>
                              {cell && (
                                <>
                                  <div className="font-medium text-gray-700">{parseInt(cell.date.slice(-2))}</div>
                                  {cell.worked && (
                                    <div className="mt-1">
                                      <div className="text-green-700 font-medium">{cell.total_hours}h</div>
                                      {cell.is_late && <div className="text-red-600">Late {cell.late_minutes}m</div>}
                                    </div>
                                  )}
                                  {cell.is_missed && !cell.worked && (
                                    <div className="mt-1 text-orange-600 font-medium">Missed</div>
                                  )}
                                </>
                              )}
                            </div>
                          ))}
                        </div>
                        <div className="flex gap-4 mt-3 text-xs text-gray-600">
                          <span className="flex items-center gap-1"><span className="w-3 h-3 bg-green-100 border border-green-300 rounded"></span> Worked</span>
                          <span className="flex items-center gap-1"><span className="w-3 h-3 bg-red-100 border border-red-300 rounded"></span> Late</span>
                          <span className="flex items-center gap-1"><span className="w-3 h-3 bg-orange-100 border border-orange-300 rounded"></span> Missed</span>
                          <span className="flex items-center gap-1"><span className="w-3 h-3 bg-white border border-gray-300 rounded"></span> Not worked</span>
                        </div>
                      </>
                    )
                  })()}

                  {/* Recent shifts detail */}
                  {(() => {
                    const workedDays = (empCalData?.days || []).filter(d => d.worked)
                    if (workedDays.length === 0) return null
                    return (
                      <div className="mt-6">
                        <h3 className="text-sm font-semibold mb-2">Recent Shifts</h3>
                        <div className="space-y-2 max-h-64 overflow-y-auto">
                          {workedDays.slice(-10).reverse().map(day => (
                            <div key={day.date} className="flex justify-between items-center p-3 bg-gray-50 rounded-lg">
                              <div>
                                <span className="font-medium text-sm">{day.date}</span>
                                {day.is_late && <span className="ml-2 text-red-600 text-xs">⚠ {day.late_minutes}m late</span>}
                              </div>
                              <div className="text-sm text-gray-600">
                                {day.shifts.map((s, i) => (
                                  <div key={i} className="text-right">
                                    {s.in?.slice(11, 16)} → {s.out?.slice(11, 16)} ({(s.minutes / 60).toFixed(1)}h)
                                  </div>
                                ))}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )
                  })()}
                </>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
