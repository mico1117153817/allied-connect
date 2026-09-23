import React from 'react'

const links = [
  ['/compliance', 'Compliance'],
  ['/company-tasks', 'Company Tasks'],
  ['/company-calendar', 'Company Calendar'],
  ['/password-vault', 'Password Vault'],
]

export default function WorkflowNav() {
  return <nav aria-label="Company management" className="border-b border-slate-200 bg-white shadow-sm">
    <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-5 gap-y-2 px-3 py-3 text-sm sm:px-6">
      <a href="/dashboard" className="font-semibold text-blue-800 hover:underline">← Dashboard</a>
      {links.map(([href, label]) => <a key={href} href={href} className="font-medium text-slate-700 hover:text-blue-700 hover:underline">{label}</a>)}
    </div>
  </nav>
}
