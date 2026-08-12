import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { logout, isManager } from '../lib/auth'

export default function EmployeeDirectory() {
  const { data, isLoading } = useQuery({ queryKey: ['employee-directory'], queryFn: () => api.get('/api/me/directory').then(r => r.data) })
  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white shadow-sm"><div className="max-w-4xl mx-auto px-4 py-4 flex justify-between items-center"><div className="flex items-center gap-3"><img src="/allied-logo.jpg" alt="Allied" className="h-10 w-auto rounded" /><h1 className="text-xl font-bold">Employee Directory</h1></div><div className="flex gap-4"><a href={isManager()?'/manager':'/dashboard'} className="text-sm text-blue-600 hover:underline">← Back</a><button onClick={logout} className="text-sm text-red-600 hover:underline">Logout</button></div></div></header>
      <main className="max-w-5xl mx-auto px-4 py-6"><div className="bg-white rounded-xl shadow-sm p-6"><h2 className="text-lg font-semibold">{data?.is_management_view ? 'All Employee Information' : 'Team Contacts'}</h2><p className="text-sm text-gray-500 mt-1 mb-5">{data?.is_management_view ? 'Management can view complete contact information for every employee.' : 'Managers and super admins are always listed. Other employees appear only when they opt in.'}</p>{isLoading?<p className="text-gray-500">Loading directory...</p>:data?.employees?.length===0?<p className="text-gray-400 text-center py-8">No employee information is available yet.</p>:<div className="divide-y">{data.employees.map(person=><div key={person.employee_id || `${person.name}-${person.phone}`} className="py-4 grid grid-cols-1 sm:grid-cols-2 gap-3 items-center"><div><span className="block font-medium text-gray-900">{person.name}</span>{person.role && <span className="text-xs uppercase tracking-wide text-gray-500">{person.role.replace('_',' ')}</span>}</div>{data.is_management_view?<div className="text-sm text-gray-700"><p>{person.phone}</p><p>{person.email}</p><p>{person.address}</p></div>:<a href={`tel:${person.phone}`} className="text-blue-600 hover:underline">{person.phone}</a>}</div>)}</div>}</div></main>
    </div>
  )
}
