import React from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import { logout } from '../lib/auth'

const LICENSE_STATUSES = ['Active', 'Expired', 'Pending', 'Not Held', 'Want to Get']
const BOND_STATUSES = ['Active', 'Expired']

export default function Compliance() {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({ queryKey: ['compliance'], queryFn: () => api.get('/api/compliance').then(r => r.data) })
  const save = useMutation({
    mutationFn: ({ state, payload }) => api.put(`/api/compliance/${encodeURIComponent(state)}`, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['compliance'] }),
  })

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white shadow-sm"><div className="max-w-7xl mx-auto px-4 py-4 flex flex-col gap-3 sm:flex-row sm:justify-between sm:items-center"><div className="flex items-center gap-3"><img src="/allied-logo.jpg" alt="Allied" className="h-10 w-auto rounded" /><h1 className="text-xl font-bold">Compliance</h1></div><div className="flex gap-4"><a href="/manager" className="text-sm text-blue-600 hover:underline">← Manager</a><button onClick={logout} className="text-sm text-red-600 hover:underline">Logout</button></div></div></header>
      <main className="max-w-7xl mx-auto px-4 py-6"><div className="bg-white rounded-xl shadow-sm p-6"><h2 className="text-lg font-semibold">State License & Bond Register</h2><p className="text-sm text-gray-500 mt-1 mb-6">Super-admin access only. Track certificates of authority, state licenses, and bonds held by Allied Alliance Group Inc.</p>
        {isLoading ? <p className="text-gray-500">Loading all 50 states...</p> : <div className="overflow-x-auto"><table className="w-full min-w-[1100px] text-sm"><thead><tr className="border-b text-left text-gray-500"><th className="p-3">State</th><th className="p-3">Certificate of Authority</th><th className="p-3">License</th><th className="p-3">License Number</th><th className="p-3">License Expiration</th><th className="p-3">Bond Held</th><th className="p-3">Bond Amount</th><th className="p-3">Action</th></tr></thead><tbody>{data?.states?.map(row => <ComplianceRow key={row.state} row={row} onSave={(payload) => save.mutate({ state: row.state, payload })} saving={save.isPending} />)}</tbody></table></div>}
      </div></main>
    </div>
  )
}

function ComplianceRow({ row, onSave, saving }) {
  const [form, setForm] = React.useState(row)
  const update = (field, value) => setForm(current => ({ ...current, [field]: value }))
  return <tr className="border-b hover:bg-gray-50"><td className="p-3 font-semibold">{row.state}</td><td className="p-3"><select value={form.certificate_of_authority ? 'Yes' : 'No'} onChange={e => update('certificate_of_authority', e.target.value === 'Yes')} className="px-2 py-2 border rounded"><option>Yes</option><option>No</option></select></td><td className="p-3"><select value={form.license_status} onChange={e => update('license_status', e.target.value)} className="px-2 py-2 border rounded">{LICENSE_STATUSES.map(status => <option key={status}>{status}</option>)}</select></td><td className="p-3"><input value={form.license_number || ''} onChange={e => update('license_number', e.target.value)} className="w-36 px-2 py-2 border rounded" placeholder="License #" /></td><td className="p-3"><input type="date" value={form.license_expiration || ''} onChange={e => update('license_expiration', e.target.value || null)} className="px-2 py-2 border rounded" /></td><td className="p-3"><select value={form.bond_status} onChange={e => update('bond_status', e.target.value)} className="px-2 py-2 border rounded">{BOND_STATUSES.map(status => <option key={status}>{status}</option>)}</select></td><td className="p-3"><input type="number" min="0" step="0.01" value={form.bond_amount ?? ''} onChange={e => update('bond_amount', e.target.value === '' ? null : Number(e.target.value))} className="w-32 px-2 py-2 border rounded" placeholder="$0.00" /></td><td className="p-3"><button onClick={() => onSave({ certificate_of_authority: form.certificate_of_authority, license_status: form.license_status, license_number: form.license_number || null, license_expiration: form.license_expiration || null, bond_status: form.bond_status, bond_amount: form.bond_amount })} disabled={saving} className="px-3 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50">Save</button></td></tr>
}
