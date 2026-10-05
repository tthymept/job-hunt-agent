// Old version: renderCalendar() built one big HTML string and shoved
// it into #calgrid.innerHTML. Here it's just JSX - map over an array,
// return elements. No string-building, no innerHTML.
export default function Calendar({ deadlineDays = [] }) {
  const leadingBlanks = 3 // October 2026 starts on a Thursday
  const days = Array.from({ length: 31 }, (_, i) => i + 1)

  return (
    <>
      <div className="calhead">
        <button className="btn sm">‹</button>
        <strong>October 2026</strong>
        <button className="btn sm">›</button>
      </div>
      <div className="calgrid">
        {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map(d => (
          <div className="dow" key={d}>{d}</div>
        ))}
        {Array.from({ length: leadingBlanks }).map((_, i) => (
          <div className="day blank" key={`blank-${i}`} />
        ))}
        {days.map(d => {
          const isDeadline = deadlineDays.includes(d)
          return (
            <div className={`day${isDeadline ? ' deadline' : ''}`} key={d}>
              {d}
              {isDeadline && <span className="dot" />}
            </div>
          )
        })}
      </div>
    </>
  )
}
