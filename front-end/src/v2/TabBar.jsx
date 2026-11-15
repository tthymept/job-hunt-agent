import { useRef, useState } from 'react'
import Icon from './Icon'

// The dashboard's tabs. Each tab is its own list of tracked jobs. The tab you
// are looking at has a menu to rename it, make it the default, turn adding
// jobs on or off, or delete it.
export default function TabBar({ tabs, activeId, counts, onSelect, actions, error, onDismissError }) {
  const [menuOpen, setMenuOpen] = useState(false)
  // null, 'new' while naming a new tab, or the id of the tab being renamed
  const [editing, setEditing] = useState(null)
  const [draft, setDraft] = useState('')

  const enabledCount = tabs.filter(t => t.enabled).length

  // The name box calls commit() on Enter and again when it loses focus, which
  // also happens when the box is removed after a save. These refs are read at
  // call time (state would be stale inside the old box's handler), so only the
  // first call sends anything and one name never creates two tabs.
  const open = useRef(false) // a name box is on screen and not yet saved or cancelled
  const saving = useRef(false)

  function startNew() {
    open.current = true
    setDraft('')
    setEditing('new')
  }

  function startRename(tab) {
    open.current = true
    setMenuOpen(false)
    setDraft(tab.name)
    setEditing(tab.id)
  }

  function closeEdit() {
    open.current = false
    setEditing(null)
  }

  async function commit(fromBlur) {
    if (!open.current || saving.current) return
    const name = draft.trim()
    const unchanged = editing !== 'new' && name === tabs.find(t => t.id === editing)?.name
    if (!name || unchanged) {
      closeEdit()
      return
    }
    saving.current = true
    try {
      const ok = editing === 'new' ? await actions.create(name) : await actions.rename(editing, name)
      // Refused (e.g. the name is taken): the message shows under the tabs. After
      // Enter the box stays open to fix the name; after clicking away it closes.
      if (ok || fromBlur) closeEdit()
    } finally {
      saving.current = false
    }
  }

  function cancelEdit() {
    if (!saving.current) closeEdit()
  }

  const nameInput = (
    <input
      className="tab-input"
      type="text"
      aria-label="Tab name"
      placeholder="Tab name"
      maxLength={40}
      autoFocus
      value={draft}
      onChange={e => setDraft(e.target.value)}
      onFocus={e => e.target.select()}
      onBlur={() => commit(true)}
      onKeyDown={e => {
        if (e.key === 'Enter') commit(false)
        if (e.key === 'Escape') cancelEdit()
      }}
    />
  )

  function runFromMenu(action) {
    setMenuOpen(false)
    action()
  }

  return (
    <div className="tabbar">
      <div className="tabs" role="tablist" aria-label="Dashboard tabs">
        {tabs.map(tab => {
          const active = tab.id === activeId
          const count = counts[tab.id] || 0
          if (editing === tab.id) return <div className="tab editing" key={tab.id}>{nameInput}</div>
          return (
            <div className={`tab${active ? ' active' : ''}${tab.enabled ? '' : ' off'}`} key={tab.id}>
              <button
                className="tab-main"
                role="tab"
                aria-selected={active}
                title={active ? 'Double-click to rename' : undefined}
                onClick={() => onSelect(tab.id)}
                onDoubleClick={() => startRename(tab)}
              >
                <span className="tab-name">{tab.name}</span>
                <span className="count">{count}</span>
                {tab.isDefault && tabs.length > 1 && <span className="tab-flag">Default</span>}
                {!tab.enabled && <span className="tab-flag">Adding off</span>}
              </button>
              {active && (
                <div className="popwrap">
                  <button
                    className="iconbtn"
                    aria-label={`Options for ${tab.name}`}
                    aria-expanded={menuOpen}
                    onClick={() => setMenuOpen(open => !open)}
                  >
                    <Icon name="more" />
                  </button>
                  {menuOpen && (
                    <>
                      {/* Invisible layer behind the menu: a click anywhere else closes it */}
                      <div className="pop-shade" onClick={() => setMenuOpen(false)} />
                      <div className="popover menu" role="menu">
                        <button role="menuitem" className="menu-item" onClick={() => startRename(tab)}>Rename</button>
                        <button
                          role="menuitem"
                          className="menu-item"
                          disabled={tab.isDefault}
                          onClick={() => runFromMenu(() => actions.setDefault(tab.id))}
                        >
                          {tab.isDefault ? <>Default tab <Icon name="check" size={14} /></> : 'Set as default'}
                          <span className="menu-hint">Opens first and is pre-selected when you add a job.</span>
                        </button>
                        <button
                          role="menuitem"
                          className="menu-item"
                          disabled={tab.enabled && enabledCount === 1}
                          onClick={() => runFromMenu(() => actions.setEnabled(tab.id, !tab.enabled))}
                        >
                          {tab.enabled ? 'Turn off adding jobs' : 'Turn on adding jobs'}
                          <span className="menu-hint">
                            {tab.enabled && enabledCount === 1
                              ? 'At least one tab has to accept new jobs.'
                              : tab.enabled
                                ? 'The tab stays visible and editable.'
                                : 'New jobs can go into this tab again.'}
                          </span>
                        </button>
                        <div className="menu-sep" role="separator" />
                        <button
                          role="menuitem"
                          className="menu-item danger"
                          disabled={count > 0 || tabs.length === 1}
                          onClick={() => runFromMenu(() => actions.remove(tab.id))}
                        >
                          Delete tab
                          {(count > 0 || tabs.length === 1) && (
                            <span className="menu-hint">
                              {tabs.length === 1 ? 'You need at least one tab.' : 'Only an empty tab can be deleted.'}
                            </span>
                          )}
                        </button>
                      </div>
                    </>
                  )}
                </div>
              )}
            </div>
          )
        })}
        {editing === 'new' ? (
          <div className="tab editing">{nameInput}</div>
        ) : (
          <button className="tab-add" onClick={startNew}><Icon name="plus" size={14} /> New tab</button>
        )}
      </div>
      {error && (
        <div className="tab-error" role="alert">
          {error}
          <button className="iconbtn" aria-label="Dismiss" onClick={onDismissError}><Icon name="close" size={14} /></button>
        </div>
      )}
    </div>
  )
}
