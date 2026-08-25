import test from 'node:test'
import assert from 'node:assert/strict'

import {
  TIME_OPTIONS,
  formatDateTime12Hour,
  formatTime12Hour,
  scheduleTimeAriaLabel,
  timeOptionsIncluding,
} from './time.js'

test('formatTime12Hour displays standard time for midnight, noon, morning, and afternoon', () => {
  assert.equal(formatTime12Hour('00:00'), '12:00 AM')
  assert.equal(formatTime12Hour('12:00'), '12:00 PM')
  assert.equal(formatTime12Hour('09:30'), '9:30 AM')
  assert.equal(formatTime12Hour('17:45'), '5:45 PM')
})

test('formatTime12Hour formats ISO punch timestamps without changing their recorded clock time', () => {
  assert.equal(formatTime12Hour('2026-08-25T13:05:00'), '1:05 PM')
  assert.equal(formatTime12Hour('2026-08-25T07:00:00-04:00'), '7:00 AM')
  assert.equal(formatTime12Hour(null), '--')
  assert.equal(formatTime12Hour('not-a-time'), '--')
})

test('formatTime12Hour preserves an existing AM or PM designation', () => {
  assert.equal(formatTime12Hour('08/25/2026 1:05 PM'), '1:05 PM')
  assert.equal(formatTime12Hour('08/25/2026 9:30 am'), '9:30 AM')
})

test('formatDateTime12Hour explicitly uses a 12-hour clock', () => {
  const formatted = formatDateTime12Hour('2026-08-25T17:45:00Z', { timeZone: 'UTC' })
  assert.match(formatted, /5:45 PM/)
  assert.doesNotMatch(formatted, /17:45/)
})

test('schedule options keep canonical values but show 12-hour labels', () => {
  assert.equal(TIME_OPTIONS.length, 96)
  assert.deepEqual(TIME_OPTIONS[0], { value: '00:00', label: '12:00 AM' })
  assert.deepEqual(TIME_OPTIONS[36], { value: '09:00', label: '9:00 AM' })
  assert.deepEqual(TIME_OPTIONS[48], { value: '12:00', label: '12:00 PM' })
  assert.deepEqual(TIME_OPTIONS[68], { value: '17:00', label: '5:00 PM' })
})

test('schedule options preserve an existing custom minute value', () => {
  const options = timeOptionsIncluding('08:05')
  assert.deepEqual(options.find(option => option.value === '08:05'), {
    value: '08:05',
    label: '8:05 AM',
  })
  assert.equal(options.filter(option => option.value === '09:00').length, 1)
})

test('schedule controls receive descriptive accessible names', () => {
  assert.equal(scheduleTimeAriaLabel('Monday', 'start'), 'Monday start time')
  assert.equal(scheduleTimeAriaLabel('Friday', 'end'), 'Friday end time')
})
