import { useEffect, useRef, useState } from 'react'
import { STATUS, ST_CLASS } from '../data'
import { blockedForGuest, isGuest, openFileLink } from '../api'
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

// What each sort compares. null means "no value" (ASAP deadline, no submitted
// date, …) and always goes last, whichever way the column is sorted, as in Excel.
const SORT_VALUES = {
  status: j => STATUS.indexOf(j.status), // pipeline order, not alphabetical
  company: j => j.co || null,
  title: j => j.title || null,
  location: j => (j.loc && j.loc !== '—' ? j.loc : null),
  duration: j => (j.dur && j.dur !== '—' ? j.dur : null),
  minDuration: j => parseInt(j.min, 10) || null,
  deadline: j => parseDay(j.dl)?.getTime() ?? null,
  submitted: j => (j.submittedAt ? Date.parse(j.submittedAt) : null),
  // Tracking ids count up as jobs are added, so this is the original order, before any arrow moves
  added: j => j.trackingId,
}

// The choices in each header's sort menu. `column` is the header that shows the
// menu: Job holds both company and title, so it offers both. Date added sits on
// the arrows column, since it is about the order itself.
const SORT_OPTIONS = [
  { column: 'added', key: 'added', dir: 'asc', label: 'Oldest first (original order)' },
  { column: 'added', key: 'added', dir: 'desc', label: 'Newest first' },
  { column: 'status', key: 'status', dir: 'asc', label: 'Pipeline order' },
  { column: 'status', key: 'status', dir: 'desc', label: 'Reverse pipeline order' },
  { column: 'job', key: 'company', dir: 'asc', label: 'Company A → Z' },
  { column: 'job', key: 'company', dir: 'desc', label: 'Company Z → A' },
  { column: 'job', key: 'title', dir: 'asc', label: 'Title A → Z' },
  { column: 'job', key: 'title', dir: 'desc', label: 'Title Z → A' },
  { column: 'location', key: 'location', dir: 'asc', label: 'A → Z' },
  { column: 'location', key: 'location', dir: 'desc', label: 'Z → A' },
  { column: 'duration', key: 'duration', dir: 'asc', label: 'A → Z' },
  { column: 'duration', key: 'duration', dir: 'desc', label: 'Z → A' },
  { column: 'minDuration', key: 'minDuration', dir: 'asc', label: 'Shortest first' },
  { column: 'minDuration', key: 'minDuration', dir: 'desc', label: 'Longest first' },
  { column: 'deadline', key: 'deadline', dir: 'asc', label: 'Earliest first' },
  { column: 'deadline', key: 'deadline', dir: 'desc', label: 'Latest first' },
  { column: 'submitted', key: 'submitted', dir: 'asc', label: 'Earliest first' },
  { column: 'submitted', key: 'submitted', dir: 'desc', label: 'Latest first' },
]
const SORT_COLUMN_LABELS = { added: 'Date added', status: 'Status', job: 'Job', location: 'Location', duration: 'Duration', minDuration: 'Min. duration', deadline: 'Deadline', submitted: 'Submitted' }

function findSortOption(sort) {
  return sort ? SORT_OPTIONS.find(o => o.key === sort.key && o.dir === sort.dir) || null : null
}

// A copy of the list in the chosen order. Array sort keeps equal items in their
// existing order, so jobs that tie stay in My order.
function sortJobs(list, sort) {
  if (!sort) return list
  const value = SORT_VALUES[sort.key]
  const flip = sort.dir === 'desc' ? -1 : 1
  return [...list].sort((a, b) => {
    const x = value(a)
    const y = value(b)
    if (x == null || y == null) return (x == null) - (y == null)
    const diff = typeof x === 'string' ? x.localeCompare(y, undefined, { numeric: true, sensitivity: 'base' }) : x - y
    return diff * flip
  })
}

// The sort is remembered on this device, like the column choice. null = My order.
const SORT_STORAGE = 'jobHuntSort'

function loadSort() {
  try {
    const saved = JSON.parse(localStorage.getItem(SORT_STORAGE))
    return findSortOption(saved) ? { key: saved.key, dir: saved.dir } : null
  } catch {
    return null
  }
}

// A sortable column header: its label opens a small menu of sort choices, like
// the filter button on an Excel column. The table scrolls sideways, which would
// clip a menu inside it, so the menu is placed on the page under the header.
// With iconOnly the header shows just the arrow (the narrow arrows column).
function SortHeader({ column, label, sort, onSort, iconOnly = false, className }) {
  const [menuAt, setMenuAt] = useState(null) // { top, left } while open
  const buttonRef = useRef(null)
  const options = SORT_OPTIONS.filter(o => o.column === column)
  const active = options.find(o => sort && o.key === sort.key && o.dir === sort.dir)

  // The menu is pinned to where the header was, so scrolling or resizing closes it
  useEffect(() => {
    if (!menuAt) return
    const close = () => setMenuAt(null)
    window.addEventListener('scroll', close, true)
    window.addEventListener('resize', close)
    return () => {
      window.removeEventListener('scroll', close, true)
      window.removeEventListener('resize', close)
    }
  }, [menuAt])

  function toggle() {
    if (menuAt) return setMenuAt(null)
    const rect = buttonRef.current.getBoundingClientRect()
    setMenuAt({ top: rect.bottom + 6, left: Math.max(8, Math.min(rect.left - 8, window.innerWidth - 228)) })
  }

  function choose(option) {
    onSort(option ? { key: option.key, dir: option.dir } : null)
    setMenuAt(null)
  }

  return (
    <th className={className} aria-sort={active ? (active.dir === 'asc' ? 'ascending' : 'descending') : undefined}>
      <button
        ref={buttonRef}
        className={`th-sort${active ? ' active' : ''}`}
        aria-haspopup="menu"
        aria-expanded={Boolean(menuAt)}
        aria-label={iconOnly ? `Sort by ${label.toLowerCase()}` : undefined}
        title={`Sort by ${label.toLowerCase()}`}
        onClick={toggle}
      >
        {!iconOnly && label}
        <Icon name={active ? (active.dir === 'asc' ? 'arrowUp' : 'arrowDown') : 'chevronDown'} size={13} />
      </button>
      {menuAt && (
        <>
          <div className="pop-shade" onClick={() => setMenuAt(null)} />
          <div className="popover menu sort-menu" role="menu" style={menuAt}>
            {options.map(o => (
              <button key={`${o.key}-${o.dir}`} role="menuitemradio" aria-checked={o === active} className="menu-item" onClick={() => choose(o)}>
                <span className="menu-check">{o === active && <Icon name="check" size={14} />}</span>
                {o.label}
              </button>
            ))}
            {sort && (
              <button role="menuitem" className="menu-item" onClick={() => choose(null)}>
                <span className="menu-check" />
                Back to my order
              </button>
            )}
          </div>
        </>
      )}
    </th>
  )
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

export default function Dashboard({ jobs, hiddenJobCount, tabs, activeTab, tabCounts, onSelectTab, tabActions, tabError, onDismissTabError, onUnlock, onStatusChange, onReorder, onOpenDrawer, onUploadCv, onDeleteCv, onOpenManualModal, onLoadFromUrl }) {
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
  // Guests can't change the order, so they get no arrows
  const canReorder = Boolean(activeTab) && !isGuest()
  const colSpan = headColumns.length + 1 + (canReorder ? 1 : 0) // + the details arrow and the move arrows

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

  // ---------- Sorting and My order ----------
  // `jobs` arrives in My order (the order saved with the arrows). A sort only
  // changes what is shown; clearing it brings My order straight back.
  const [sort, setSort] = useState(loadSort)
  const sortOption = findSortOption(sort)
  const shownJobs = sortJobs(visibleJobs, sort)

  function changeSort(next) {
    setSort(next)
    try {
      if (next) localStorage.setItem(SORT_STORAGE, JSON.stringify(next))
      else localStorage.removeItem(SORT_STORAGE)
    } catch {
      // Storage unavailable: the sort still applies until the page is reloaded
    }
  }

  // Swaps a job with the row shown above (-1) or below (+1) it. With a filter on,
  // that neighbour may not be next to it in the full list; they still swap places.
  function moveJob(job, step) {
    const neighbour = visibleJobs[visibleJobs.indexOf(job) + step]
    if (!neighbour) return
    const ids = jobs.map(j => j.trackingId)
    const a = ids.indexOf(job.trackingId)
    const b = ids.indexOf(neighbour.trackingId)
    ;[ids[a], ids[b]] = [ids[b], ids[a]]
    onReorder(ids)
  }

  // Keeps the sorted view as My order, then shows My order (which now looks the same)
  function saveSortAsMyOrder() {
    onReorder(sortJobs(jobs, sort).map(j => j.trackingId))
    changeSort(null)
  }

  // Columns the header turns into sort menus; others stay plain labels
  const sortableColumns = new Set(SORT_OPTIONS.map(o => o.column))

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
          <div className="toolbar-title">
            <h2>
              Job tracker
              <span className="count">
                {filtering ? `${visibleJobs.length} of ${jobCountLabel}` : jobCountLabel}
              </span>
            </h2>
            {/* While sorted: what the sort is, a way back to My order, and a way to keep it */}
            {sortOption && (
              <>
                <span className="sort-chip">
                  <Icon name={sortOption.dir === 'asc' ? 'arrowUp' : 'arrowDown'} size={13} />
                  {SORT_COLUMN_LABELS[sortOption.column]} · {sortOption.label}
                  <button className="iconbtn" aria-label="Back to my order" title="Back to my order" onClick={() => changeSort(null)}>
                    <Icon name="close" size={13} />
                  </button>
                </span>
                {canReorder && (
                  <button className="btn sm quiet" title="Keep this order as My order, so the arrows start from it" onClick={saveSortAsMyOrder}>
                    Save as my order
                  </button>
                )}
              </>
            )}
          </div>
          <div className="toolbar-tools">
            {/* Phones show cards without a header row, so sorting moves into this dropdown */}
            <select
              className="sort-select"
              aria-label="Sort"
              value={sortOption ? `${sortOption.key}:${sortOption.dir}` : ''}
              onChange={e => {
                const [key, dir] = e.target.value.split(':')
                changeSort(key ? { key, dir } : null)
              }}
            >
              <option value="">My order</option>
              {SORT_OPTIONS.map(o => (
                <option key={`${o.key}:${o.dir}`} value={`${o.key}:${o.dir}`}>
                  {SORT_COLUMN_LABELS[o.column]} · {o.label}
                </option>
              ))}
            </select>
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
                {canReorder && (
                  <SortHeader column="added" label="Date added" sort={sort} onSort={changeSort} iconOnly className="c-move" />
                )}
                {headColumns.map(c =>
                  sortableColumns.has(c.key)
                    ? <SortHeader key={c.key} column={c.key} label={c.label} sort={sort} onSort={changeSort} />
                    : <th key={c.key}>{c.label}</th>
                )}
                <th></th>
              </tr>
            </thead>
            <tbody>
              {shownJobs.map((j, i) => (
                <tr key={j.trackingId} className={canReorder ? 'can-move' : undefined}>
                  {canReorder && (
                    <td className="c-move">
                      {/* The arrows move a job in My order, so they rest while a sort is on */}
                      <span className="move-btns" title={sortOption ? 'Clear the sort to reorder' : undefined}>
                        <button
                          className="iconbtn"
                          aria-label={`Move ${j.title} up`}
                          title={sortOption ? undefined : 'Move up'}
                          disabled={Boolean(sortOption) || i === 0}
                          onClick={() => moveJob(j, -1)}
                        >
                          <Icon name="chevronUp" size={14} />
                        </button>
                        <button
                          className="iconbtn"
                          aria-label={`Move ${j.title} down`}
                          title={sortOption ? undefined : 'Move down'}
                          disabled={Boolean(sortOption) || i === shownJobs.length - 1}
                          onClick={() => moveJob(j, 1)}
                        >
                          <Icon name="chevronDown" size={14} />
                        </button>
                      </span>
                    </td>
                  )}
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
