import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('../../', import.meta.url))
const read = name => readFileSync(`${root}/src/pages/${name}.jsx`, 'utf8')

test('notification center supports list, links, read, and mark-all-read workflows', () => {
  const source = read('NotificationCenter')
  for (const fragment of ['/api/notifications', '/read', '/read-all', 'Mark all as read', 'Notification Center']) assert.ok(source.includes(fragment), fragment)
  assert.match(source, /hour12:\s*true/)
})

test('notification center is routed and linked from the dashboard', () => {
  const app = readFileSync(`${root}/src/App.jsx`, 'utf8')
  const dashboard = read('Dashboard')
  assert.ok(app.includes('NotificationCenter'))
  assert.ok(app.includes('/notifications'))
  assert.ok(dashboard.includes('/notifications'))
})

test('vault exposes category, edit, archive, copy endpoint, and audit workflows', () => {
  const source = read('PasswordVault')
  for (const fragment of ['/categories', '/copy', 'Audit', 'Edit credential', 'Archive credential', 'Manage categories']) assert.ok(source.includes(fragment), fragment)
})

test('tasks expose summary recipient options and category management', () => {
  const source = read('CompanyTasks')
  for (const fragment of ['/send-summary', 'Send Task Summary', 'Manage Categories', 'include_pdf', 'employee_ids', 'external_emails']) assert.ok(source.includes(fragment), fragment)
})

test('calendar exposes event type and color management', () => {
  const source = read('CompanyCalendar')
  for (const fragment of ['/event-types', 'Manage Event Types', 'event_type_id', 'Default color']) assert.ok(source.includes(fragment), fragment)
})
