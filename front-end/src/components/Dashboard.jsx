import { useRef, useState } from 'react'
import { STATUS, ST_CLASS } from '../data'
import Calendar from './Calendar'
import { blockedForGuest } from '../api'
import { locationGroup } from '../locationGroup'

// The columns you can show or hide. The details arrow at the end of each row always stays.
const COLUMNS = [
  { key: 'status', label: 'Status' },
  { key: 'company', label: 'Company' },
  { key: 'title', label: 'Job Title' },
  { key: 'location', label: 'Location' },
  { key: 'duration', label: 'Duration' },
  { key: 'minDuration', label: 'Min. Duration' },
  { key: 'deadline', label: 'Deadline' },
  { key: 'submitted', label: 'Submitted' },
  { key: 'apply', label: 'Apply Link' },
  { key: 'upload', label: 'My Upload', thClass: 'cvhead' },
]

// Stores the hidden columns rather than the shown ones, so a column added later
// shows up by default. Storage can be unavailable (private mode), in which case
// the choice only lasts until the page is reloaded.
const HIDDEN_COLUMNS_STORAGE = 'jobHuntHiddenColumns'

function loadHiddenColumns() {
  try {
    const saved = JSON.parse(localStorage.getItem(HIDDEN_COLUMNS_STORAGE))
    return Array.isArray(saved) ? saved : []
  } catch {
    return []
  }
}

// en-CA gives YYYY-MM-DD, the same format as the Deadline column, in the viewer's timezone
function formatSubmittedDate(iso) {
  return iso ? new Date(iso).toLocaleDateString('en-CA') : '—'
}

function UploadCell({ job, onUploadCv, onDeleteCv }) {
  const inputRef = useRef(null)

  function pickFile() {
    if (blockedForGuest()) return
    inputRef.current.click()
  }

  function deleteFile() {
    if (blockedForGuest()) return
    onDeleteCv(job.trackingId)
  }

  return (
    <>
      {job.myUploadUrl ? (
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 10 }}>
          <a className="filelink" href={job.myUploadUrl} target="_blank" rel="noreferrer">📎 View upload</a>
          <button className="btn sm" title="Replace upload" aria-label="Replace upload" onClick={pickFile}>⬆</button>
          <button className="btn sm" title="Delete upload" aria-label="Delete upload" onClick={deleteFile}>🗑</button>
        </span>
      ) : (
        <button className="btn sm" onClick={pickFile}>⬆ Upload</button>
      )}
      {/* One hidden file input serves both the Upload and Replace buttons */}
      <input
        ref={inputRef}
        type="file"
        style={{ display: 'none' }}
        accept=".pdf,.docx"
        onChange={e => {
          const file = e.target.files[0]
          if (file) onUploadCv(job.trackingId, file)
          e.target.value = '' // so choosing the same file again still triggers onChange
        }}
      />
    </>
  )
}

// Stands in for the tracked jobs a guest can't see: blurred placeholder rows
// with a prompt to enter the access key
function LockedRows({ onUnlock, colSpan }) {
  return (
    <tr className="empty-row locked-row">
      <td colSpan={colSpan}>
        <div className="locked">
          <div className="locked-ghost" aria-hidden="true">
            {[0, 1, 2].map(i => (
              <div className="ghost-line" key={i}>
                <span style={{ width: '16%' }} /><span style={{ width: '14%' }} /><span style={{ width: '24%' }} />
                <span style={{ width: '12%' }} /><span style={{ width: '10%' }} />
              </div>
            ))}
          </div>
          <div className="locked-msg">
            <span>🔒 <b>More jobs</b> hidden in guest view</span>
            <button className="btn sm primary" onClick={onUnlock}>Enter access key</button>
          </div>
        </div>
      </td>
    </tr>
  )
}

export default function Dashboard({ jobs, hiddenJobCount, onUnlock, onStatusChange, onOpenDrawer, onUploadCv, onDeleteCv, onOpenManualModal, onLoadFromUrl }) {
  const [url, setUrl] = useState('')
  const [loadingUrl, setLoadingUrl] = useState(false)
  const [urlMessage, setUrlMessage] = useState(null)

  async function handleLoad() {
    if (!url.trim()) return
    setLoadingUrl(true)
    setUrlMessage(null)
    const result = await onLoadFromUrl(url.trim())
    setLoadingUrl(false)
    if (result.ok) setUrl('')
    else setUrlMessage(result.message)
  }

  const [showFilter, setShowFilter] = useState(false)
  const [statusFilter, setStatusFilter] = useState('all')
  const [locationFilter, setLocationFilter] = useState('all')

  // Location dropdown options come from the jobs you actually have: { bangkok: { label, count } }
  const locationOptions = {}
  for (const j of jobs) {
    const g = locationGroup(j.loc)
    if (!locationOptions[g.key]) locationOptions[g.key] = { label: g.label, count: 0 }
    locationOptions[g.key].count += 1
  }

  // visibleJobs is worked out from jobs + the two filters on every render.
  // It is not stored in state, so it can never get out of sync with them.
  const visibleJobs = jobs.filter(
    j =>
      (statusFilter === 'all' || j.status === statusFilter) &&
      (locationFilter === 'all' || locationGroup(j.loc).key === locationFilter)
  )
  const activeFilters = [statusFilter, locationFilter].filter(f => f !== 'all').length
  // Guests see "4+" rather than the real total, which would give away how many are hidden
  const jobCountLabel = hiddenJobCount > 0 ? `${jobs.length}+` : jobs.length

  function clearFilters() {
    setStatusFilter('all')
    setLocationFilter('all')
  }

  const [showColumns, setShowColumns] = useState(false)
  const [hiddenColumns, setHiddenColumns] = useState(loadHiddenColumns)
  const shownColumns = COLUMNS.filter(c => !hiddenColumns.includes(c.key))
  const hiddenCount = COLUMNS.length - shownColumns.length
  const isShown = key => !hiddenColumns.includes(key)
  const colSpan = shownColumns.length + 1 // + the details arrow

  function saveHiddenColumns(next) {
    setHiddenColumns(next)
    try {
      localStorage.setItem(HIDDEN_COLUMNS_STORAGE, JSON.stringify(next))
    } catch {
      // Storage unavailable: the choice still applies until the page is reloaded
    }
  }

  function toggleColumn(key) {
    saveHiddenColumns(isShown(key) ? [...hiddenColumns, key] : hiddenColumns.filter(k => k !== key))
  }

  return (
    <section>
      <div className="pagehead">
        <div>
          <h1>Dashboard</h1>
          <p>Track every application, deadline, and tailored CV in one place.</p>
        </div>
        <div className="actions">
          <button className="btn">⬇ Export</button>
          <button className="btn">⚙ Settings</button>
        </div>
      </div>

      <div className="urlbar">
        <input
          type="text"
          placeholder="Paste job posting URL..."
          value={url}
          onChange={e => setUrl(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') handleLoad() }}
        />
        <button className="btn accent-outline" onClick={handleLoad} disabled={loadingUrl}>
          {loadingUrl ? 'Loading…' : '⬇ Load Job'}
        </button>
      </div>
      {urlMessage && <div className="url-msg">{urlMessage}</div>}

      <div className="sectionhead">
        <h2>
          Job tracker{' '}
          <span className="count">
            {activeFilters
              ? `${visibleJobs.length} of ${jobCountLabel} jobs`
              : `${jobCountLabel} jobs`}
          </span>
        </h2>
        <div className="actions">
          <button className="btn sm" onClick={() => setShowFilter(s => !s)}>
            ☰ Filter{activeFilters ? ` (${activeFilters})` : ''}
          </button>
          <button className="btn sm" onClick={() => setShowColumns(s => !s)}>
            ▤ Columns{hiddenCount ? ` (${hiddenCount} hidden)` : ''}
          </button>
          <button className="btn sm primary" onClick={onOpenManualModal}>+ Add Job Manually</button>
        </div>
      </div>

      {showFilter && (
        <div className="card filterbar">
          <div className="field-row">
            <label>Status</label>
            <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}>
              <option value="all">All statuses</option>
              {STATUS.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div className="field-row">
            <label>Location</label>
            <select value={locationFilter} onChange={e => setLocationFilter(e.target.value)}>
              <option value="all">All locations</option>
              {Object.entries(locationOptions)
                .sort((a, b) => a[1].label.localeCompare(b[1].label))
                .map(([key, o]) => (
                  <option key={key} value={key}>{o.label} ({o.count})</option>
                ))}
            </select>
          </div>
          <button className="btn sm" onClick={clearFilters}>Clear</button>
        </div>
      )}

      {showColumns && (
        <div className="card filterbar columnsbar">
          {COLUMNS.map(c => (
            <label className="col-toggle" key={c.key}>
              <input
                type="checkbox"
                checked={isShown(c.key)}
                disabled={isShown(c.key) && shownColumns.length === 1} // keep at least one column
                onChange={() => toggleColumn(c.key)}
              />
              {c.label}
            </label>
          ))}
          <button className="btn sm" onClick={() => saveHiddenColumns([])}>Show all</button>
        </div>
      )}
      <div className="card tablewrap">
        <table className="cards">
          <thead>
            <tr>
              {shownColumns.map(c => <th key={c.key} className={c.thClass}>{c.label}</th>)}
              <th></th>
            </tr>
          </thead>
          <tbody>
            {visibleJobs.map(j => (
              <tr key={j.trackingId}>
                {isShown('status') && (
                  <td className="c-full">
                    <select
                      className={`pill st-${ST_CLASS[j.status]}`}
                      value={j.status}
                      onChange={e => onStatusChange(j.trackingId, e.target.value)}
                    >
                      {STATUS.map(s => <option key={s}>{s}</option>)}
                      <option value="Untracked" style={{ color: 'crimson' }}>🗑 Untrack</option>
                    </select>
                  </td>
                )}
                {isShown('company') && <td className="c-co">{j.co}</td>}
                {isShown('title') && <td className="job-title c-title">{j.title}</td>}
                {isShown('location') && <td data-label="Location">{j.loc}</td>}
                {isShown('duration') && <td data-label="Duration">{j.dur}</td>}
                {isShown('minDuration') && <td data-label="Min. duration">{j.min}</td>}
                {isShown('deadline') && <td data-label="Deadline">{j.dl}</td>}
                {isShown('submitted') && <td data-label="Submitted">{formatSubmittedDate(j.submittedAt)}</td>}
                {isShown('apply') && (
                  <td data-label="Apply">
                    {j.applyLink ? <a className="applink" href={j.applyLink} target="_blank" rel="noreferrer">Open ↗</a> : '—'}
                  </td>
                )}
                {isShown('upload') && (
                  <td className="cvcell" data-label="My upload"><UploadCell job={j} onUploadCv={onUploadCv} onDeleteCv={onDeleteCv} /></td>
                )}
                <td className="c-open">
                  <button className="chev" aria-label="Show details" onClick={() => onOpenDrawer(j)}>›</button>
                </td>
              </tr>
            ))}
            {jobs.length > 0 && visibleJobs.length === 0 && (
              <tr className="empty-row"><td colSpan={colSpan}>No jobs match these filters.</td></tr>
            )}
            {jobs.length === 0 && (
              <tr className="empty-row"><td colSpan={colSpan}>No tracked jobs yet. Paste a link above or add jobs from Explore.</td></tr>
            )}
            {hiddenJobCount > 0 && <LockedRows onUnlock={onUnlock} colSpan={colSpan} />}
          </tbody>
        </table>
      </div>

      <div className="sectionhead"><h2>Deadline calendar</h2></div>
      <div className="card" style={{ padding: 16 }}>
        <Calendar jobs={jobs} onOpenJob={onOpenDrawer} />
      </div>
    </section>
  )
}