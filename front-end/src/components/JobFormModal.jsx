import { useState, useEffect } from 'react'

const API = 'http://localhost:8000'

const EMPTY_FORM = {
  company: '', title: '', location: '', duration: '',
  minDurationMonths: '', deadline: '', applyLink: '', skills: '', description: '',
}

// Converts the backend's `edit` object into the form's state shape
function toForm(edit) {
  return {
    company: edit.company || '',
    title: edit.title || '',
    location: edit.location || '',
    duration: edit.duration || '',
    minDurationMonths: edit.min_duration_months ?? '',
    deadline: edit.deadline || '',
    applyLink: edit.apply_link || '',
    skills: (edit.skills || []).join(', '),
    description: edit.description || '',
  }
}

export default function JobFormModal({ open, mode, initial, trackingId, onClose, onSaved }) {
  const isEdit = mode === 'edit'
  const [form, setForm] = useState(EMPTY_FORM)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  // Reset every time the modal opens: blank for Add, prefilled for Edit
  useEffect(() => {
    if (open) {
      setForm(initial ? toForm(initial) : EMPTY_FORM)
      setError(null)
    }
  }, [open, isEdit, initial])

  if (!open) return null

  function update(field, value) {
    setForm(prev => ({ ...prev, [field]: value }))
  }

  function handleSubmit(e) {
    e.preventDefault()
    if (!form.company.trim() || !form.title.trim()) {
      setError('Company and Job Title are required.')
      return
    }
    setSubmitting(true)
    setError(null)

    const url = isEdit ? `${API}/api/tracker/${trackingId}/edit` : `${API}/api/jobs/manual`
    fetch(url, {
      method: isEdit ? 'PATCH' : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        company: form.company,
        title: form.title,
        location: form.location || null,
        duration: form.duration || null,
        min_duration_months: form.minDurationMonths !== '' ? Number(form.minDurationMonths) : null,
        deadline: form.deadline || null,
        apply_link: form.applyLink || null,
        skills: form.skills ? form.skills.split(',').map(s => s.trim()).filter(Boolean) : [],
        description: form.description || null,
      }),
    })
      .then(res => {
        if (!res.ok) throw new Error('Request failed')
        return res.json()
      })
      .then(() => onSaved())
      .catch(() => setError(
        isEdit
          ? 'Failed to save changes — check the backend is running.'
          : 'Failed to add job — check the backend is running.'
      ))
      .finally(() => setSubmitting(false))
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" onClick={e => e.stopPropagation()}>
        <h3>{isEdit ? 'Edit Job' : 'Add Job Manually'}</h3>
        <div className="sub">
          {isEdit
            ? 'Changes only apply to your own tracker — the original listing stays untouched.'
            : 'Fill in what you know — only Company and Job Title are required.'}
        </div>

        <form onSubmit={handleSubmit}>
          <div className="field-grid">
            <div className="field-row">
              <label>Company *</label>
              <input value={form.company} onChange={e => update('company', e.target.value)} />
            </div>
            <div className="field-row">
              <label>Job Title *</label>
              <input value={form.title} onChange={e => update('title', e.target.value)} />
            </div>
            <div className="field-row">
              <label>Location</label>
              <input value={form.location} onChange={e => update('location', e.target.value)} placeholder="e.g. Singapore" />
            </div>
            <div className="field-row">
              <label>Duration</label>
              <input value={form.duration} onChange={e => update('duration', e.target.value)} placeholder="e.g. 18 May – 17 July" />
            </div>
            <div className="field-row">
              <label>Min Duration (months)</label>
              <input type="number" value={form.minDurationMonths} onChange={e => update('minDurationMonths', e.target.value)} />
            </div>
            <div className="field-row">
              <label>Deadline (blank = ASAP)</label>
              <input type="date" value={form.deadline} onChange={e => update('deadline', e.target.value)} />
            </div>
          </div>

          <div className="field-row">
            <label>Apply Link</label>
            <input value={form.applyLink} onChange={e => update('applyLink', e.target.value)} placeholder="https://..." />
          </div>
          <div className="field-row">
            <label>Skills (comma-separated)</label>
            <input value={form.skills} onChange={e => update('skills', e.target.value)} placeholder="Python, SQL, PySpark" />
          </div>
          <div className="field-row">
            <label>Description</label>
            <textarea value={form.description} onChange={e => update('description', e.target.value)} />
          </div>

          {error && <div className="jd" style={{ color: '#991b1b' }}>{error}</div>}

          <div className="modal-actions">
            <button type="button" className="btn" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn primary" disabled={submitting}>
              {submitting ? (isEdit ? 'Saving…' : 'Adding…') : isEdit ? '✎ Edit Job' : '+ Add Job'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}