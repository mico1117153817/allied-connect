export function formatTime12Hour(value, fallback = '--') {
  if (!value) return fallback

  const match = String(value).match(/(?:^|T|\s)(\d{1,2}):(\d{2})(?::\d{2})?\s*(AM|PM)?/i)
  if (!match) return fallback

  const hours = Number(match[1])
  const minutes = Number(match[2])
  const existingPeriod = match[3]?.toUpperCase()
  const invalidHours = existingPeriod ? hours < 1 || hours > 12 : hours < 0 || hours > 23
  if (!Number.isInteger(hours) || invalidHours || minutes < 0 || minutes > 59) {
    return fallback
  }

  const period = existingPeriod || (hours >= 12 ? 'PM' : 'AM')
  const standardHour = existingPeriod ? hours : (hours % 12 || 12)
  return `${standardHour}:${String(minutes).padStart(2, '0')} ${period}`
}

export function formatDateTime12Hour(value, options = {}) {
  if (!value) return '--'

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '--'

  return new Intl.DateTimeFormat('en-US', {
    month: 'numeric',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
    ...options,
  }).format(date)
}

export const TIME_OPTIONS = Array.from({ length: 24 * 4 }, (_, index) => {
  const hours = Math.floor(index / 4)
  const minutes = (index % 4) * 15
  const value = `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`
  return { value, label: formatTime12Hour(value) }
})

export function timeOptionsIncluding(value) {
  if (!value || TIME_OPTIONS.some(option => option.value === value)) return TIME_OPTIONS

  const label = formatTime12Hour(value, '')
  if (!label) return TIME_OPTIONS

  return [...TIME_OPTIONS, { value, label }].sort((left, right) => left.value.localeCompare(right.value))
}

export function scheduleTimeAriaLabel(day, boundary) {
  return `${day} ${boundary} time`
}
