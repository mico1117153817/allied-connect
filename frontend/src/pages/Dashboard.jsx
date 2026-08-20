import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { api } from '../lib/api'
import { formatCalendarDate } from '../lib/calendar'
import { getEmployee, logout, isManager, canAccessCompliance } from '../lib/auth'

export default function Dashboard() {
  const employee = getEmployee()
  const qc = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const selectedEmployeeId = isManager() ? (searchParams.get('employee') || '') : ''
  const viewingEmployee = !!selectedEmployeeId
  const [monthOffset, setMonthOffset] = useState(0)
  const [emailInput, setEmailInput] = useState('')
  const [emailMsg, setEmailMsg] = useState('')
  const [selectedDay, setSelectedDay] = useState(null)
  const [selectedPpId, setSelectedPpId] = useState('')

  // Get current month date range
  const now = new Date()
  const targetMonth = new Date(now.getFullYear(), now.getMonth() + monthOffset, 1)
  const start = new Date(targetMonth.getFullYear(), targetMonth.getMonth(), 1)
  const end = new Date(targetMonth.getFullYear(), targetMonth.getMonth() + 1, 0)
  const startStr = start.toISOString().slice(0, 10)
  const endStr = end.toISOString().slice(0, 10)

  const { data: managementEmployees } = useQuery({
    queryKey: ['employee-view-employees'],
    queryFn: () => api.get('/api/manager/employees').then(r => r.data),
    enabled: isManager(),
  })

  const selectedEmployee = managementEmployees?.employees?.find(e => e.timestation_id === selectedEmployeeId)

  const { data: hoursData, isLoading: hoursLoading } = useQuery({
    queryKey: ['hours', selectedEmployeeId || 'self', startStr, endStr],
    queryFn: () => viewingEmployee
      ? api.get(`/api/manager/employee/${selectedEmployeeId}/hours`, { params: { start: startStr, end: endStr } }).then(r => r.data)
      : api.get('/api/me/hours', { params: { start: startStr, end: endStr } }).then(r => r.data),
    enabled: !isManager() || viewingEmployee,
  })

  const { data: calData, isLoading: calLoading } = useQuery({
    queryKey: ['calendar', selectedEmployeeId || 'self', startStr, endStr],
    queryFn: () => viewingEmployee
      ? api.get(`/api/manager/employee/${selectedEmployeeId}/calendar`, { params: { start: startStr, end: endStr } }).then(r => r.data)
      : api.get('/api/me/calendar', { params: { start: startStr, end: endStr } }).then(r => r.data),
    enabled: !isManager() || viewingEmployee,
  })

  const { data: profile } = useQuery({
    queryKey: ['profile'],
    queryFn: () => api.get('/api/me/').then(r => r.data),
    enabled: !viewingEmployee,
  })

  // Pay periods
  const { data: ppList } = useQuery({
    queryKey: ['pay-periods', viewingEmployee ? 'management' : 'self'],
    queryFn: () => api.get(viewingEmployee ? '/api/manager/pay-periods' : '/api/me/pay-periods').then(r => r.data),
    enabled: !isManager() || viewingEmployee,
  })

  const { data: ppData, isLoading: ppLoading } = useQuery({
    queryKey: ['pay-period-detail', selectedEmployeeId || 'self', selectedPpId],
    queryFn: () => viewingEmployee
      ? api.get(`/api/manager/employee/${selectedEmployeeId}/pay-period/${selectedPpId}`).then(r => r.data)
      : api.get(`/api/me/pay-period/${selectedPpId}`).then(r => r.data),
    enabled: !!selectedPpId && (!isManager() || viewingEmployee),
  })

  // Hour balances
  const { data: balancesData } = useQuery({
    queryKey: ['balances', selectedEmployeeId || 'self'],
    queryFn: () => viewingEmployee
      ? api.get(`/api/manager/employee/${selectedEmployeeId}/balances`).then(r => r.data)
      : api.get('/api/me/balances').then(r => r.data),
    enabled: !isManager() || viewingEmployee,
  })

  const { data: balanceHistory } = useQuery({
    queryKey: ['balance-history', selectedEmployeeId || 'self'],
    queryFn: () => viewingEmployee
      ? api.get(`/api/manager/employee/${selectedEmployeeId}/balances`).then(r => r.data)
      : api.get('/api/me/balance-history').then(r => r.data),
    enabled: !isManager() || viewingEmployee,
  })

  const emailMutation = useMutation({
    mutationFn: (email) => api.put('/api/me/email', { email }),
    onSuccess: () => {
      setEmailMsg('Email saved!')
      qc.invalidateQueries({ queryKey: ['profile'] })
      setEmailInput('')
    },
    onError: () => setEmailMsg('Failed to save email.'),
  })

  const days = calData?.days || []
  const workedDays = days.filter(d => d.worked)
  const lateDays = days.filter(d => d.is_late)
  const earlyLeaveDays = days.filter(d => d.is_early_leave)
  const monthName = targetMonth.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })

  // Build calendar grid
  const firstDayOfWeek = start.getDay() // 0=Sun
  const daysInMonth = end.getDate()
  const calendarCells = []
  for (let i = 0; i < firstDayOfWeek; i++) calendarCells.push(null)
  for (let d = 1; d <= daysInMonth; d++) {
    const dateStr = `${start.getFullYear()}-${String(start.getMonth() + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`
    calendarCells.push(days.find(day => day.date === dateStr) || { date: dateStr, worked: false })
  }

  // Determine cell background color
  const cellBg = (cell) => {
    if (!cell) return 'bg-gray-50 border-gray-100'
    if (cell.is_missed) return 'bg-orange-100 border-orange-400'
    if (cell.is_late) return 'bg-red-100 border-red-400'
    if (cell.is_early_leave) return 'bg-yellow-100 border-yellow-400'
    if (cell.worked) return 'bg-green-100 border-green-300'
    return 'bg-white border-gray-200'
  }

  // Check if a date falls within the selected pay period
  const ppStart = ppData?.pay_period?.start_date
  const ppEnd = ppData?.pay_period?.end_date
  const isInPayPeriod = (dateStr) => ppStart && ppEnd && dateStr >= ppStart && dateStr <= ppEnd

  // Format time from ISO string
  const fmtTime = (iso) => iso ? iso.slice(11, 16) : '--'

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex justify-between items-center">
          <div className="flex items-center gap-3">
            <img src="/allied-logo.jpg" alt="Allied" className="h-10 w-auto rounded" />
            <h1 className="text-xl font-bold text-gray-900">Allied Connect</h1>
          </div>
          <div className="flex items-center gap-4">
            <span className="text-sm text-gray-600">{viewingEmployee ? selectedEmployee?.name : employee?.name}</span>
            {canAccessCompliance() && (
              <a href="/compliance" className="text-sm text-blue-600 hover:underline">Compliance</a>
            )}
            {isManager() && (
              <a href="/manager" className="text-sm text-blue-600 hover:underline">Manager View</a>
            )}
            <button onClick={logout} className="text-sm text-red-600 hover:underline">Logout</button>
          </div>
        </div>
      </header>

      {isManager() && (
        <div className="max-w-7xl mx-auto px-4 mt-4">
          <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 flex flex-wrap gap-4 items-end">
            <div className="flex-1 min-w-64">
              <label className="block text-sm font-medium text-blue-900 mb-1">Employee View — Select Employee</label>
              <select
                value={selectedEmployeeId}
                onChange={(e) => {
                  const value = e.target.value
                  setSelectedPpId('')
                  setMonthOffset(0)
                  if (value) setSearchParams({ employee: value })
                  else setSearchParams({})
                }}
                className="w-full px-4 py-2 border rounded-lg bg-white"
              >
                <option value="">Choose an employee...</option>
                {managementEmployees?.employees?.map(item => (
                  <option key={item.timestation_id} value={item.timestation_id}>{item.name} — {item.department}</option>
                ))}
              </select>
            </div>
            {viewingEmployee && (
              <div className="text-sm text-blue-800">
                Viewing the portal as <span className="font-semibold">{selectedEmployee?.name}</span>.
                {employee?.role === 'manager' && ' Hourly rate and gross pay remain hidden.'}
              </div>
            )}
          </div>
        </div>
      )}

      {isManager() && !viewingEmployee && (
        <div className="max-w-7xl mx-auto px-4 py-12">
          <div className="bg-white rounded-xl shadow-sm p-10 text-center text-gray-500">
            Select an employee above to open their employee dashboard.
          </div>
        </div>
      )}

      {(!isManager() || viewingEmployee) && (
      <>
      {/* Email prompt if missing */}
      {profile && !profile.email && (
        <div className="max-w-7xl mx-auto px-4 mt-4">
          <div className="bg-yellow-50 border-l-4 border-yellow-400 p-4 rounded">
            <p className="text-sm text-yellow-800 mb-2">Please add your email to receive time-off notifications.</p>
            <div className="flex gap-2">
              <input
                type="email"
                value={emailInput}
                onChange={(e) => setEmailInput(e.target.value)}
                placeholder="your@email.com"
                className="flex-1 px-3 py-2 border rounded text-sm"
              />
              <button
                onClick={() => emailInput && emailMutation.mutate(emailInput)}
                className="px-4 py-2 bg-blue-600 text-white rounded text-sm hover:bg-blue-700"
              >
                Save
              </button>
            </div>
            {emailMsg && <p className="text-xs mt-1 text-gray-700">{emailMsg}</p>}
          </div>
        </div>
      )}

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* Stats */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
          <div className="bg-white p-5 rounded-xl shadow-sm">
            <p className="text-sm text-gray-500">Hours This Month</p>
            <p className="text-2xl font-bold text-blue-600">{hoursLoading ? '...' : (hoursData?.total_hours || 0)}</p>
          </div>
          <div className="bg-white p-5 rounded-xl shadow-sm">
            <p className="text-sm text-gray-500">Days Worked</p>
            <p className="text-2xl font-bold text-green-600">{workedDays.length}</p>
          </div>
          <div className="bg-white p-5 rounded-xl shadow-sm">
            <p className="text-sm text-gray-500">Late Arrivals</p>
            <p className="text-2xl font-bold text-red-600">{lateDays.length}</p>
          </div>
          <div className="bg-white p-5 rounded-xl shadow-sm">
            <p className="text-sm text-gray-500">Left Early</p>
            <p className="text-2xl font-bold text-yellow-600">{earlyLeaveDays.length}</p>
          </div>
        </div>

        {/* Navigation */}
        <div className="flex gap-3 mb-6">
          <a href={viewingEmployee ? `/time-off?employee=${selectedEmployeeId}` : '/time-off'} className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium">Request Time Off</a>
          <a href="/documents" className="px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 text-sm font-medium">Documents</a>
          {!viewingEmployee && <a href="/my-info" className="px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 text-sm font-medium">My Info</a>}
          {!viewingEmployee && <a href="/directory" className="px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 text-sm font-medium">Employee Directory</a>}
        </div>

        {/* Hour Balances */}
        {balancesData?.balances && (
          <div className="bg-white rounded-xl shadow-sm p-6 mb-6">
            <h2 className="text-lg font-semibold mb-4">My Hour Balances</h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="bg-purple-50 p-4 rounded-lg">
                <p className="text-sm text-gray-500">Back Hours</p>
                <p className="text-2xl font-bold text-purple-600">{balancesData.balances.back_hours || 0}h</p>
              </div>
              <div className="bg-indigo-50 p-4 rounded-lg">
                <p className="text-sm text-gray-500">Vacation Hours</p>
                <p className="text-2xl font-bold text-indigo-600">{balancesData.balances.vacation_hours || 0}h</p>
              </div>
              <div className="bg-teal-50 p-4 rounded-lg">
                <p className="text-sm text-gray-500">Sick Hours</p>
                <p className="text-2xl font-bold text-teal-600">{balancesData.balances.sick_hours || 0}h</p>
              </div>
            </div>

            {/* Transaction History */}
            {balanceHistory?.transactions?.length > 0 && (
              <div className="mt-6">
                <h3 className="text-sm font-semibold mb-2">Transaction History</h3>
                <div className="space-y-1 max-h-48 overflow-y-auto">
                  {balanceHistory.transactions.map(t => (
                    <div key={t.id} className="flex justify-between items-center p-2 bg-gray-50 rounded text-sm">
                      <div>
                        <span className={`font-medium ${t.action === 'added' ? 'text-green-700' : 'text-red-700'}`}>
                          {t.action === 'added' ? '+' : ''}{t.amount}h {t.type.replace('_', ' ')}
                        </span>
                        <span className="ml-2 text-gray-500 text-xs">
                          by {t.input_by_name || 'system'} · {t.created_at ? new Date(t.created_at).toLocaleString() : ''}
                        </span>
                        {t.reason && <span className="ml-2 text-gray-400 text-xs">— {t.reason}</span>}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Pay Period Selector */}
        {ppList?.pay_periods?.length > 0 && (
          <div className="bg-white rounded-xl shadow-sm p-6 mb-6">
            <h2 className="text-lg font-semibold mb-3">Pay Period</h2>
            <div className="flex flex-wrap gap-4 items-center">
              <select
                value={selectedPpId}
                onChange={(e) => {
                  const ppId = e.target.value
                  setSelectedPpId(ppId)
                  if (ppId) {
                    const selectedPp = ppList.pay_periods.find(p => p.id == ppId)
                    if (selectedPp) {
                      const ppStart = new Date(selectedPp.start_date)
                      const monthDiff = (ppStart.getFullYear() - now.getFullYear()) * 12 + (ppStart.getMonth() - now.getMonth())
                      setMonthOffset(monthDiff)
                    }
                  }
                }}
                className="px-4 py-2 border rounded-lg min-w-48"
              >
                <option value="">Select a pay period...</option>
                {ppList.pay_periods.map(pp => (
                  <option key={pp.id} value={pp.id}>
                    {pp.label} — Pay: {pp.pay_date} ({pp.start_date} → {pp.end_date})
                  </option>
                ))}
              </select>
              {ppData && (
                <div className="grid grid-cols-2 md:grid-cols-6 gap-3 flex-1">
                  <div className="bg-blue-50 p-3 rounded-lg">
                    <p className="text-xs text-gray-500">Total Hours</p>
                    <p className="text-xl font-bold text-blue-600">{ppData.total_hours}</p>
                  </div>
                  <div className="bg-green-50 p-3 rounded-lg">
                    <p className="text-xs text-gray-500">Days Worked</p>
                    <p className="text-xl font-bold text-green-600">{ppData.days_worked}</p>
                  </div>
                  <div className="bg-red-50 p-3 rounded-lg">
                    <p className="text-xs text-gray-500">Late</p>
                    <p className="text-xl font-bold text-red-600">{ppData.late_arrivals}</p>
                  </div>
                  <div className="bg-yellow-50 p-3 rounded-lg">
                    <p className="text-xs text-gray-500">Left Early</p>
                    <p className="text-xl font-bold text-yellow-600">{ppData.left_early}</p>
                  </div>
                  <div className="bg-purple-50 p-3 rounded-lg">
                    <p className="text-xs text-gray-500">Back Hours (balance)</p>
                    <p className="text-xl font-bold text-purple-600">{ppData.back_hours || 0}h</p>
                  </div>
                  <div className="bg-indigo-50 p-3 rounded-lg">
                    <p className="text-xs text-gray-500">Vac Hours (balance)</p>
                    <p className="text-xl font-bold text-indigo-600">{ppData.vacation_hours || 0}h</p>
                  </div>
                  {ppData.sick_hours !== undefined && (
                    <div className="bg-teal-50 p-3 rounded-lg">
                      <p className="text-xs text-gray-500">Sick Hours (balance)</p>
                      <p className="text-xl font-bold text-teal-600">{ppData.sick_hours || 0}h</p>
                    </div>
                  )}
                  {ppData.gross_pay !== null && ppData.gross_pay !== undefined && (
                    <div className="col-span-2 md:col-span-6 bg-emerald-50 p-3 rounded-lg flex justify-between items-center">
                      <div>
                        <p className="text-xs text-gray-500">
                          Gross Pay — ${ppData.hourly_rate}/hr × {(ppData.total_hours + (ppData.back_hours_used || 0) + (ppData.vacation_hours_used || 0) + (ppData.sick_hours_used || 0)).toFixed(2)}h
                        </p>
                        <p className="text-sm text-gray-600">
                          Worked: {ppData.total_hours}h
                          {(ppData.back_hours_used || 0) > 0 && ` + Back used: ${ppData.back_hours_used}h`}
                          {(ppData.vacation_hours_used || 0) > 0 && ` + Vac used: ${ppData.vacation_hours_used}h`}
                          {(ppData.sick_hours_used || 0) > 0 && ` + Sick used: ${ppData.sick_hours_used}h`}
                          {(ppData.back_hours_used || 0) === 0 && (ppData.vacation_hours_used || 0) === 0 && (ppData.sick_hours_used || 0) === 0 && ' (no hours used this period)'}
                        </p>
                      </div>
                      <p className="text-2xl font-bold text-emerald-700">
                        ${ppData.gross_pay.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}
                      </p>
                    </div>
                  )}
                  {ppData.hours_used && ppData.hours_used.length > 0 && (
                    <div className="col-span-2 md:col-span-6 mt-2">
                      <p className="text-sm font-semibold mb-1">Hours Used This Period</p>
                      <div className="space-y-1 max-h-32 overflow-y-auto">
                        {ppData.hours_used.map((h, i) => (
                          <div key={i} className="flex justify-between items-center p-2 bg-gray-50 rounded text-xs">
                            <div>
                              <span className={h.action === 'added' ? 'text-green-700' : 'text-red-700'}>
                                {h.action === 'added' ? '+' : ''}{h.amount}h {h.type.replace('_', ' ')}
                              </span>
                              <span className="ml-2 text-gray-500">
                                by {h.input_by_name || 'system'} · {h.created_at ? new Date(h.created_at).toLocaleString() : ''}
                              </span>
                              {h.reason && <span className="ml-1 text-gray-400">— {h.reason}</span>}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Calendar */}
        <div className="bg-white rounded-xl shadow-sm p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold">{monthName}</h2>
            <div className="flex gap-2">
              <button onClick={() => setMonthOffset(m => m - 1)} className="px-3 py-1 border rounded hover:bg-gray-50 text-sm">← Prev</button>
              <button onClick={() => setMonthOffset(0)} className="px-3 py-1 border rounded hover:bg-gray-50 text-sm">Today</button>
              <button onClick={() => setMonthOffset(m => m + 1)} className="px-3 py-1 border rounded hover:bg-gray-50 text-sm">Next →</button>
            </div>
          </div>

          {calLoading ? (
            <p className="text-center text-gray-500 py-8">Loading calendar...</p>
          ) : (
            <>
              <div className="grid grid-cols-7 gap-1 mb-1">
                {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map(d => (
                  <div key={d} className="text-center text-xs font-medium text-gray-500 py-1">{d}</div>
                ))}
              </div>
              <div className="grid grid-cols-7 gap-1">
                {calendarCells.map((cell, i) => (
                  <div
                    key={i}
                    onClick={() => cell && setSelectedDay(cell)}
                    className={[
                      'min-h-20 p-1 rounded border text-xs transition',
                      cellBg(cell),
                      cell && 'cursor-pointer hover:ring-2 hover:ring-blue-300',
                      cell && isInPayPeriod(cell.date) && 'ring-2 ring-blue-500 border-blue-500',
                    ].filter(Boolean).join(' ')}
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
                ))}
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
          )}
        </div>
      </div>

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
                          <span className="text-sm">{fmtTime(s.in)}</span>
                        </div>
                        <div className="text-gray-400">→</div>
                        <div className="flex items-center gap-3">
                          <span className="text-sm">{fmtTime(s.out)}</span>
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
                ) : selectedDay.is_scheduled ? (
                  <p className="text-gray-500">Not scheduled to work this day.</p>
                ) : (
                  <p className="text-gray-500">No shifts recorded for this day.</p>
                )}
              </div>
            )}
          </div>
        </div>
      )}
      </>
      )}
    </div>
  )
}
