import { useState } from 'react'
import { setAccessKey, setGuest } from '../api'

// Shown when the backend answers 401: the deployed app is locked with one
// access key (APP_ACCESS_KEY on the server). Not an account login, just the key,
// typed once per device and remembered in this browser.
// Without the key, visitors can continue as a guest and look around read-only.
// With `blocked`, the same form is a popup for a guest who tried to change something.
export default function AccessKeyGate({ blocked = false, onClose }) {
  const [key, setKey] = useState('')

  function handleSubmit(e) {
    e.preventDefault()
    if (!key.trim()) return
    setAccessKey(key.trim())
    // Reload so every page loads its data again with the key attached.
    // A wrong key simply brings this screen back.
    window.location.reload()
  }

  function continueAsGuest() {
    setGuest()
    window.location.reload()
  }

  return (
    <div className={`modal-overlay ${blocked ? 'blocked' : 'gate'}`} onClick={blocked ? onClose : undefined}>
      <form className="modal-box" onSubmit={handleSubmit} onClick={e => e.stopPropagation()}>
        {blocked ? (
          <>
            <h3>🔒 Access key needed</h3>
            <div className="sub">
              You're browsing in view-only guest mode, so you can look around but not make changes.
              Enter the access key to unlock this.
            </div>
          </>
        ) : (
          <>
            <h3>💼 Job Hunt Pipeline</h3>
            <div className="sub">Enter your access key to open the app on this device.</div>
          </>
        )}
        <div className="field-row">
          <label htmlFor="accessKey">Access key</label>
          <input
            id="accessKey"
            type="password"
            autoComplete="current-password"
            autoFocus
            value={key}
            onChange={e => setKey(e.target.value)}
          />
        </div>
        <div className="modal-actions">
          {blocked ? (
            <button type="button" className="btn" onClick={onClose}>Close</button>
          ) : (
            <button type="button" className="btn" onClick={continueAsGuest}>👀 View as guest</button>
          )}
          <button type="submit" className="btn primary">Unlock</button>
        </div>
      </form>
    </div>
  )
}
