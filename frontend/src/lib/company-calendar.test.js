import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const source = readFileSync(new URL('../pages/CompanyCalendar.jsx', import.meta.url), 'utf8')

test('calendar uses the company calendar API contract for events, detail, edits and attachments', () => {
  assert.match(source, /api\.get\('\/api\/company-calendar'/)
  assert.match(source, /api\.post\('\/api\/company-calendar'/)
  assert.match(source, /api\.put\(`\/api\/company-calendar\/\$\{[^}]+\}`/)
  assert.match(source, /api\.get\(`\/api\/company-calendar\/events\/\$\{[^}]+\}`/)
  assert.match(source, /api\.post\(`\/api\/company-calendar\/events\/\$\{[^}]+\}\/attachments`/)
  assert.match(source, /new FormData\(\)/)
})

test('calendar exposes responsive month, week and day controls plus complete event fields', () => {
  for (const label of ['Previous', 'Today', 'Next', 'Event title', 'Description', 'Start', 'End', 'All day', 'Color', 'Notes', 'Reminder', 'Attendees']) {
    assert.ok(source.includes(label), `missing ${label}`)
  }
  assert.match(source, /\['month', 'week', 'day'\]/)
  assert.match(source, /hour12:\s*true/)
  assert.match(source, /grid-cols-7/)
})

test('task calendar entries remain distinguishable and update through their source reference', () => {
  assert.match(source, /source_type\s*===\s*'task'/)
  assert.match(source, /event\.id/)
  assert.match(source, /start_at/)
  assert.match(source, /Task deadline/)
})
