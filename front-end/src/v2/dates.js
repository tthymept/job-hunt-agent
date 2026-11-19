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

// Timestamps from the server (status history, interview times) are full ISO
// strings. These read them on this device's calendar and clock.

// A timestamp -> a Date at local midnight of its day, or null
export function dayOf(iso) {
  if (!iso) return null
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return null
  d.setHours(0, 0, 0, 0)
  return d
}

// Whole days from one day to another (rounded, so a clock change doesn't matter)
export function daysBetween(from, to) {
  return Math.round((to - from) / 86400000)
}

export function today() {
  const d = new Date()
  d.setHours(0, 0, 0, 0)
  return d
}

// "Fri 21 Nov"
export function shortDay(date) {
  return date.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' })
}

// "14:30"
export function timeOf(date) {
  return date.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
}

const pad = n => String(n).padStart(2, '0')

// A timestamp as the "YYYY-MM-DD" a date field shows, or ''
export function toDateInput(iso) {
  const d = iso ? new Date(iso) : null
  if (!d || Number.isNaN(d.getTime())) return ''
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

// A timestamp as the "YYYY-MM-DDTHH:mm" a date-and-time field shows, or ''
export function toDateTimeInput(iso) {
  const d = iso ? new Date(iso) : null
  if (!d || Number.isNaN(d.getTime())) return ''
  return `${toDateInput(iso)}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}
