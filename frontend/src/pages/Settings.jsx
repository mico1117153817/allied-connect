import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import { logout } from '../lib/auth'

export default function Settings() {
  const qc = useQueryClient()
  const [editKey, setEditKey] = useState(null)
  const [editValue, setEditValue] = useState('')
  const [msg, setMsg] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['settings'],
    queryFn: () => api.get('/api/settings').then(r => r.data),
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

  const formatLabel = (key) => {
    return key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white shadow-sm">
        <div className="max-w-3xl mx-auto px-4 py-4 flex justify-between items-center">
          <h1 className="text-xl font-bold">Settings</h1>
          <div className="flex items-center gap-4">
            <a href="/manager" className="text-sm text-blue-600 hover:underline">← Manager</a>
            <button onClick={logout} className="text-sm text-red-600 hover:underline">Logout</button>
          </div>
        </div>
      </header>

      <div className="max-w-3xl mx-auto px-4 py-6">
        <div className="bg-white rounded-xl shadow-sm p-6">
          <h2 className="text-lg font-semibold mb-4">Portal Settings</h2>
          {isLoading ? (
            <p className="text-gray-500">Loading...</p>
          ) : (
            <div className="space-y-4">
              {data?.settings?.map(s => (
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
                        <span className="font-bold text-blue-700 text-lg">{s.value}{s.key.includes('minutes') ? ' min' : ''}</span>
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
              ))}
            </div>
          )}
          {msg && <p className="text-green-600 text-sm mt-4">{msg}</p>}
        </div>

        <div className="bg-white rounded-xl shadow-sm p-6 mt-6">
          <h2 className="text-lg font-semibold mb-4">Manager Quick Reference</h2>
          <div className="text-sm text-gray-600 space-y-1">
            <p><strong>Late Threshold:</strong> Employees clocking in more than the threshold minutes after their scheduled start will be flagged as "late" on their calendar.</p>
            <p><strong>Default:</strong> 1 minute</p>
            <p><strong>To set schedules:</strong> Use the Manager dashboard to set scheduled start times per employee per day of week. Late detection only works when a schedule is set.</p>
          </div>
        </div>
      </div>
    </div>
  )
}
