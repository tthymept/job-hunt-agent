import { useState, useEffect } from 'react'

const API = 'http://localhost:8000'
const JSON_HEADERS = { 'Content-Type': 'application/json' }

function titleCase(text) {
  return (text || '').replace(/\b\w/g, c => c.toUpperCase())
}

function describeStatus(interest) {
  if (interest.status === 'paused') return 'Paused'
  if (!interest.backfilled) return 'Fetching jobs…'
  return 'Active'
}

export default function InterestsModal({ open, onClose }) {
  const [interests, setInterests] = useState([])
  const [role, setRole] = useState('')
  const [country, setCountry] = useState('')
  const [city, setCity] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  function loadInterests() {
    return fetch(`${API}/api/interests`)
      .then(res => res.json())
      .then(setInterests)
      .catch(err => console.error('Failed to load interests:', err))
  }

  useEffect(() => {
    if (open) {
      setError(null)
      loadInterests()
    }
  }, [open])

  // While any active interest is still backfilling, re-check every 5 seconds
  // so the "Fetching jobs…" label flips to "Active" on its own.
  const fetching = interests.some(i => i.status === 'active' && !i.backfilled)
  useEffect(() => {
    if (!open || !fetching) return
    const timer = setInterval(loadInterests, 5000)
    return () => clearInterval(timer)
  }, [open, fetching])

  // Must stay below every hook above, otherwise React throws
  if (!open) return null

  async function handleAdd(e) {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      const res = await fetch(`${API}/api/interests`, {
        method: 'POST',
        headers: JSON_HEADERS,
        body: JSON.stringify({ role, country, city }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Could not add this interest.')
      setRole('')
      setCountry('')
      setCity('')
      await loadInterests()
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  async function updateStatus(id, status) {
    try {
      await fetch(`${API}/api/interests/${id}`, {
        method: 'PATCH',
        headers: JSON_HEADERS,
        body: JSON.stringify({ status }),
      })
      await loadInterests()
    } catch (err) {
      setError('Could not update this interest. Is the backend running?')
    }
  }

  async function removeInterest(id) {
    if (!window.confirm('Remove this search interest? Jobs already found will stay in Explore.')) return
    try {
      await fetch(`${API}/api/interests/${id}`, { method: 'DELETE' })
      await loadInterests()
    } catch (err) {
      setError('Could not remove this interest. Is the backend running?')
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" style={{ width: 560 }} onClick={e => e.stopPropagation()}>
        <h3>Search interests</h3>
        <div className="sub">
          The scheduled fetch searches job boards for every active interest. A new one also gets a one-time deeper search.
        </div>

        {interests.length === 0 ? (
          <p className="interest-empty">No interests yet. Add your first one below.</p>
        ) : (
          <div className="interest-list">
            {interests.map(i => (
              <div key={i.id} className={`interest-row${i.status === 'paused' ? ' paused' : ''}`}>
                <div className="interest-main">
                  <div className="interest-role">{titleCase(i.role)}</div>
                  <div className="interest-meta">
                    {i.city ? `${titleCase(i.city)}, ` : ''}{titleCase(i.country)} · {describeStatus(i)}
                  </div>
                </div>
                <div className="interest-actions">
                  {i.status === 'paused' ? (
                    <button className="btn sm" onClick={() => updateStatus(i.id, 'active')}>Resume</button>
                  ) : (
                    <button className="btn sm" onClick={() => updateStatus(i.id, 'paused')}>Pause</button>
                  )}
                  <button className="btn sm" onClick={() => removeInterest(i.id)}>Remove</button>
                </div>
              </div>
            ))}
          </div>
        )}

        <form onSubmit={handleAdd}>
          <div className="field-row">
            <label>Role</label>
            <input
              type="text"
              value={role}
              onChange={e => setRole(e.target.value)}
              placeholder="Data engineer intern"
              required
            />
          </div>
          <div className="field-grid">
            <div className="field-row">
              <label>Country</label>
              <input
                type="text"
                value={country}
                onChange={e => setCountry(e.target.value)}
                placeholder="Singapore"
                required
              />
            </div>
            <div className="field-row">
              <label>City (optional)</label>
              <input
                type="text"
                value={city}
                onChange={e => setCity(e.target.value)}
                placeholder="Bangkok"
              />
            </div>
          </div>
          {error && <p className="interest-error">{error}</p>}
          <div className="actions" style={{ justifyContent: 'flex-end' }}>
            <button type="button" className="btn" onClick={onClose}>Done</button>
            <button type="submit" className="btn primary" disabled={submitting}>
              {submitting ? 'Adding…' : 'Add interest'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}