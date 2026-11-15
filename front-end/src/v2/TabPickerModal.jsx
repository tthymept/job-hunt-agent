import { useState } from 'react'

// "Which tab should this job go into?" Shown before adding a job when more than
// one tab accepts new jobs. Tabs with adding turned off are not offered.
export default function TabPickerModal({ tabs, initialId, onPick, onCancel }) {
  const [tabId, setTabId] = useState(initialId)

  function handleSubmit(e) {
    e.preventDefault()
    onPick(tabId)
  }

  return (
    <div className="modal-overlay blocked" onClick={onCancel}>
      <form className="modal-box" onSubmit={handleSubmit} onClick={e => e.stopPropagation()}>
        <h3>Add to which tab?</h3>
        <div className="sub">Pick the tab this job should go into. You can move it later from the job details.</div>

        <div className="style-options" role="radiogroup" aria-label="Tab">
          {tabs.map(tab => (
            <label key={tab.id} className={`style-option${tabId === tab.id ? ' selected' : ''}`}>
              <input
                type="radio"
                name="targetTab"
                checked={tabId === tab.id}
                onChange={() => setTabId(tab.id)}
              />
              <span>
                <b>{tab.name}</b>
                {tab.isDefault && <span className="style-hint">Default tab</span>}
              </span>
            </label>
          ))}
        </div>

        <div className="modal-actions">
          <button type="button" className="btn" onClick={onCancel}>Cancel</button>
          <button type="submit" className="btn primary" autoFocus>Add here</button>
        </div>
      </form>
    </div>
  )
}
