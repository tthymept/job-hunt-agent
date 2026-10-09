import { useState } from 'react'

const DOW = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const MAX_SHOWN = 2 // company names shown per day before "+N more"

function pad(n) {
  return String(n).padStart(2, '0')
}

export default function Calendar({ jobs = [], onOpenJob }) {
  const today = new Date()
  // The month being viewed lives in state: changing it re-renders the grid
  const [view, setView] = useState({ year: today.getFullYear(), month: today.getMonth() })
  const { year, month } = view

  // Group tracked jobs by deadline: { '2026-10-24': [job, job], ... }
  // Only real ISO dates are used, so "ASAP" or free-text deadlines are skipped
  const byDate = {}
  for (const j of jobs) {
    const match = /^\d{4}-\d{2}-\d{2}/.exec(j.dl || '')
    if (!match) continue
    const key = match[0]
    if (!byDate[key]) byDate[key] = []
    byDate[key].push(j)
  }

  // getDay() is 0 for Sunday; this shifts it so the week starts on Monday
  const leadingBlanks = (new Date(year, month, 1).getDay() + 6) % 7
  // Day 0 of the next month is the last day of this month
  const daysInMonth = new Date(year, month + 1, 0).getDate()
  const todayKey = `${today.getFullYear()}-${pad(today.getMonth() + 1)}-${pad(today.getDate())}`
  const label = new Date(year, month, 1).toLocaleDateString('en-GB', { month: 'long', year: 'numeric' })

  function shiftMonth(delta) {
    // Date handles the wrap-around (December + 1 = January of next year)
    const d = new Date(year, month + delta, 1)
    setView({ year: d.getFullYear(), month: d.getMonth() })
  }

  return (
    <>
      <div className="calhead">
        <button className="btn sm" onClick={() => shiftMonth(-1)}>‹</button>
        <strong>{label}</strong>
        <button className="btn sm" onClick={() => shiftMonth(1)}>›</button>
      </div>
      <div className="calgrid">
        {DOW.map(d => (
          <div className="dow" key={d}>{d}</div>
        ))}
        {Array.from({ length: leadingBlanks }).map((_, i) => (
          <div className="day blank" key={`blank-${i}`} />
        ))}
        {Array.from({ length: daysInMonth }, (_, i) => i + 1).map(d => {
          const key = `${year}-${pad(month + 1)}-${pad(d)}`
          const items = byDate[key] || []
          return (
            <div
              className={`day${items.length ? ' deadline' : ''}${key === todayKey ? ' today' : ''}`}
              key={d}
            >
              {d}
              {items.slice(0, MAX_SHOWN).map(j => (
                <button
                  key={j.trackingId}
                  className="cal-item"
                  title={`${j.co} — ${j.title}`}
                  onClick={() => onOpenJob?.(j)}
                >
                  {j.co}
                </button>
              ))}
              {items.length > MAX_SHOWN && (
                <div className="cal-more">+{items.length - MAX_SHOWN} more</div>
              )}
            </div>
          )
        })}
      </div>
    </>
  )
}