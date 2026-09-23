import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { buildSync } from 'esbuild'
import { fileURLToPath, pathToFileURL } from 'node:url'

const root = fileURLToPath(new URL('../../', import.meta.url))
const out = fileURLToPath(new URL('../../node_modules/.cache/company-tasks-contract.mjs', import.meta.url))
buildSync({ entryPoints: [`${root}/src/pages/CompanyTasks.jsx`], bundle: true, platform: 'node', format: 'esm', packages: 'external', loader: { '.jsx': 'jsx' }, define: { 'import.meta.env.VITE_API_URL': '""' }, outfile: out })
const tasks = await import(`${pathToFileURL(out).href}?${Date.now()}`)
const source = readFileSync(`${root}/src/pages/CompanyTasks.jsx`, 'utf8')

test('task filtering spans search, company, status, priority, department, and category', () => {
  const rows = [
    { task_id: 'TASK-1', title: 'File Nevada report', company_id: 1, status: 'In Progress', priority: 'High', department: 'Compliance', category: 'Filing' },
    { task_id: 'TASK-2', title: 'Order supplies', company_id: 2, status: 'Completed', priority: 'Low', department: 'Operations', category: 'Other' },
  ]
  assert.deepEqual(tasks.filterTasks(rows, { search: 'nevada', company: '1', status: 'In Progress', priority: 'High', department: 'Compliance', category: 'Filing' }), [rows[0]])
})

test('task dates use an explicit 12-hour clock', () => {
  assert.match(tasks.formatTaskDate('2030-01-02T15:04:00Z', 'UTC'), /3:04 PM/)
})

test('frontend exposes complete task workflow API contracts', () => {
  for (const fragment of ['/attachments', '/reminders', '/summary.pdf', '/notes', 'assigned_employee_ids', 'state_compliance_id', 'completion_notes']) assert.ok(source.includes(fragment), fragment)
  for (const label of ['Primary Assignee', 'Additional Assignees', 'Archive Task', 'Mark Complete', 'Edit Task']) assert.ok(source.includes(label), label)
})
