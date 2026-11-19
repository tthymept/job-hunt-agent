import Icon from './Icon'

const NAV_ITEMS = [
  { key: 'dashboard', icon: 'dashboard', label: 'Dashboard' },
  { key: 'explore', icon: 'search', label: 'Explore Jobs', short: 'Explore' },
  { key: 'cv', icon: 'file', label: 'My CV' },
]

function initials(name) {
  return (name || '')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map(part => part[0].toUpperCase())
    .join('') || '?'
}

export default function Sidebar({ view, setView, me, guest, onUnlock, onLogout }) {
  return (
    <aside className="sidebar">
      <div className="brand">
        {/* Same shapes as public/favicon.svg, so the logo matches the browser tab */}
        <span className="mark">
          <svg width="28" height="28" viewBox="0 0 32 32" aria-hidden="true">
            <path d="M8 16h16" stroke="currentColor" strokeWidth="2" />
            <circle cx="8" cy="16" r="3" fill="currentColor" />
            <circle cx="16" cy="16" r="3" fill="currentColor" />
            <circle cx="24" cy="16" r="3.8" fill="var(--mark-dot)" />
          </svg>
        </span>
        <span className="brand-name">Job Hunt Pipeline</span>
      </div>
      <nav className="nav" aria-label="Main">
        {NAV_ITEMS.map(item => (
          <button
            key={item.key}
            className={view === item.key ? 'active' : ''}
            aria-current={view === item.key ? 'page' : undefined}
            onClick={() => setView(item.key)}
          >
            <Icon name={item.icon} size={17} />
            <span className="nav-label">{item.label}</span>
            <span className="nav-short">{item.short || item.label}</span>
          </button>
        ))}
      </nav>
      {guest && (
        <div className="guest-note">
          <b><Icon name="eye" size={14} /> Guest view</b>
          You can look around, but changes need the access key.
          <button className="btn sm" onClick={onUnlock}><Icon name="lock" size={13} /> Enter key</button>
        </div>
      )}
      {me && (
        <button className="who" title="Log out" onClick={onLogout}>
          <span className="avatar">{initials(me.name)}</span>
          <span className="who-text">
            <span className="who-name">{me.name}</span>
            <span className="who-mail">{me.email}</span>
          </span>
          <span className="who-out"><Icon name="logout" size={15} /></span>
        </button>
      )}
    </aside>
  )
}
