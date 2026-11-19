import { useState, useEffect } from 'react'

import { apiFetch, blockedForGuest, readResult } from '../api'

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

// A saved timestamp as the YYYY-MM-DD a date field shows, on this device's calendar
function toDateField(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const pad = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

// tabId (new look only): the dashboard tab a new job goes into. Left out, the server picks the default tab.
// application (edit only): { status, submittedAt } - your own record of applying, not part of the job posting.
export default function JobFormModal({ open, mode, initial, application, trackingId, tabId, onClose, onSaved }) {
  const isEdit = mode === 'edit'
  const [form, setForm] = useState(EMPTY_FORM)
  const [submittedOn, setSubmittedOn] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  const savedSubmittedOn = toDateField(application?.submittedAt)
  // A job still at Saved hasn't been applied to, so it can't have a submitted date yet
  const notSubmittedYet = !application || application.status === 'Saved / Not Applied'

  // Reset every time the modal opens: blank for Add, prefilled for Edit
  useEffect(() => {
    if (open) {
      setForm(initial ? toForm(initial) : EMPTY_FORM)
      setSubmittedOn(savedSubmittedOn)
      setError(null)
    }
  }, [open, isEdit, initial, savedSubmittedOn])

  if (!open) return null

  function update(field, value) {
    setForm(prev => ({ ...prev, [field]: value }))
  }

  function handleSubmit(e) {
    e.preventDefault()
    if (blockedForGuest()) return
    if (!form.company.trim() || !form.title.trim()) {
      setError('Company and Job Title are required.')
      return
    }
    setSubmitting(true)
    setError(null)

    const body = {
      company: form.company,
      title: form.title,
      location: form.location || null,
      duration: form.duration || null,
      min_duration_months: form.minDurationMonths !== '' ? Number(form.minDurationMonths) : null,
      deadline: form.deadline || null,
      apply_link: form.applyLink || null,
      skills: form.skills ? form.skills.split(',').map(s => s.trim()).filter(Boolean) : [],
      description: form.description || null,
      tab_id: tabId ?? null,
    }
    // Sent only when changed, so the exact time saved when the job was marked
    // Submitted isn't replaced by a plain date
    if (isEdit && submittedOn !== savedSubmittedOn) body.submitted_on = submittedOn || null

    const url = isEdit ? `/api/tracker/${trackingId}/edit` : `/api/jobs/manual`
    apiFetch(url, {
      method: isEdit ? 'PATCH' : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
      .then(res => readResult(res, isEdit
        ? 'Failed to save changes. Check the backend is running.'
        : 'Failed to add job. Check the backend is running.'))
      .then(() => onSaved())
      .catch(err => setError(err.message))
      .finally(() => setSubmitting(false))
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" onClick={e => e.stopPropagation()}>
        <h3>{isEdit ? 'Edit Job' : 'Add Job Manually'}</h3>
        <div className="sub">
          {isEdit
            ? 'Your application details are yours alone. Job details come from the posting: changing them only affects your tracker.'
            : 'Fill in what you know — only Company and Job Title are required.'}
        </div>

        <form onSubmit={handleSubmit}>
          {/* Kept apart from the job fields: this is what you did, not what the posting says */}
          {isEdit && (
            <fieldset className="form-section mine">
              <legend className="form-section-title">Your application</legend>
              <div className="field-row">
                <label htmlFor="submittedOn">Submitted on</label>
                <input
                  id="submittedOn"
                  type="date"
                  value={submittedOn}
                  max={toDateField(new Date().toISOString())}
                  disabled={notSubmittedYet}
                  onChange={e => setSubmittedOn(e.target.value)}
                />
                <span className="field-hint">
                  {notSubmittedYet
                    ? 'Set the status to Submitted first. The date is filled in then, and you can change it here.'
                    : 'Filled in when you marked the job Submitted. Change it if you applied on a different day.'}
                </span>
              </div>
            </fieldset>
          )}

          {isEdit && <div className="form-section-title">Job details</div>}
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
