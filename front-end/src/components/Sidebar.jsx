const NAV_ITEMS = [
  { key: 'dashboard', label: '⬛ Dashboard' },
  { key: 'explore', label: '🔍 Explore Jobs' },
  { key: 'cv', label: '📄 My CV' },
]

// Old version: one addEventListener on #nav that read data-view off
// whichever button was clicked, then manually toggled .active classes
// on buttons AND on .view sections elsewhere in the document.
// Here: view is just a piece of state. Clicking a button calls
// setView(), and the "active" class + which page shows are both
// derived from that one value - no manual class-toggling anywhere.
export default function Sidebar({ view, setView }) {
  return (
    <aside className="sidebar">
      <div className="brand"><span className="mark">💼</span> Job Hunt Pipeline</div>
      <nav className="nav">
        {NAV_ITEMS.map(item => (
          <button
            key={item.key}
            className={view === item.key ? 'active' : ''}
            onClick={() => setView(item.key)}
          >
            {item.label}
          </button>
        ))}
      </nav>
      <div className="tip"><b>Pipeline tip</b>Keep deadlines current to see them in your calendar.</div>
      <div className="who">
        <span className="dot">AT</span>
        <div>Alex Tan<br/><span style={{ color: 'var(--sub)', fontSize: '11.5px' }}>alex.tan@email.com</span></div>
      </div>
    </aside>
  )
}
