import test from 'node:test'
import assert from 'node:assert/strict'

import { formatCalendarDate } from './calendar.js'

test('formatCalendarDate preserves calendar date without timezone shift', () => {
  assert.equal(formatCalendarDate('2026-08-03'), 'Monday, August 3, 2026')
})
