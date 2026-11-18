import { useRef, useState } from 'react'
import { STATUS, ST_CLASS } from '../data'
import { blockedForGuest, openFileLink } from '../api'
import { locationGroup } from '../locationGroup'
import Calendar from './Calendar'
import TabBar from './TabBar'
import Icon from './Icon'
import { parseDay, formatDay, daysUntil, daysLabel } from './dates'

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
  { key: 'upload', label: 'My Uploads' },
]

// The stage tiles above the table. Each one counts the jobs in its statuses and,
// when clicked, filters the table to them. `tone` picks the dot colour.
const STAGES = [
  { key: 'all', label: 'All jobs' },
  { key: 'saved', label: 'To apply', tone: 'saved', statuses: ['Saved / Not Applied'] },
  { key: 'submitted', label: 'Submitted', tone: 'sub', statuses: ['Submitted'] },
  { key: 'progress', label: 'In progress', tone: 'online', statuses: ['Online Assignment', 'Interview Round 1', 'Interview Round 2'] },
  { key: 'offered', label: 'Offered', tone: 'off', statuses: ['Offered'] },
  { key: 'rejected', label: 'Rejected', tone: 'rej', statuses: ['Rejected'] },
]

// Same storage key as the current UI, so your column choice carries over.
// Stores the hidden columns rather than the shown ones, so a column added later
// shows up by default.
const HIDDEN_COLUMNS_STORAGE = 'jobHuntHiddenColumns'

function loadHiddenColumns() {
  try {
    const saved = JSON.parse(localStorage.getItem(HIDDEN_COLUMNS_STORAGE))
    return Array.isArray(saved) ? saved : []
  } catch {
    return []
  }
}

// Deadline cell: the date, plus how long is left while the job is still unapplied
function DeadlineCell({ job }) {
  const date = parseDay(job.dl)
  if (!date) return job.dl
  const days = daysUntil(date)
  const pending = job.status === 'Saved / Not Applied'
  return (
    <>
      {formatDay(date)}
      {pending && <span className={`due${days <= 7 ? ' soon' : ''}${days < 0 ? ' over' : ''}`}>{daysLabel(days)}</span>}
    </>
  )
}

// The two files a tracked job can hold. `kind` is what the backend calls the
// slot, `field` is where the job says whether that file exists.
const UPLOAD_SLOTS = [
  { kind: 'cv', label: 'CV', field: 'hasMyUpload' },
  { kind: 'cover_letter', label: 'Cover letter', field: 'hasCoverLetter' },
]

// One file slot: a link to the file with replace and delete, or an upload button
function UploadSlot({ job, slot, onUploadCv, onDeleteCv }) {
  const inputRef = useRef(null)
  const hasFile = job[slot.field]

  function openFile() {
    if (blockedForGuest()) return
    openFileLink(`/api/tracker/${job.trackingId}/file-link?kind=${slot.kind}`)
  }

  function pickFile() {
    if (blockedForGuest()) return
    inputRef.current.click()
  }

  function deleteFile() {
    if (blockedForGuest()) return
    onDeleteCv(job.trackingId, slot.kind)
  }

  return (
    <span className="upload-slot">
      {hasFile ? (
        <>
          <button className="textlink" title={`Open ${slot.label}`} onClick={openFile}>
            <Icon name="file" size={14} /> {slot.label}
          </button>
          <button className="iconbtn" title={`Replace ${slot.label}`} aria-label={`Replace ${slot.label}`} onClick={pickFile}><Icon name="upload" size={14} /></button>
          <button className="iconbtn danger" title={`Delete ${slot.label}`} aria-label={`Delete ${slot.label}`} onClick={deleteFile}><Icon name="trash" size={14} /></button>
        </>
      ) : (
        <button className="upload-add" title={`Upload ${slot.label}`} onClick={pickFile}><Icon name="upload" size={13} /> {slot.label}</button>
      )}
      {/* One hidden file input serves both the upload and replace buttons */}
      <input
        ref={inputRef}
        type="file"
        style={{ display: 'none' }}
        accept=".pdf,.doc,.docx"
        onChange={e => {
          const file = e.target.files[0]
          if (file) onUploadCv(job.trackingId, file, slot.kind)
          e.target.value = '' // so choosing the same file again still triggers onChange
        }}
      />
    </span>
  )
}

function UploadCell({ job, onUploadCv, onDeleteCv }) {
  return (
    <span className="upload-box">
      {UPLOAD_SLOTS.map(slot => (
        <UploadSlot key={slot.kind} job={job} slot={slot} onUploadCv={onUploadCv} onDeleteCv={onDeleteCv} />
      ))}
    </span>
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
            <span className="locked-text"><Icon name="lock" size={15} /> <b>More jobs</b> hidden in guest view</span>
            <button className="btn sm primary" onClick={onUnlock}>Enter access key</button>
          </div>
        </div>
      </td>
    </tr>
  )
}

// The next few dated deadlines, soonest first
function UpcomingDeadlines({ jobs, onOpenJob }) {
  const upcoming = jobs
    .map(job => ({ job, date: parseDay(job.dl) }))
    .filter(item => item.date && daysUntil(item.date) >= 0)
    .sort((a, b) => a.date - b.date)
    .slice(0, 6)

  return (
    <div className="card upcoming">
      <h3>Upcoming deadlines</h3>
      {upcoming.length === 0 && (
        <p className="upcoming-empty">No dated deadlines ahead. Jobs marked ASAP have no date to show.</p>
      )}
      {upcoming.map(({ job, date }) => {
        const days = daysUntil(date)
        return (
          <button className="upcoming-item" key={job.trackingId} onClick={() => onOpenJob(job)}>
            <span className="datebox">
              <b>{date.getDate()}</b>
              {date.toLocaleDateString('en-GB', { month: 'short' })}
            </span>
            <span className="upcoming-main">
              <span className="upcoming-co">{job.co}</span>
              <span className="upcoming-title">{job.title}</span>
            </span>
            <span className={`due${days <= 7 ? ' soon' : ''}`}>{daysLabel(days)}</span>
          </button>
        )
      })}
    </div>
  )
}

export default function Dashboard({ jobs, hiddenJobCount, tabs, activeTab, tabCounts, onSelectTab, tabActions, tabError, onDismissTabError, onUnlock, onStatusChange, onOpenDrawer, onUploadCv, onDeleteCv, onOpenManualModal, onLoadFromUrl }) {
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

  // A tab with adding turned off shows a notice in place of the add-a-job row
  const addingOff = activeTab ? !activeTab.enabled : false

  const [stage, setStage] = useState('all')
  const [locationFilter, setLocationFilter] = useState('all')
  const [search, setSearch] = useState('')

  // Location dropdown options come from the jobs you actually have: { bangkok: { label, count } }
  const locationOptions = {}
  for (const j of jobs) {
    const g = locationGroup(j.loc)
    if (!locationOptions[g.key]) locationOptions[g.key] = { label: g.label, count: 0 }
    locationOptions[g.key].count += 1
  }

  // visibleJobs is worked out from jobs + the filters on every render.
  // It is not stored in state, so it can never get out of sync with them.
  const stageStatuses = STAGES.find(s => s.key === stage)?.statuses
  const needle = search.trim().toLowerCase()
  const visibleJobs = jobs.filter(
    j =>
      (!stageStatuses || stageStatuses.includes(j.status)) &&
      (locationFilter === 'all' || locationGroup(j.loc).key === locationFilter) &&
      (!needle || `${j.co} ${j.title}`.toLowerCase().includes(needle))
  )
  const filtering = stage !== 'all' || locationFilter !== 'all' || needle !== ''
  // Guests see "4+" rather than the real total, which would give away how many are hidden
  const jobCountLabel = hiddenJobCount > 0 ? `${jobs.length}+` : jobs.length

  function stageCount(s) {
    if (!s.statuses) return jobCountLabel
    return jobs.filter(j => s.statuses.includes(j.status)).length
  }

  function clearFilters() {
    setStage('all')
    setLocationFilter('all')
    setSearch('')
  }

  const [showColumns, setShowColumns] = useState(false)
  const [hiddenColumns, setHiddenColumns] = useState(loadHiddenColumns)
  const shownColumns = COLUMNS.filter(c => !hiddenColumns.includes(c.key))
  const hiddenCount = COLUMNS.length - shownColumns.length
  const isShown = key => !hiddenColumns.includes(key)
  // Company and Job Title share one table cell (title on top, company under it),
  // so the table needs less width. Each can still be hidden on its own.
  const showJob = isShown('company') || isShown('title')
  const headColumns = shownColumns.filter(c => c.key !== 'company' && c.key !== 'title')
  if (showJob) headColumns.splice(isShown('status') ? 1 : 0, 0, { key: 'job', label: 'Job' })
  const colSpan = headColumns.length + 1 // + the details arrow

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
      </div>

      <TabBar
        tabs={tabs}
        activeId={activeTab?.id}
        counts={tabCounts}
        onSelect={onSelectTab}
        actions={tabActions}
        error={tabError}
        onDismissError={onDismissTabError}
      />

      {addingOff ? (
        <div className="addbar-off">
          <span><b>Adding jobs is turned off for this tab.</b> You can still view and edit everything in it.</span>
          <button className="btn" onClick={() => tabActions.setEnabled(activeTab.id, true)}>Turn on adding</button>
        </div>
      ) : (
      <div className="addbar">
        <div className="inputwrap grow">
          <Icon name="link" />
          <input
            type="text"
            aria-label="Job posting URL"
            placeholder="Paste a job posting URL to add it"
            value={url}
            onChange={e => setUrl(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') handleLoad() }}
          />
        </div>
        <button className="btn primary" onClick={handleLoad} disabled={loadingUrl}>
          {loadingUrl ? 'Loading…' : 'Load job'}
        </button>
        <span className="addbar-or">or</span>
        <button className="btn" onClick={onOpenManualModal}><Icon name="plus" /> Add manually</button>
      </div>
      )}
      {urlMessage && <div className="url-msg" role="alert">{urlMessage}</div>}

      <div className="stages" role="group" aria-label="Filter by stage">
        {STAGES.map(s => (
          <button
            key={s.key}
            className={`stage${stage === s.key ? ' active' : ''}`}
            aria-pressed={stage === s.key}
            onClick={() => setStage(s.key)}
          >
            <span className="stage-label">
              {s.tone && <i className={`dot st-${s.tone}`} />}
              {s.label}
            </span>
            <span className="stage-num">{stageCount(s)}</span>
          </button>
        ))}
      </div>

      <div className="card tablecard">
        <div className="toolbar">
          <h2>
            Job tracker
            <span className="count">
              {filtering ? `${visibleJobs.length} of ${jobCountLabel}` : jobCountLabel}
            </span>
          </h2>
          <div className="toolbar-tools">
            <div className="inputwrap">
              <Icon name="search" size={15} />
              <input
                type="search"
                aria-label="Search company or title"
                placeholder="Search company or title"
                value={search}
                onChange={e => setSearch(e.target.value)}
              />
            </div>
            <select aria-label="Location" value={locationFilter} onChange={e => setLocationFilter(e.target.value)}>
              <option value="all">All locations</option>
              {Object.entries(locationOptions)
                .sort((a, b) => a[1].label.localeCompare(b[1].label))
                .map(([key, o]) => (
                  <option key={key} value={key}>{o.label} ({o.count})</option>
                ))}
            </select>
            {filtering && <button className="btn quiet" onClick={clearFilters}>Clear</button>}
            <div className="popwrap">
              <button className="btn" aria-expanded={showColumns} onClick={() => setShowColumns(s => !s)}>
                <Icon name="columns" size={15} /> Columns{hiddenCount ? ` (${hiddenCount} hidden)` : ''}
              </button>
              {showColumns && (
                <>
                  {/* Invisible layer behind the menu: a click anywhere else closes it */}
                  <div className="pop-shade" onClick={() => setShowColumns(false)} />
                  <div className="popover">
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
                </>
              )}
            </div>
          </div>
        </div>

        <div className="tablewrap">
          <table className="cards">
            <thead>
              <tr>
                {headColumns.map(c => <th key={c.key}>{c.label}</th>)}
                <th></th>
              </tr>
            </thead>
            <tbody>
              {visibleJobs.map(j => (
                <tr key={j.trackingId}>
                  {isShown('status') && (
                    <td className="c-full">
                      <span className={`status st-${ST_CLASS[j.status]}`}>
                        <select
                          aria-label={`Status of ${j.title}`}
                          value={j.status}
                          onChange={e => onStatusChange(j.trackingId, e.target.value)}
                        >
                          {STATUS.map(s => <option key={s}>{s}</option>)}
                          <option value="Untracked">Untrack (remove)</option>
                        </select>
                      </span>
                    </td>
                  )}
                  {showJob && (
                    <td className="c-job">
                      <button className="rowlink" title={`${j.title} · ${j.co}`} onClick={() => onOpenDrawer(j)}>
                        {isShown('title') && <span className="job-title">{j.title}</span>}
                        {isShown('company') && <span className="job-co">{j.co}</span>}
                      </button>
                    </td>
                  )}
                  {isShown('location') && <td data-label="Location" className="clip" title={j.loc}>{j.loc}</td>}
                  {isShown('duration') && <td data-label="Duration" className="clip" title={j.dur}>{j.dur}</td>}
                  {isShown('minDuration') && <td data-label="Min. duration">{j.min}</td>}
                  {isShown('deadline') && <td data-label="Deadline" className="num"><DeadlineCell job={j} /></td>}
                  {isShown('submitted') && (
                    <td data-label="Submitted" className="num">{j.submittedAt ? formatDay(new Date(j.submittedAt)) : '—'}</td>
                  )}
                  {isShown('apply') && (
                    <td data-label="Apply">
                      {j.applyLink
                        ? <a className="textlink" href={j.applyLink} target="_blank" rel="noreferrer">Open <Icon name="external" size={13} /></a>
                        : '—'}
                    </td>
                  )}
                  {isShown('upload') && (
                    <td data-label="My uploads"><UploadCell job={j} onUploadCv={onUploadCv} onDeleteCv={onDeleteCv} /></td>
                  )}
                  <td className="c-open">
                    <button className="iconbtn" aria-label="Show details" title="Show details" onClick={() => onOpenDrawer(j)}>
                      <Icon name="chevronRight" />
                    </button>
                  </td>
                </tr>
              ))}
              {jobs.length > 0 && visibleJobs.length === 0 && (
                <tr className="empty-row">
                  <td colSpan={colSpan}>
                    No jobs match these filters. <button className="textlink" onClick={clearFilters}>Clear filters</button>
                  </td>
                </tr>
              )}
              {jobs.length === 0 && (
                <tr className="empty-row"><td colSpan={colSpan}>{addingOff ? 'No tracked jobs in this tab.' : 'No tracked jobs in this tab yet. Paste a link above or add jobs from Explore.'}</td></tr>
              )}
              {hiddenJobCount > 0 && <LockedRows onUnlock={onUnlock} colSpan={colSpan} />}
            </tbody>
          </table>
        </div>
      </div>

      <div className="sectionhead"><h2>Deadlines</h2></div>
      <div className="deadlines">
        <div className="card calcard">
          <Calendar jobs={jobs} onOpenJob={onOpenDrawer} />
        </div>
        <UpcomingDeadlines jobs={jobs} onOpenJob={onOpenDrawer} />
      </div>
    </section>
  )
}
