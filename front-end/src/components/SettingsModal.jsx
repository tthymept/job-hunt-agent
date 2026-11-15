import { useState } from 'react'
import { UI_STYLES, getUiStyle, setUiStyle } from '../uiStyle'

// Opened from the Settings button on the Dashboard. Shared by both looks, so it
// only uses class names that exist in index.css and in v2/v2.css.
export default function SettingsModal({ onClose }) {
  const current = getUiStyle()
  const [style, setStyle] = useState(current)
  const [error, setError] = useState(null)

  function handleSubmit(e) {
    e.preventDefault()
    if (style === current) {
      onClose()
      return
    }
    if (!setUiStyle(style)) {
      setError('This browser is blocking storage, so the choice cannot be saved.')
      return
    }
    // The look is picked when the page loads, so reload to apply it
    window.location.reload()
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <form className="modal-box" onSubmit={handleSubmit} onClick={e => e.stopPropagation()}>
        <h3>Settings</h3>
        <div className="sub">Choose how the app looks on this device. Your jobs and data stay the same.</div>

        <div className="style-options" role="radiogroup" aria-label="Appearance">
          {UI_STYLES.map(option => (
            <label key={option.value} className={`style-option${style === option.value ? ' selected' : ''}`}>
              <input
                type="radio"
                name="uiStyle"
                value={option.value}
                checked={style === option.value}
                onChange={() => setStyle(option.value)}
              />
              <span>
                <b>{option.label}{option.value === 'new' ? ' (default)' : ''}</b>
                <span className="style-hint">{option.hint}</span>
              </span>
            </label>
          ))}
        </div>

        {error && <p className="interest-error">{error}</p>}

        <div className="modal-actions">
          <button type="button" className="btn" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn primary">{style === current ? 'Done' : 'Apply'}</button>
        </div>
      </form>
    </div>
  )
}
