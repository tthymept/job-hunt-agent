import { useState } from 'react'
import { setAccessKey } from '../api'

// Shown when the backend answers 401: the deployed app is locked with one
// access key (APP_ACCESS_KEY on the server). Not an account login, just the key,
// typed once per device and remembered in this browser.
export default function AccessKeyGate() {
  const [key, setKey] = useState('')

  function handleSubmit(e) {
    e.preventDefault()
    if (!key.trim()) return
    setAccessKey(key.trim())
    // Reload so every page loads its data again with the key attached.
    // A wrong key simply brings this screen back.
    window.location.reload()
  }

  return (
    <div className="modal-overlay gate">
      <form className="modal-box" onSubmit={handleSubmit}>
        <h3>💼 Job Hunt Pipeline</h3>
        <div className="sub">Enter your access key to open the app on this device.</div>
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
          <button type="submit" className="btn primary">Unlock</button>
        </div>
      </form>
    </div>
  )
}
