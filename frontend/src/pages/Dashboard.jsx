import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import { getEmployee, logout, isManager } from '../lib/auth'

export default function Dashboard() {
  const employee = getEmployee()
  const qc = useQueryClient()
  const [monthOffset, setMonthOffset] = useState(0)
  const [emailInput, setEmailInput] = useState('')
  const [emailMsg, setEmailMsg] = useState('')

  // Get current month date range
  const now = new Date()
  const targetMonth = new Date(now.getFullYear(), now.getMonth() + monthOffset, 1)
  const start = new Date(targetMonth.getFullYear(), targetMonth.getMonth(), 1)
  const end = new Date(targetMonth.getFullYear(), targetMonth.getMonth() + 1, 0)
  const startStr = start.toISOString().slice(0, 10)
  const endStr = end.toISOString().slice(0, 10)

  const { data: hoursData, isLoading: hoursLoading } = useQuery({
    queryKey: ['hours', startStr, endStr],
    queryFn: () => api.get('/api/me/hours', { params: { start: startStr, end: endStr } }).then(r => r.data),
  })

  const { data: calData, isLoading: calLoading } = useQuery({
    queryKey: ['calendar', startStr, endStr],
    queryFn: () => api.get('/api/me/calendar', { params: { start: startStr, end: endStr } }).then(r => r.data),
  })

  const { data: profile } = useQuery({
    queryKey: ['profile'],
    queryFn: () => api.get('/api/me/').then(r => r.data),
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
            <span className="text-sm text-gray-600">{employee?.name}</span>
            {isManager() && (
              <a href="/manager" className="text-sm text-blue-600 hover:underline">Manager View</a>
            )}
            <button onClick={logout} className="text-sm text-red-600 hover:underline">Logout</button>
          </div>
        </div>
      </header>

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
            <p className="text-sm text-gray-500">Department</p>
            <p className="text-lg font-bold text-gray-700">{employee?.department || '—'}</p>
          </div>
        </div>

        {/* Navigation */}
        <div className="flex gap-3 mb-6">
          <a href="/time-off" className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium">Request Time Off</a>
          <a href="/documents" className="px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 text-sm font-medium">Documents</a>
        </div>

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
                    className={[
                      'min-h-20 p-1 rounded border text-xs',
                      !cell && 'bg-gray-50 border-gray-100',
                      cell && !cell.worked && 'bg-white border-gray-200',
                      cell?.worked && !cell.is_late && 'bg-green-50 border-green-200',
                      cell?.is_late && 'bg-red-50 border-red-200',
                    ].filter(Boolean).join(' ')}
                  >
                    {cell && (
                      <>
                        <div className="font-medium text-gray-700">{parseInt(cell.date.slice(-2))}</div>
                        {cell.worked && (
                          <div className="mt-1">
                            <div className="text-green-700 font-medium">{cell.total_hours}h</div>
                            {cell.is_late && <div className="text-red-600">Late {cell.late_minutes}m</div>}
                          </div>
                        )}
                      </>
                    )}
                  </div>
                ))}
              </div>
              <div className="flex gap-4 mt-3 text-xs text-gray-600">
                <span className="flex items-center gap-1"><span className="w-3 h-3 bg-green-100 border border-green-300 rounded"></span> Worked</span>
                <span className="flex items-center gap-1"><span className="w-3 h-3 bg-red-100 border border-red-300 rounded"></span> Late</span>
                <span className="flex items-center gap-1"><span className="w-3 h-3 bg-white border border-gray-300 rounded"></span> Not worked</span>
              </div>
            </>
          )}
        </div>

        {/* Shift details for worked days */}
        {workedDays.length > 0 && (
          <div className="bg-white rounded-xl shadow-sm p-6 mt-6">
            <h2 className="text-lg font-semibold mb-3">Recent Shifts</h2>
            <div className="space-y-2">
              {workedDays.slice(-5).reverse().map(day => (
                <div key={day.date} className="flex justify-between items-center p-3 bg-gray-50 rounded-lg">
                  <div>
                    <span className="font-medium">{day.date}</span>
                    {day.is_late && <span className="ml-2 text-red-600 text-sm">⚠ {day.late_minutes}m late</span>}
                  </div>
                  <div className="text-sm text-gray-600">
                    {day.shifts.map((s, i) => (
                      <div key={i}>
                        {s.in?.slice(11, 16)} → {s.out?.slice(11, 16)} ({(s.minutes / 60).toFixed(1)}h)
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
