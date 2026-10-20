const NAV_ITEMS = [
  { key: 'dashboard', icon: '⬛', label: 'Dashboard' },
  { key: 'explore', icon: '🔍', label: 'Explore Jobs', short: 'Explore' },
  { key: 'cv', icon: '📄', label: 'My CV' },
]

function initials(name) {
  return (name || '')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map(part => part[0].toUpperCase())
    .join('') || '?'
}

// Old version: one addEventListener on #nav that read data-view off
// whichever button was clicked, then manually toggled .active classes
// on buttons AND on .view sections elsewhere in the document.
// Here: view is just a piece of state. Clicking a button calls
// setView(), and the "active" class + which page shows are both
// derived from that one value - no manual class-toggling anywhere.
export default function Sidebar({ view, setView, me, guest, onUnlock, onLogout }) {
  return (
    <aside className="sidebar">
      <div className="brand"><span className="mark">💼</span> <span className="brand-name">Job Hunt Pipeline</span></div>
      <nav className="nav">
        {NAV_ITEMS.map(item => (
          <button
            key={item.key}
            className={view === item.key ? 'active' : ''}
            onClick={() => setView(item.key)}
          >
            <span className="nav-icon">{item.icon}</span>
            <span className="nav-label">{item.label}</span>
            <span className="nav-short">{item.short || item.label}</span>
          </button>
        ))}
      </nav>
      {guest ? (
        <div className="tip">
          <b>👀 Guest view</b>You can look around, but changes need the access key.
          <button className="btn sm" style={{ marginTop: 8 }} onClick={onUnlock}>🔒 Enter key</button>
        </div>
      ) : (
        <div className="tip"><b>Pipeline tip</b>Keep deadlines current to see them in your calendar.</div>
      )}
      {me && (
        <button className="who" title="Log out" onClick={onLogout}>
          <span className="dot">{initials(me.name)}</span>
          <div className="who-text">
            {me.name}<br/><span style={{ color: 'var(--sub)', fontSize: '11.5px' }}>{me.email}</span>
          </div>
        </button>
      )}
    </aside>
  )
}
