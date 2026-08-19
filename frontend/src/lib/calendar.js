export function formatCalendarDate(dateString, locale = 'en-US') {
  const [year, month, day] = String(dateString).split('-').map(Number)
  const calendarDate = new Date(year, month - 1, day)
  return calendarDate.toLocaleDateString(locale, {
    weekday: 'long', month: 'long', day: 'numeric', year: 'numeric',
  })
}
