import { useState } from 'react'
import Icon from './Icon'
import { AGENDA_KINDS, agendaItems } from './stages'

const DOW = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const MAX_SHOWN = 2 // company names shown per day before "+N more"

function pad(n) {
  return String(n).padStart(2, '0')
}

// onOpenJob(job, tab): an application deadline opens the job's details, an OA,
// interview or offer opens its Progress tab
export default function Calendar({ jobs = [], onOpenJob }) {
  const today = new Date()
  // The month being viewed lives in state: changing it re-renders the grid
  const [view, setView] = useState({ year: today.getFullYear(), month: today.getMonth() })
  const { year, month } = view

  // Group what's coming up by day: { '2026-10-24': [item, item], ... }.
  // "ASAP" and free-text deadlines have no date, so they don't appear.
  const byDate = {}
  for (const item of agendaItems(jobs)) {
    const key = `${item.date.getFullYear()}-${pad(item.date.getMonth() + 1)}-${pad(item.date.getDate())}`
    if (!byDate[key]) byDate[key] = []
    byDate[key].push(item)
  }

  // getDay() is 0 for Sunday; this shifts it so the week starts on Monday
  const leadingBlanks = (new Date(year, month, 1).getDay() + 6) % 7
  // Day 0 of the next month is the last day of this month
  const daysInMonth = new Date(year, month + 1, 0).getDate()
  const todayKey = `${today.getFullYear()}-${pad(today.getMonth() + 1)}-${pad(today.getDate())}`
  const label = new Date(year, month, 1).toLocaleDateString('en-GB', { month: 'long', year: 'numeric' })
  const onThisMonth = year === today.getFullYear() && month === today.getMonth()

  function shiftMonth(delta) {
    // Date handles the wrap-around (December + 1 = January of next year)
    const d = new Date(year, month + delta, 1)
    setView({ year: d.getFullYear(), month: d.getMonth() })
  }

  return (
    <>
      <div className="calhead">
        <strong>{label}</strong>
        <div className="calnav">
          {!onThisMonth && (
            <button className="btn sm quiet" onClick={() => setView({ year: today.getFullYear(), month: today.getMonth() })}>
              Today
            </button>
          )}
          <button className="iconbtn" aria-label="Previous month" onClick={() => shiftMonth(-1)}><Icon name="chevronLeft" /></button>
          <button className="iconbtn" aria-label="Next month" onClick={() => shiftMonth(1)}><Icon name="chevronRight" /></button>
        </div>
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
            <div className={`day${key === todayKey ? ' today' : ''}`} key={d}>
              <span className="daynum">{d}</span>
              {items.slice(0, MAX_SHOWN).map(item => (
                <button
                  key={item.key}
                  className={`cal-item k-${item.kind}`}
                  title={`${AGENDA_KINDS[item.kind].label}${item.time ? ` ${item.time}` : ''}: ${item.job.co} — ${item.job.title}`}
                  onClick={() => onOpenJob?.(item.job, AGENDA_KINDS[item.kind].tab)}
                >
                  {item.job.co}
                </button>
              ))}
              {items.length > MAX_SHOWN && (
                <div className="cal-more">+{items.length - MAX_SHOWN} more</div>
              )}
            </div>
          )
        })}
        {/* Blank cells after the last day, so the final week is a full row */}
        {Array.from({ length: (7 - ((leadingBlanks + daysInMonth) % 7)) % 7 }).map((_, i) => (
          <div className="day blank" key={`tail-${i}`} />
        ))}
      </div>
      <div className="cal-legend">
        {Object.entries(AGENDA_KINDS).map(([kind, k]) => (
          <span key={kind}><i className={`cal-swatch k-${kind}`} />{k.label}</span>
        ))}
      </div>
    </>
  )
}
