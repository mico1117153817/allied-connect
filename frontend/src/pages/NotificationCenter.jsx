import React from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'

export function formatNotificationTime(value) {
  return value ? new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short', hour12: true }).format(new Date(value)) : ''
}

export default function NotificationCenter() {
  const qc = useQueryClient()
  const query = useQuery({ queryKey: ['notifications'], queryFn: () => api.get('/api/notifications').then(r => r.data.notifications || []) })
  const refresh = () => qc.invalidateQueries({ queryKey: ['notifications'] })
  const read = useMutation({ mutationFn: id => api.post(`/api/notifications/${id}/read`), onSuccess: refresh })
  const readAll = useMutation({ mutationFn: () => api.post('/api/notifications/read-all'), onSuccess: refresh })
  const rows = query.data || []
  const unread = rows.filter(item => !item.read_at).length
  return <main className="mx-auto max-w-4xl space-y-5 px-3 py-5 sm:px-6">
    <header className="flex flex-wrap items-end justify-between gap-3"><div><p className="text-sm font-semibold text-blue-700">Allied Connect</p><h1 className="text-2xl font-bold text-blue-950">Notification Center</h1><p className="text-sm text-slate-500">{unread ? `${unread} unread notification${unread === 1 ? '' : 's'}` : 'You are all caught up.'}</p></div><div className="flex gap-2"><Link to="/dashboard" className="rounded-lg border px-4 py-2 text-sm">Dashboard</Link><button disabled={!unread || readAll.isPending} onClick={() => readAll.mutate()} className="rounded-lg bg-blue-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">Mark all as read</button></div></header>
    {query.isError && <p role="alert" className="rounded-lg bg-red-50 p-3 text-red-700">Unable to load notifications.</p>}
    <section className="overflow-hidden rounded-xl bg-white shadow-sm">{query.isLoading ? <p className="p-8 text-center text-slate-500">Loading notifications…</p> : <ul className="divide-y">{rows.map(item => <li key={item.id} className={`p-4 sm:p-5 ${item.read_at ? '' : 'bg-blue-50'}`}><div className="flex items-start justify-between gap-4"><div className="min-w-0"><div className="flex items-center gap-2"><h2 className="font-semibold text-blue-950">{item.title}</h2>{!item.read_at && <span className="rounded-full bg-blue-700 px-2 py-0.5 text-xs text-white">New</span>}</div><p className="mt-1 whitespace-pre-wrap text-sm text-slate-600">{item.body}</p><p className="mt-2 text-xs text-slate-400">{formatNotificationTime(item.created_at)}</p></div><div className="flex shrink-0 flex-col gap-2 sm:flex-row">{item.link && <Link to={item.link} onClick={() => !item.read_at && read.mutate(item.id)} className="rounded border px-3 py-2 text-sm font-medium text-blue-700">Open</Link>}{!item.read_at && <button onClick={() => read.mutate(item.id)} className="rounded border px-3 py-2 text-sm">Mark read</button>}</div></div></li>)}{!rows.length && <li className="p-10 text-center text-slate-500">No notifications yet.</li>}</ul>}</section>
  </main>
}
