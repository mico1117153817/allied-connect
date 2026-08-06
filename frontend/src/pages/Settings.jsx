import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import { logout, isSuperAdmin } from '../lib/auth'

const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
const DOW_NUM = [0, 1, 2, 3, 4, 5, 6]

export default function Settings() {
  const qc = useQueryClient()
  const [editKey, setEditKey] = useState(null)
  const [editValue, setEditValue] = useState('')
  const [msg, setMsg] = useState('')
  const [scheduleEmpId, setScheduleEmpId] = useState('')
  const [scheduleForm, setScheduleForm] = useState({})

  // Bulk schedule state
  const [bulkForm, setBulkForm] = useState({
    0: { start: '09:00', end: '17:00' },
    1: { start: '09:00', end: '17:00' },
    2: { start: '09:00', end: '17:00' },
    3: { start: '09:00', end: '17:00' },
    4: { start: '09:00', end: '17:00' },
    5: { start: '', end: '' },
    6: { start: '', end: '' },
  })
  const [bulkSaving, setBulkSaving] = useState(false)
  const [ppForm, setPpForm] = useState({ pay_date: '', label: '', start_date: '', end_date: '' })
  const [rateEmpId, setRateEmpId] = useState('')
  const [rateValue, setRateValue] = useState('')
  const [rateMsg, setRateMsg] = useState('')
  const [hbEmpId, setHbEmpId] = useState('')
  const [hbData, setHbData] = useState(null)
  const [hbForm, setHbForm] = useState({ type: 'back_hours', amount: '', reason: '' })
  const [hbMsg, setHbMsg] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['settings'],
    queryFn: () => api.get('/api/settings').then(r => r.data),
  })

  const { data: empData } = useQuery({
    queryKey: ['all-employees'],
    queryFn: () => api.get('/api/manager/employees').then(r => r.data),
  })

  const { data: scheduleData, isLoading: scheduleLoading } = useQuery({
    queryKey: ['schedule', scheduleEmpId],
    queryFn: () => api.get(`/api/manager/scheduled-shifts/${scheduleEmpId}`).then(r => r.data),
    enabled: !!scheduleEmpId,
  })

  const { data: ppData, isLoading: ppLoading } = useQuery({
    queryKey: ['pay-periods-mgr'],
    queryFn: () => api.get('/api/manager/pay-periods').then(r => r.data),
  })

  const updateMutation = useMutation({
    mutationFn: ({ key, value }) => api.put('/api/settings', { key, value }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['settings'] })
      setEditKey(null)
      setMsg('Setting saved!')
    },
    onError: () => setMsg('Failed to save setting.'),
  })

  const scheduleMutation = useMutation({
    mutationFn: (data) => api.post('/api/manager/scheduled-shifts', data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['schedule', scheduleEmpId] })
      setMsg('Schedule saved!')
    },
    onError: () => setMsg('Failed to save schedule.'),
  })

  const formatLabel = (key) => key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())

  // Load schedule form when data arrives
  const currentSchedule = {}
  if (scheduleData?.scheduled_shifts) {
    for (const s of scheduleData.scheduled_shifts) {
      currentSchedule[s.day_of_week] = { start: s.start_time, end: s.end_time }
    }
  }

  const handleScheduleSave = (dow) => {
    const entry = scheduleForm[dow]
    if (!entry || !entry.start) {
      setMsg(`Please enter a start time for ${DAYS[dow]}`)
      return
    }
    scheduleMutation.mutate({
      employee_id: scheduleEmpId,
      day_of_week: dow,
      start_time: entry.start,
      end_time: entry.end || '17:00',
      department_id: null,
    })
  }

  const handleBulkSave = async () => {
    setBulkSaving(true)
    setMsg('')
    try {
      const schedules = DOW_NUM
        .filter(dow => bulkForm[dow]?.start)
        .map(dow => ({
          day_of_week: dow,
          start_time: bulkForm[dow].start,
          end_time: bulkForm[dow].end || '17:00',
        }))

      if (schedules.length === 0) {
        setMsg('Please check at least one day.')
        setBulkSaving(false)
        return
      }

      const resp = await api.post('/api/manager/bulk-schedule', { schedules })
      setMsg(`Schedule applied to ${resp.data.employees_updated} employees (${resp.data.total_shifts} shifts)`)
      qc.invalidateQueries({ queryKey: ['schedule', scheduleEmpId] })
    } catch (err) {
      setMsg('Failed to apply schedule.')
    } finally {
      setBulkSaving(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white shadow-sm">
        <div className="max-w-5xl mx-auto px-4 py-4 flex justify-between items-center">
          <div className="flex items-center gap-3">
            <img src="/allied-logo.jpg" alt="Allied" className="h-10 w-auto rounded" />
            <h1 className="text-xl font-bold">Settings</h1>
          </div>
          <div className="flex items-center gap-4">
            <a href="/manager" className="text-sm text-blue-600 hover:underline">← Manager</a>
            <button onClick={logout} className="text-sm text-red-600 hover:underline">Logout</button>
          </div>
        </div>
      </header>

      <div className="max-w-5xl mx-auto px-4 py-6 space-y-6">
        {msg && (
          <div className="bg-green-50 border border-green-200 text-green-700 text-sm px-4 py-2 rounded-lg">
            {msg}
          </div>
        )}

        {/* Late Threshold Setting */}
        <div className="bg-white rounded-xl shadow-sm p-6">
          <h2 className="text-lg font-semibold mb-4">Portal Settings</h2>
          {isLoading ? (
            <p className="text-gray-500">Loading...</p>
          ) : (
          <div className="space-y-4">
              {data?.settings?.map(s => {
                const isThreshold = s.key.includes('minutes')
                return (
                <div key={s.key} className="border rounded-lg p-4">
                  <div className="flex justify-between items-center">
                    <div>
                      <p className="font-medium">{formatLabel(s.key)}</p>
                      <p className="text-xs text-gray-500 mt-1">{s.description}</p>
                    </div>
                    {editKey === s.key ? (
                      <div className="flex gap-2">
                        <input
                          type="number"
                          min="0"
                          value={editValue}
                          onChange={(e) => setEditValue(e.target.value)}
                          className="w-24 px-3 py-1 border rounded text-sm"
                        />
                        <button
                          onClick={() => updateMutation.mutate({ key: s.key, value: editValue })}
                          className="px-3 py-1 bg-green-600 text-white rounded text-sm hover:bg-green-700"
                        >
                          Save
                        </button>
                        <button
                          onClick={() => setEditKey(null)}
                          className="px-3 py-1 border rounded text-sm hover:bg-gray-50"
                        >
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <div className="flex items-center gap-3">
                        <span className="font-bold text-blue-700 text-lg">{s.value}{isThreshold ? ' min' : ''}</span>
                        <button
                          onClick={() => { setEditKey(s.key); setEditValue(s.value) }}
                          className="px-3 py-1 border rounded text-sm hover:bg-gray-50"
                        >
                          Edit
                        </button>
                      </div>
                    )}
                  </div>
                </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Pay Period Management */}
        <div className="bg-white rounded-xl shadow-sm p-6">
          <h2 className="text-lg font-semibold mb-2">Pay Periods</h2>
          <p className="text-sm text-gray-600 mb-4">
            Create pay periods so employees can view their hours by pay cycle. Pay dates are typically the 8th and 22nd of each month.
          </p>

          {/* Create form */}
          <div className="bg-gray-50 p-4 rounded-lg mb-4">
            <h3 className="text-sm font-medium mb-3">Add Pay Period</h3>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
              <div>
                <label className="block text-xs text-gray-500 mb-1">Pay Date</label>
                <input
                  type="date"
                  value={ppForm.pay_date}
                  onChange={(e) => setPpForm({ ...ppForm, pay_date: e.target.value })}
                  className="w-full px-3 py-2 border rounded text-sm"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">Label (e.g. 8/8)</label>
                <input
                  type="text"
                  value={ppForm.label}
                  onChange={(e) => setPpForm({ ...ppForm, label: e.target.value })}
                  placeholder="8/8"
                  className="w-full px-3 py-2 border rounded text-sm"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">Start Date</label>
                <input
                  type="date"
                  value={ppForm.start_date}
                  onChange={(e) => setPpForm({ ...ppForm, start_date: e.target.value })}
                  className="w-full px-3 py-2 border rounded text-sm"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">End Date</label>
                <input
                  type="date"
                  value={ppForm.end_date}
                  onChange={(e) => setPpForm({ ...ppForm, end_date: e.target.value })}
                  className="w-full px-3 py-2 border rounded text-sm"
                />
              </div>
            </div>
            <button
              onClick={async () => {
                if (!ppForm.pay_date || !ppForm.label || !ppForm.start_date || !ppForm.end_date) {
                  setMsg('Please fill in all fields')
                  return
                }
                try {
                  await api.post('/api/manager/pay-periods', ppForm)
                  setMsg('Pay period saved!')
                  setPpForm({ pay_date: '', label: '', start_date: '', end_date: '' })
                  qc.invalidateQueries({ queryKey: ['pay-periods-mgr'] })
                } catch (err) {
                  setMsg('Failed to save pay period')
                }
              }}
              className="mt-3 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium"
            >
              Add Pay Period
            </button>
          </div>

          {/* Existing periods */}
          {ppLoading ? (
            <p className="text-gray-500">Loading...</p>
          ) : ppData?.pay_periods?.length === 0 ? (
            <p className="text-gray-400 text-center py-4">No pay periods created yet.</p>
          ) : (
            <div className="space-y-2">
              {ppData?.pay_periods?.map(p => (
                <div key={p.id} className="flex justify-between items-center p-3 border rounded-lg">
                  <div>
                    <span className="font-medium text-sm">{p.label}</span>
                    <span className="ml-3 text-sm text-gray-500">
                      Pay: {p.pay_date} · Period: {p.start_date} → {p.end_date}
                    </span>
                  </div>
                  <button
                    onClick={async () => {
                      try {
                        await api.delete(`/api/manager/pay-periods/${p.id}`)
                        qc.invalidateQueries({ queryKey: ['pay-periods-mgr'] })
                        setMsg('Pay period deleted')
                      } catch (err) {
                        setMsg('Failed to delete')
                      }
                    }}
                    className="text-red-500 text-sm hover:underline"
                  >
                    Delete
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Schedule Management */}
        <div className="bg-white rounded-xl shadow-sm p-6">
          <h2 className="text-lg font-semibold mb-2">Set Default Schedule for All Employees</h2>
          <p className="text-sm text-gray-600 mb-4">
            Set a schedule template that applies to everyone at once. You can then customize individual employees below.
          </p>
          <div className="space-y-2 mb-4">
            <div className="grid grid-cols-12 gap-2 text-xs font-medium text-gray-500 pb-1 border-b">
              <div className="col-span-3">Day</div>
              <div className="col-span-3">Work Day?</div>
              <div className="col-span-3">Start Time</div>
              <div className="col-span-3">End Time</div>
            </div>
            {DOW_NUM.map(dow => (
              <div key={dow} className="grid grid-cols-12 gap-2 items-center py-1">
                <div className="col-span-3 font-medium text-sm">{DAYS[dow]}</div>
                <div className="col-span-3">
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={!!bulkForm[dow].start}
                      onChange={(e) => {
                        const checked = e.target.checked
                        setBulkForm({
                          ...bulkForm,
                          [dow]: checked
                            ? { start: '09:00', end: '17:00' }
                            : { start: '', end: '' }
                        })
                      }}
                    />
                    {bulkForm[dow].start ? 'Yes' : 'No'}
                  </label>
                </div>
                <div className="col-span-3">
                  <input
                    type="time"
                    value={bulkForm[dow].start}
                    onChange={(e) => setBulkForm({
                      ...bulkForm,
                      [dow]: { ...bulkForm[dow], start: e.target.value }
                    })}
                    disabled={!bulkForm[dow].start}
                    className="w-full px-2 py-1 border rounded text-sm disabled:bg-gray-100"
                  />
                </div>
                <div className="col-span-3">
                  <input
                    type="time"
                    value={bulkForm[dow].end}
                    onChange={(e) => setBulkForm({
                      ...bulkForm,
                      [dow]: { ...bulkForm[dow], end: e.target.value }
                    })}
                    disabled={!bulkForm[dow].start}
                    className="w-full px-2 py-1 border rounded text-sm disabled:bg-gray-100"
                  />
                </div>
              </div>
            ))}
          </div>
          <button
            onClick={handleBulkSave}
            disabled={bulkSaving}
            className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 font-medium text-sm"
          >
            {bulkSaving ? 'Applying...' : 'Apply to All Employees'}
          </button>
        </div>

        {/* Individual Schedule Management */}
        <div className="bg-white rounded-xl shadow-sm p-6">
          <h2 className="text-lg font-semibold mb-2">Individual Employee Schedule</h2>
          <p className="text-sm text-gray-600 mb-4">
            Customize a specific employee's schedule. This overrides the default schedule set above.
          </p>

          <div className="mb-6">
            <label className="block text-sm font-medium text-gray-700 mb-1">Select Employee</label>
            <select
              value={scheduleEmpId}
              onChange={(e) => { setScheduleEmpId(e.target.value); setScheduleForm({}); setMsg('') }}
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

          {!scheduleEmpId ? (
            <p className="text-gray-400 text-center py-4">Select an employee to manage their schedule.</p>
          ) : scheduleLoading ? (
            <p className="text-gray-500">Loading schedule...</p>
          ) : (
            <div className="space-y-2">
              <div className="grid grid-cols-12 gap-2 text-xs font-medium text-gray-500 pb-1 border-b">
                <div className="col-span-2">Day</div>
                <div className="col-span-3">Scheduled?</div>
                <div className="col-span-3">Start Time</div>
                <div className="col-span-2">End Time</div>
                <div className="col-span-2"></div>
              </div>
              {DOW_NUM.map(dow => {
                const existing = currentSchedule[dow]
                const formEntry = scheduleForm[dow] || (existing ? { start: existing.start, end: existing.end } : { start: '', end: '' })
                return (
                  <div key={dow} className="grid grid-cols-12 gap-2 items-center py-1">
                    <div className="col-span-2 font-medium text-sm">{DAYS[dow]}</div>
                    <div className="col-span-3">
                      <label className="flex items-center gap-2 text-sm">
                        <input
                          type="checkbox"
                          checked={!!formEntry.start || !!existing?.start}
                          onChange={(e) => {
                            const checked = e.target.checked
                            setScheduleForm({
                              ...scheduleForm,
                              [dow]: checked
                                ? { start: existing?.start || '09:00', end: existing?.end || '17:00' }
                                : { start: '', end: '' }
                            })
                          }}
                        />
                        {existing?.start ? 'Yes' : 'No'}
                      </label>
                    </div>
                    <div className="col-span-3">
                      <input
                        type="time"
                        value={formEntry.start}
                        onChange={(e) => setScheduleForm({
                          ...scheduleForm,
                          [dow]: { ...formEntry, start: e.target.value }
                        })}
                        disabled={!formEntry.start && !existing?.start}
                        className="w-full px-2 py-1 border rounded text-sm disabled:bg-gray-100"
                      />
                    </div>
                    <div className="col-span-2">
                      <input
                        type="time"
                        value={formEntry.end}
                        onChange={(e) => setScheduleForm({
                          ...scheduleForm,
                          [dow]: { ...formEntry, end: e.target.value }
                        })}
                        disabled={!formEntry.start && !existing?.start}
                        className="w-full px-2 py-1 border rounded text-sm disabled:bg-gray-100"
                      />
                    </div>
                    <div className="col-span-2">
                      <button
                        onClick={() => handleScheduleSave(dow)}
                        disabled={!scheduleForm[dow]?.start}
                        className="px-3 py-1 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 disabled:opacity-50"
                      >
                        {scheduleMutation.isPending ? '...' : 'Save'}
                      </button>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Hour Balance Management (super admin only) */}
        {isSuperAdmin() && (
          <div className="bg-white rounded-xl shadow-sm p-6">
            <h2 className="text-lg font-semibold mb-2">Employee Hour Balances</h2>
            <p className="text-sm text-gray-600 mb-4">
              Add back hours, vacation hours, or sick hours to an employee's balance. Every addition is logged with your name and timestamp.
            </p>
            <div className="mb-4">
              <label className="block text-sm font-medium text-gray-700 mb-1">Select Employee</label>
              <select
                value={hbEmpId}
                onChange={async (e) => {
                  setHbEmpId(e.target.value)
                  if (e.target.value) {
                    const resp = await api.get(`/api/manager/hour-balance/${e.target.value}`)
                    setHbData(resp.data)
                  }
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

            {hbEmpId && hbData && (
              <>
                {/* Current balances */}
                <div className="grid grid-cols-3 gap-4 mb-6">
                  <div className="bg-purple-50 p-3 rounded-lg">
                    <p className="text-xs text-gray-500">Back Hours</p>
                    <p className="text-xl font-bold text-purple-600">{hbData.balances.back_hours || 0}h</p>
                  </div>
                  <div className="bg-indigo-50 p-3 rounded-lg">
                    <p className="text-xs text-gray-500">Vacation Hours</p>
                    <p className="text-xl font-bold text-indigo-600">{hbData.balances.vacation_hours || 0}h</p>
                  </div>
                  <div className="bg-teal-50 p-3 rounded-lg">
                    <p className="text-xs text-gray-500">Sick Hours</p>
                    <p className="text-xl font-bold text-teal-600">{hbData.balances.sick_hours || 0}h</p>
                  </div>
                </div>

                {/* Add hours form */}
                <div className="bg-gray-50 p-4 rounded-lg mb-4">
                  <h3 className="text-sm font-medium mb-3">Add Hours</h3>
                  <div className="flex flex-wrap gap-3 items-end">
                    <div>
                      <label className="block text-xs text-gray-500 mb-1">Type</label>
                      <select
                        value={hbForm.type}
                        onChange={(e) => setHbForm({ ...hbForm, type: e.target.value })}
                        className="px-3 py-2 border rounded text-sm"
                      >
                        <option value="back_hours">Back Hours</option>
                        <option value="vacation_hours">Vacation Hours</option>
                        <option value="sick_hours">Sick Hours</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs text-gray-500 mb-1">Amount (hours)</label>
                      <input
                        type="number"
                        step="0.25"
                        min="0.25"
                        value={hbForm.amount}
                        onChange={(e) => setHbForm({ ...hbForm, amount: e.target.value })}
                        className="w-32 px-3 py-2 border rounded text-sm"
                        placeholder="8"
                      />
                    </div>
                    <div className="flex-1 min-w-48">
                      <label className="block text-xs text-gray-500 mb-1">Reason (optional)</label>
                      <input
                        type="text"
                        value={hbForm.reason}
                        onChange={(e) => setHbForm({ ...hbForm, reason: e.target.value })}
                        className="w-full px-3 py-2 border rounded text-sm"
                        placeholder="Overtime from last week"
                      />
                    </div>
                    <button
                      onClick={async () => {
                        try {
                          await api.post('/api/manager/hour-balance/add', {
                            employee_id: hbEmpId,
                            type: hbForm.type,
                            amount: parseFloat(hbForm.amount),
                            reason: hbForm.reason || null,
                          })
                          setHbMsg('Hours added!')
                          const resp = await api.get(`/api/manager/hour-balance/${hbEmpId}`)
                          setHbData(resp.data)
                          setHbForm({ type: 'back_hours', amount: '', reason: '' })
                        } catch (err) {
                          setHbMsg('Failed to add hours')
                        }
                      }}
                      className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium"
                    >
                      Add Hours
                    </button>
                  </div>
                  {hbMsg && <p className="text-green-600 text-sm mt-2">{hbMsg}</p>}
                </div>

                {/* Transaction history */}
                {hbData.transactions?.length > 0 && (
                  <div>
                    <h3 className="text-sm font-semibold mb-2">Transaction History</h3>
                    <div className="space-y-1 max-h-64 overflow-y-auto">
                      {hbData.transactions.map(t => (
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
              </>
            )}
          </div>
        )}

        {/* Hourly Rate Management (super admin only) */}
        {isSuperAdmin() && (
          <div className="bg-white rounded-xl shadow-sm p-6">
            <h2 className="text-lg font-semibold mb-2">Employee Hourly Rates</h2>
            <p className="text-sm text-gray-600 mb-4">
              Set private hourly rates for gross pay calculations. Only super admins can see and set these rates. Employees see their own rate and gross pay when they view a pay period — no other employees can see it.
            </p>
            <div className="mb-4">
              <label className="block text-sm font-medium text-gray-700 mb-1">Select Employee</label>
              <select
                value={rateEmpId}
                onChange={(e) => { setRateEmpId(e.target.value); setRateMsg('') }}
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
            {rateEmpId && (
              <div className="flex gap-3 items-end">
                <div>
                  <label className="block text-xs text-gray-500 mb-1">Hourly Rate ($)</label>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={rateValue}
                    onChange={(e) => setRateValue(e.target.value)}
                    placeholder="25.00"
                    className="w-32 px-3 py-2 border rounded text-sm"
                  />
                </div>
                <button
                  onClick={async () => {
                    try {
                      await api.put('/api/manager/hourly-rate', { employee_id: rateEmpId, hourly_rate: rateValue })
                      setRateMsg('Rate saved!')
                      qc.invalidateQueries({ queryKey: ['hourly-rate', rateEmpId] })
                    } catch (err) {
                      setRateMsg('Failed to save rate')
                    }
                  }}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium"
                >
                  Save Rate
                </button>
              </div>
            )}
            {rateMsg && <p className="text-green-600 text-sm mt-2">{rateMsg}</p>}
          </div>
        )}

        {/* Legend */}
        <div className="bg-white rounded-xl shadow-sm p-6">
          <h2 className="text-lg font-semibold mb-4">Calendar Legend</h2>
          <div className="space-y-2 text-sm text-gray-600">
            <p><span className="inline-block w-4 h-4 bg-green-100 border border-green-300 rounded mr-2 align-middle"></span> Worked (on time)</p>
            <p><span className="inline-block w-4 h-4 bg-red-100 border border-red-300 rounded mr-2 align-middle"></span> Late arrival (after threshold)</p>
            <p><span className="inline-block w-4 h-4 bg-orange-100 border border-orange-300 rounded mr-2 align-middle"></span> Missed day (scheduled but didn't work)</p>
            <p><span className="inline-block w-4 h-4 bg-yellow-100 border border-yellow-400 rounded mr-2 align-middle"></span> Left early (before scheduled end time)</p>
            <p><span className="inline-block w-4 h-4 bg-white border border-gray-300 rounded mr-2 align-middle"></span> Not scheduled / not worked</p>
          </div>
        </div>
      </div>
    </div>
  )
}
