import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import { formatCalendarDate } from '../lib/calendar'
import { logout, isSuperAdmin } from '../lib/auth'

export default function Manager() {
  const qc = useQueryClient()
  const [tab, setTab] = useState('today')
  const [payDate, setPayDate] = useState(new Date().toISOString().slice(0, 10))
  const [adjForm, setAdjForm] = useState({ employee_id: '', pay_date: '', type: 'back_hours', hours: 0, description: '' })
  const [selectedEmpId, setSelectedEmpId] = useState('')
  const [selectedEmpPeriodId, setSelectedEmpPeriodId] = useState('')
  const [empMonthOffset, setEmpMonthOffset] = useState(0)
  const [selectedDay, setSelectedDay] = useState(null)
  const [selectedRequest, setSelectedRequest] = useState(null)

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
    enabled: !!selectedEmpId && !selectedEmpPeriodId,
  })

  const { data: empPeriods } = useQuery({
    queryKey: ['manager-pay-periods'],
    queryFn: () => api.get('/api/manager/pay-periods').then(r => r.data),
  })

  const { data: empPeriodData, isLoading: empPeriodLoading } = useQuery({
    queryKey: ['emp-pay-period', selectedEmpId, selectedEmpPeriodId],
    queryFn: () => api.get(`/api/manager/employee/${selectedEmpId}/pay-period/${selectedEmpPeriodId}`).then(r => r.data),
    enabled: !!selectedEmpId && !!selectedEmpPeriodId,
  })

  const visibleEmpCalendar = selectedEmpPeriodId
    ? { days: empPeriodData?.calendar || [] }
    : empCalData
  const visibleEmpLoading = selectedEmpPeriodId ? empPeriodLoading : empCalLoading

  const reviewMutation = useMutation({
    mutationFn: ({ id, status }) => api.put(`/api/time-off/${id}/review`, { status }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['all-time-off'] })
      setSelectedRequest(null)
    },
  })

  const voidMutation = useMutation({
    mutationFn: (id) => api.put(`/api/time-off/${id}/void`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['all-time-off'] }),
  })

  const adjMutation = useMutation({
    mutationFn: (data) => api.post('/api/manager/pay-adjustment', data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['pay-adjustments', payDate] })
      setAdjForm({ employee_id: '', pay_date: payDate, type: 'back_hours', hours: 0, description: '' })
    },
  })

  const pendingRequestCount = timeOffData?.requests?.filter(request => request.status === 'pending').length || 0
  const payPeriodFor = (request) => empPeriods?.pay_periods?.find(period => period.id === request?.pay_period_id)

  const formatEasternTime = (timestamp) => timestamp
    ? new Intl.DateTimeFormat('en-US', {
        timeZone: 'America/New_York',
        month: 'short', day: 'numeric', year: 'numeric',
        hour: 'numeric', minute: '2-digit', second: '2-digit', timeZoneName: 'short',
      }).format(new Date(timestamp))
    : 'Unknown'

  const statusColor = (status) => ({
    pending: 'bg-yellow-100 text-yellow-800',
    approved: 'bg-green-100 text-green-800',
    denied: 'bg-red-100 text-red-800',
    voided: 'bg-orange-100 text-orange-800',
  }[status] || 'bg-gray-100')

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white shadow-sm">
        <div className="max-w-7xl mx-auto px-4 py-4 flex flex-col gap-4 sm:flex-row sm:justify-between sm:items-center">
          <div className="flex items-center gap-3 min-w-0">
            <img src="/allied-logo.jpg" alt="Allied" className="h-10 w-auto max-w-32 rounded shrink-0" />
            <h1 className="text-lg sm:text-xl font-bold leading-tight">Allied Connect — Manager</h1>
          </div>
          <nav className="grid grid-cols-2 gap-x-4 gap-y-3 w-full sm:w-auto sm:flex sm:flex-wrap sm:items-center sm:justify-end" aria-label="Management navigation">
            <a href="/dashboard" className="text-sm text-blue-600 hover:underline">Employee View</a>
            <a href="/manage-documents" className="text-sm text-blue-600 hover:underline">Documents</a>
            <a href="/directory" className="text-sm text-blue-600 hover:underline">Employee Directory</a>
            {isSuperAdmin() && <a href="/compliance" className="text-sm text-blue-600 hover:underline">Compliance</a>}
            <a href="/settings" className="text-sm text-blue-600 hover:underline">Settings</a>
            <button onClick={logout} className="text-sm text-red-600 hover:underline text-left sm:text-center">Logout</button>
          </nav>
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
              <span className="relative inline-flex items-center">
                {t === 'today' ? 'Who\'s At Work' : t === 'timeoff' ? 'Time Off Requests' : t === 'pay' ? 'Pay Adjustments' : 'Employee Calendar'}
                {t === 'timeoff' && pendingRequestCount > 0 && (
                  <span className="absolute -top-4 -right-6 min-w-5 h-5 px-1 rounded-full bg-red-600 text-white text-xs leading-5 text-center font-bold" aria-label={`${pendingRequestCount} pending time-off requests`}>
                    {pendingRequestCount}
                  </span>
                )}
              </span>
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
                  <button key={r.id} type="button" onClick={() => setSelectedRequest(r)} className="w-full text-left flex flex-col sm:flex-row sm:justify-between sm:items-center gap-3 p-4 border rounded-lg hover:border-blue-400 hover:bg-blue-50 transition">
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium">{r.employee_name}</span>
                        <span className={`text-xs px-2 py-1 rounded-full font-medium ${statusColor(r.status)}`}>{r.status}</span>
                        <span className="text-sm font-medium text-blue-700 capitalize">{(r.request_type || r.type || 'time off').replaceAll('_', ' ')}</span>
                      </div>
                      <p className="text-sm text-gray-600 mt-1">
                        {r.request_type === 'back_hours' ? `${r.hours_requested || 0} back hours requested` : `${r.start_date} → ${r.end_date}`}
                      </p>
                      <p className="text-xs text-blue-600 mt-2">View request details</p>
                    </div>
                    <span className="text-xl text-gray-400" aria-hidden="true">›</span>
                  </button>
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
                    onChange={(e) => {
                      setSelectedEmpId(e.target.value)
                      setSelectedEmpPeriodId('')
                    }}
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
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Select Pay Period</label>
                    <select
                      value={selectedEmpPeriodId}
                      onChange={(e) => {
                        const periodId = e.target.value
                        setSelectedEmpPeriodId(periodId)
                        if (periodId) {
                          const period = empPeriods?.pay_periods?.find(p => p.id == periodId)
                          if (period) {
                            const periodStart = new Date(`${period.start_date}T00:00:00`)
                            const offset = (periodStart.getFullYear() - empNow.getFullYear()) * 12 + periodStart.getMonth() - empNow.getMonth()
                            setEmpMonthOffset(offset)
                          }
                        }
                      }}
                      className="px-4 py-2 border rounded-lg min-w-72"
                    >
                      <option value="">Monthly calendar view...</option>
                      {empPeriods?.pay_periods?.map(period => (
                        <option key={period.id} value={period.id}>
                          {period.label} — {period.start_date} → {period.end_date}
                        </option>
                      ))}
                    </select>
                  </div>
                )}
                {selectedEmpId && !selectedEmpPeriodId && (
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
              ) : visibleEmpLoading ? (
                <p className="text-gray-500 text-center py-8">Loading employee data...</p>
              ) : (
                <>
                  {/* Pay-period summary mirrors the employee view. */}
                  {selectedEmpPeriodId && empPeriodData && (
                    <div className="mb-6 space-y-4">
                      <div className="rounded-lg border-2 border-blue-400 bg-blue-50 p-3 text-sm text-blue-800">
                        <span className="font-semibold">{empPeriodData.pay_period.label}</span>
                        {' '}· Pay: {empPeriodData.pay_period.pay_date} · {empPeriodData.pay_period.start_date} → {empPeriodData.pay_period.end_date}
                      </div>
                      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
                        <div className="bg-blue-50 p-3 rounded-lg"><p className="text-xs text-gray-500">Total Hours</p><p className="text-xl font-bold text-blue-600">{empPeriodData.total_hours}</p></div>
                        <div className="bg-green-50 p-3 rounded-lg"><p className="text-xs text-gray-500">Days Worked</p><p className="text-xl font-bold text-green-600">{empPeriodData.days_worked}</p></div>
                        <div className="bg-red-50 p-3 rounded-lg"><p className="text-xs text-gray-500">Late</p><p className="text-xl font-bold text-red-600">{empPeriodData.late_arrivals}</p></div>
                        <div className="bg-yellow-50 p-3 rounded-lg"><p className="text-xs text-gray-500">Left Early</p><p className="text-xl font-bold text-yellow-600">{empPeriodData.left_early}</p></div>
                        <div className="bg-purple-50 p-3 rounded-lg"><p className="text-xs text-gray-500">Back Used</p><p className="text-xl font-bold text-purple-600">{empPeriodData.back_hours_used}h</p></div>
                        <div className="bg-indigo-50 p-3 rounded-lg"><p className="text-xs text-gray-500">Vacation Used</p><p className="text-xl font-bold text-indigo-600">{empPeriodData.vacation_hours_used}h</p></div>
                        <div className="bg-teal-50 p-3 rounded-lg"><p className="text-xs text-gray-500">Sick Used</p><p className="text-xl font-bold text-teal-600">{empPeriodData.sick_hours_used}h</p></div>
                      </div>
                      {empPeriodData.can_view_pay && empPeriodData.gross_pay !== null && empPeriodData.gross_pay !== undefined && (
                        <div className="bg-emerald-50 border border-emerald-200 p-4 rounded-lg flex flex-wrap justify-between gap-4 items-center">
                          <div>
                            <p className="text-xs text-gray-500">Gross Pay · ${empPeriodData.hourly_rate}/hr</p>
                            <p className="text-sm text-gray-600">Worked {empPeriodData.total_hours}h + balance hours used {(empPeriodData.back_hours_used + empPeriodData.vacation_hours_used + empPeriodData.sick_hours_used).toFixed(2)}h</p>
                          </div>
                          <p className="text-2xl font-bold text-emerald-700">${empPeriodData.gross_pay.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</p>
                        </div>
                      )}
                      {!empPeriodData.can_view_pay && (
                        <p className="text-xs text-gray-500 bg-gray-50 border rounded-lg p-3">Hourly rate and gross pay are restricted to super admins.</p>
                      )}
                      {empPeriodData.hours_used?.length > 0 && (
                        <div>
                          <h3 className="text-sm font-semibold mb-2">Hours Used This Period</h3>
                          <div className="space-y-1">
                            {empPeriodData.hours_used.map((entry, index) => (
                              <div key={index} className="p-2 bg-gray-50 rounded text-xs">
                                <span className="font-medium text-red-700">{entry.amount}h {entry.type.replace('_', ' ')}</span>
                                <span className="ml-2 text-gray-500">by {entry.input_by_name || 'system'} · {entry.created_at ? new Date(entry.created_at).toLocaleString() : ''}</span>
                                {entry.reason && <span className="ml-2 text-gray-400">— {entry.reason}</span>}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Stats */}
                  <div className="grid grid-cols-4 gap-4 mb-6">
                    {(() => {
                      const days = visibleEmpCalendar?.days || []
                      const workedDays = days.filter(d => d.worked)
                      const lateDays = days.filter(d => d.is_late)
                      const earlyDays = days.filter(d => d.is_early_leave)
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
                          <div className="bg-yellow-50 p-4 rounded-lg">
                            <p className="text-sm text-gray-500">Left Early</p>
                            <p className="text-2xl font-bold text-yellow-600">{earlyDays.length}</p>
                          </div>
                        </>
                      )
                    })()}
                  </div>

                  {/* Calendar grid */}
                  {(() => {
                    const days = visibleEmpCalendar?.days || []
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
                          {cells.map((cell, i) => {
                            const bg = !cell ? 'bg-gray-50 border-gray-100'
                              : cell.is_missed ? 'bg-orange-100 border-orange-400'
                              : cell.is_late ? 'bg-red-100 border-red-400'
                              : cell.is_early_leave ? 'bg-yellow-100 border-yellow-400'
                              : cell.worked ? 'bg-green-100 border-green-300'
                              : 'bg-white border-gray-200'
                            return (
                              <div
                                key={i}
                                onClick={() => cell && setSelectedDay(cell)}
                                className={`min-h-20 p-1 rounded border text-xs cursor-pointer hover:ring-2 hover:ring-blue-300 transition ${bg}`}
                              >
                                {cell && (
                                  <>
                                    <div className="font-medium text-gray-700">{parseInt(cell.date.slice(-2))}</div>
                                    {cell.worked && (
                                      <div className="mt-1">
                                        <div className="text-gray-800 font-medium">{cell.total_hours}h</div>
                                        {cell.is_late && <div className="text-red-700">Late {cell.late_minutes}m</div>}
                                        {cell.is_early_leave && <div className="text-yellow-800">Early {cell.early_leave_minutes}m</div>}
                                      </div>
                                    )}
                                    {cell.is_missed && !cell.worked && (
                                      <div className="mt-1 text-orange-700 font-medium">Missed</div>
                                    )}
                                  </>
                                )}
                              </div>
                            )
                          })}
                        </div>
                        <div className="flex flex-wrap gap-4 mt-3 text-xs text-gray-600">
                          <span className="flex items-center gap-1"><span className="w-3 h-3 bg-green-100 border border-green-300 rounded"></span> Worked</span>
                          <span className="flex items-center gap-1"><span className="w-3 h-3 bg-red-100 border border-red-400 rounded"></span> Late</span>
                          <span className="flex items-center gap-1"><span className="w-3 h-3 bg-yellow-100 border border-yellow-400 rounded"></span> Left early</span>
                          <span className="flex items-center gap-1"><span className="w-3 h-3 bg-orange-100 border border-orange-400 rounded"></span> Missed</span>
                          <span className="flex items-center gap-1"><span className="w-3 h-3 bg-white border border-gray-300 rounded"></span> Not worked</span>
                        </div>
                        <p className="text-xs text-gray-400 mt-2">Click any day to see punch in/out times</p>
                      </>
                    )
                  })()}

                  {/* Recent shifts detail */}
                  {(() => {
                    const workedDays = (visibleEmpCalendar?.days || []).filter(d => d.worked)
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

      {/* Time-Off Request Detail Modal */}
      {selectedRequest && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={() => setSelectedRequest(null)}>
          <div className="bg-white rounded-xl shadow-2xl max-w-lg w-full p-6" onClick={(e) => e.stopPropagation()}>
            <div className="flex justify-between items-start gap-4 mb-5">
              <div>
                <h3 className="text-xl font-bold">{selectedRequest.employee_name}</h3>
                <p className="text-sm text-gray-500">Time-Off Request #{selectedRequest.id}</p>
              </div>
              <button onClick={() => setSelectedRequest(null)} className="text-gray-500 hover:text-gray-700 text-xl" aria-label="Close request details">✕</button>
            </div>
            <dl className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
              <div><dt className="text-gray-500">Request Type</dt><dd className="font-semibold capitalize">{(selectedRequest.request_type || selectedRequest.type || 'time off').replaceAll('_', ' ')}</dd></div>
              <div><dt className="text-gray-500">Status</dt><dd><span className={`inline-block text-xs px-2 py-1 rounded-full font-medium ${statusColor(selectedRequest.status)}`}>{selectedRequest.status}</span></dd></div>
              {selectedRequest.request_type === 'back_hours' ? (
                <>
                  <div><dt className="text-gray-500">Hours Requested</dt><dd className="font-semibold">{selectedRequest.hours_requested || 0} hours</dd></div>
                  <div><dt className="text-gray-500">Hours From</dt><dd className="font-semibold capitalize">{(selectedRequest.hour_type || 'back_hours').replaceAll('_', ' ')}</dd></div>
                  <div><dt className="text-gray-500">Pay Period</dt><dd className="font-semibold">{payPeriodFor(selectedRequest)?.label || `Pay Period ID ${selectedRequest.pay_period_id || 'Not selected'}`}</dd>{payPeriodFor(selectedRequest) && <p className="text-xs text-gray-500 mt-1">{payPeriodFor(selectedRequest).start_date} → {payPeriodFor(selectedRequest).end_date}</p>}</div>
                </>
              ) : (
                <>
                  <div><dt className="text-gray-500">Start Date</dt><dd className="font-semibold">{selectedRequest.start_date}</dd></div>
                  <div><dt className="text-gray-500">End Date</dt><dd className="font-semibold">{selectedRequest.end_date}</dd></div>
                  {selectedRequest.hours_requested && <div><dt className="text-gray-500">Paid Hours</dt><dd className="font-semibold">{selectedRequest.hours_requested} hours from {(selectedRequest.hour_type || '').replaceAll('_', ' ')}</dd></div>}
                </>
              )}
              <div className="sm:col-span-2"><dt className="text-gray-500">Reason</dt><dd className="font-semibold">{selectedRequest.reason?.trim() || 'No reason provided'}</dd></div>
              <div className="sm:col-span-2"><dt className="text-gray-500">Submitted (Eastern Time)</dt><dd className="font-semibold">{formatEasternTime(selectedRequest.created_at)}</dd></div>
            </dl>
            {selectedRequest.status === 'pending' && (
              <div className="flex flex-col-reverse sm:flex-row sm:justify-end gap-3 mt-6 pt-5 border-t">
                <button onClick={() => reviewMutation.mutate({ id: selectedRequest.id, status: 'denied' })} disabled={reviewMutation.isPending} className="px-4 py-2 bg-red-600 text-white rounded-lg disabled:opacity-50">Deny Request</button>
                <button onClick={() => reviewMutation.mutate({ id: selectedRequest.id, status: 'approved' })} disabled={reviewMutation.isPending} className="px-4 py-2 bg-green-600 text-white rounded-lg disabled:opacity-50">Approve Request</button>
              </div>
            )}
            {selectedRequest.status === 'approved' && (
              <div className="flex justify-end mt-6 pt-5 border-t"><button onClick={() => { voidMutation.mutate(selectedRequest.id); setSelectedRequest(null) }} className="px-4 py-2 bg-orange-600 text-white rounded-lg">Void Request</button></div>
            )}
          </div>
        </div>
      )}

      {/* Day Detail Modal */}
      {selectedDay && (
        <div
          className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4"
          onClick={() => setSelectedDay(null)}
        >
          <div
            className="bg-white rounded-2xl shadow-2xl max-w-md w-full p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-lg font-bold">
                {formatCalendarDate(selectedDay.date)}
              </h3>
              <button onClick={() => setSelectedDay(null)} className="text-gray-400 hover:text-gray-600 text-xl">✕</button>
            </div>

            {selectedDay.worked ? (
              <div className="space-y-3">
                <div className="bg-gray-50 p-3 rounded-lg">
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-500">Total Hours</span>
                    <span className="font-bold text-blue-600">{selectedDay.total_hours}h</span>
                  </div>
                </div>

                {selectedDay.is_late && (
                  <div className="bg-red-50 border border-red-200 p-3 rounded-lg">
                    <p className="text-red-700 text-sm font-medium">⚠ Arrived {selectedDay.late_minutes} minutes late</p>
                  </div>
                )}
                {selectedDay.is_early_leave && (
                  <div className="bg-yellow-50 border border-yellow-300 p-3 rounded-lg">
                    <p className="text-yellow-800 text-sm font-medium">⏰ Left {selectedDay.early_leave_minutes} minutes early</p>
                  </div>
                )}

                <div>
                  <p className="text-sm font-medium text-gray-700 mb-2">Punches</p>
                  <div className="space-y-2">
                    {selectedDay.shifts.map((s, i) => (
                      <div key={i} className="flex justify-between items-center p-3 border rounded-lg">
                        <div className="flex items-center gap-3">
                          <span className="bg-green-100 text-green-700 px-2 py-1 rounded text-xs font-medium">IN</span>
                          <span className="text-sm">{s.in?.slice(11, 16)}</span>
                        </div>
                        <div className="text-gray-400">→</div>
                        <div className="flex items-center gap-3">
                          <span className="text-sm">{s.out?.slice(11, 16)}</span>
                          <span className="bg-red-100 text-red-700 px-2 py-1 rounded text-xs font-medium">OUT</span>
                        </div>
                        <div className="text-sm text-gray-600 font-medium">{(s.minutes / 60).toFixed(1)}h</div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              <div className="text-center py-6">
                {selectedDay.is_missed ? (
                  <div>
                    <p className="text-orange-600 font-medium mb-2">📅 Scheduled but did not work</p>
                    <p className="text-gray-500 text-sm">This day was scheduled but no punches were recorded.</p>
                  </div>
                ) : (
                  <p className="text-gray-500">No shifts recorded for this day.</p>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
