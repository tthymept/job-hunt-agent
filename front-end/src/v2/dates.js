// The backend sends dates as text: "2026-11-30" for a real date, or free text
// such as "ASAP" or "—". These helpers only touch the real dates.

// "2026-11-30..." -> a Date at local midnight, or null for anything else
export function parseDay(text) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(text || '')
  return m ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])) : null
}

export function formatDay(date) {
  return date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}

// "2026-11-30" -> "30 Nov 2026"; "ASAP" and "—" pass through unchanged
export function prettyDay(text) {
  const date = parseDay(text)
  return date ? formatDay(date) : text
}

// Whole days from today: 0 is today, negative is in the past
export function daysUntil(date) {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return Math.round((date - today) / 86400000)
}

export function daysLabel(days) {
  if (days < 0) return 'Overdue'
  if (days === 0) return 'Today'
  if (days === 1) return 'Tomorrow'
  return `in ${days} days`
}
