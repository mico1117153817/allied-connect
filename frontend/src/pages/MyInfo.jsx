import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import { logout } from '../lib/auth'

const blankProfile = { name: '', address: '', email: '', phone: '', show_in_directory: false }

export default function MyInfo() {
  const qc = useQueryClient()
  const [form, setForm] = useState(blankProfile)
  const [message, setMessage] = useState('')
  const { data, isLoading } = useQuery({ queryKey: ['profile-status'], queryFn: () => api.get('/api/me/profile-status').then(r => r.data) })

  useEffect(() => {
    if (data?.profile) setForm(data.profile)
  }, [data])

  const save = useMutation({
    mutationFn: (payload) => api.put('/api/me/profile', payload).then(r => r.data),
    onSuccess: () => {
      setMessage('Your information has been saved.')
      qc.invalidateQueries({ queryKey: ['profile-status'] })
      qc.invalidateQueries({ queryKey: ['profile'] })
    },
    onError: (err) => setMessage(err.response?.data?.detail || 'Unable to save your information.'),
  })

  const update = (field, value) => setForm(current => ({ ...current, [field]: value }))

  if (isLoading) return <div className="min-h-screen flex items-center justify-center text-gray-500">Loading your information...</div>

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white shadow-sm"><div className="max-w-2xl mx-auto px-4 py-4 flex justify-between items-center"><div className="flex items-center gap-3"><img src="/allied-logo.jpg" alt="Allied" className="h-10 w-auto rounded" /><h1 className="text-xl font-bold">My Info</h1></div><button onClick={logout} className="text-sm text-red-600 hover:underline">Logout</button></div></header>
      <main className="max-w-2xl mx-auto px-4 py-8"><div className="bg-white shadow-sm rounded-xl p-6">
        {!data?.is_complete && <div className="mb-6 border border-blue-200 bg-blue-50 text-blue-900 rounded-lg p-4 text-sm">Complete your information to access Allied Connect.</div>}
        <h2 className="text-lg font-semibold">Personal Information</h2><p className="text-sm text-gray-500 mt-1 mb-6">Management can view all of this information. Only your name and phone number are shown in the employee directory when you opt in.</p>
        <form onSubmit={(e) => { e.preventDefault(); setMessage(''); save.mutate(form) }} className="space-y-4">
          <div><label className="block text-sm font-medium mb-1">Full Name</label><input required value={form.name} onChange={e => update('name', e.target.value)} className="w-full px-3 py-2 border rounded-lg" /></div>
          <div><label className="block text-sm font-medium mb-1">Home Address</label><input required value={form.address} onChange={e => update('address', e.target.value)} className="w-full px-3 py-2 border rounded-lg" /></div>
          <div className="grid sm:grid-cols-2 gap-4"><div><label className="block text-sm font-medium mb-1">Email</label><input required type="email" value={form.email} onChange={e => update('email', e.target.value)} className="w-full px-3 py-2 border rounded-lg" /></div><div><label className="block text-sm font-medium mb-1">Phone Number</label><input required type="tel" value={form.phone} onChange={e => update('phone', e.target.value)} className="w-full px-3 py-2 border rounded-lg" /></div></div>
          <label className="flex gap-3 p-4 border rounded-lg cursor-pointer"><input type="checkbox" checked={form.show_in_directory} onChange={e => update('show_in_directory', e.target.checked)} className="mt-1" /><span><span className="block text-sm font-medium">Include my name and phone number in the employee directory</span><span className="block text-xs text-gray-500 mt-1">Your address and email are never shown in the employee directory.</span></span></label>
          {message && <p className={`text-sm ${message.includes('saved') ? 'text-green-700' : 'text-red-600'}`}>{message}</p>}
          <div className="flex gap-3"><button disabled={save.isPending} className="px-5 py-2 bg-blue-600 text-white rounded-lg disabled:opacity-50">{save.isPending ? 'Saving...' : 'Save My Info'}</button>{data?.is_complete && <a href="/dashboard" className="px-5 py-2 border rounded-lg text-gray-700">Back to Dashboard</a>}</div>
        </form>
      </div></main>
    </div>
  )
}
