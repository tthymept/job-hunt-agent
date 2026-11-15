import { useState, useEffect } from 'react'
import InterestsModal from '../components/InterestsModal'
import { apiFetch, readJson } from '../api'
import Icon from './Icon'
import { prettyDay } from './dates'

function getPageNumbers(current, total) {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1)
  const pages = [1]
  if (current > 3) pages.push('…')
  for (let p = Math.max(2, current - 1); p <= Math.min(total - 1, current + 1); p++) pages.push(p)
  if (current < total - 2) pages.push('…')
  pages.push(total)
  return pages
}

const POSTED_DATE_OPTIONS = [
  { value: 'today', label: 'Today' },
  { value: '3days', label: '3 days' },
  { value: 'week', label: 'Week' },
  { value: 'month', label: 'Month' },
  { value: 'all', label: 'All' },
]

export default function Explore({ jobs, onAdd, page, pageSize, total, onPageChange, sort, onSortChange, filters, onApplyFilters, onOpenDrawer }) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const rangeStart = total === 0 ? 0 : (page - 1) * pageSize + 1
  const rangeEnd = Math.min(page * pageSize, total)

  // Draft values - what the user is currently typing/selecting, separate
  // from `filters`, which is what's actually been applied to the fetch.
  const [draftRole, setDraftRole] = useState(filters.role)
  const [draftLocation, setDraftLocation] = useState(filters.location)
  const [draftPostedDate, setDraftPostedDate] = useState(filters.postedDate)
  const [interestsOpen, setInterestsOpen] = useState(false)
  // Location options are the places in your search interests: [{ value, label }]
  const [locations, setLocations] = useState([])

  function loadLocations() {
    apiFetch(`/api/explore-locations`)
      .then(readJson)
      .then(setLocations)
      .catch(err => console.error('Failed to load locations:', err))
  }

  useEffect(loadLocations, [])

  function handleSearch() {
    onApplyFilters({ role: draftRole, location: draftLocation, postedDate: draftPostedDate })
  }

  function handleCloseInterests() {
    setInterestsOpen(false)
    loadLocations()
    // A fresh filters object makes App refetch, so jobs from a finished backfill show up
    onApplyFilters({ ...filters })
  }

  return (
    <section>
      <div className="pagehead">
        <div>
          <h1>Explore Jobs</h1>
          <p>Find relevant internships and add them directly to your pipeline.</p>
        </div>
        <button className="btn" onClick={() => setInterestsOpen(true)}><Icon name="target" /> Search interests</button>
      </div>

      <div className="card filterbar">
        <div className="f f-grow">
          <label htmlFor="exploreRole">Role</label>
          <div className="inputwrap">
            <Icon name="search" size={15} />
            <input
              id="exploreRole"
              type="search"
              placeholder="Data, analytics, engineering..."
              value={draftRole}
              onChange={e => setDraftRole(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSearch()}
            />
          </div>
        </div>
        <div className="f">
          <label htmlFor="exploreLocation">Location</label>
          <select id="exploreLocation" value={draftLocation} onChange={e => setDraftLocation(e.target.value)}>
            <option value="all">All locations</option>
            {locations.map(l => <option key={l.value} value={l.value}>{l.label}</option>)}
          </select>
        </div>
        <div className="f">
          <label>Posted</label>
          <div className="seg" role="group" aria-label="Posted date">
            {POSTED_DATE_OPTIONS.map(opt => (
              <button
                key={opt.value}
                className={draftPostedDate === opt.value ? 'active' : ''}
                aria-pressed={draftPostedDate === opt.value}
                onClick={() => setDraftPostedDate(opt.value)}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
        <div className="f f-submit">
          <button className="btn primary" onClick={handleSearch}>Search</button>
        </div>
      </div>

      <div className="card tablecard">
        <div className="toolbar">
          <h2>Recommended roles <span className="count">{total}</span></h2>
          <div className="toolbar-tools">
            <select aria-label="Sort" value={sort} onChange={e => onSortChange(e.target.value)}>
              <option value="relevance">Sort: Most relevant</option>
              <option value="deadline">Sort: Deadline soonest</option>
            </select>
          </div>
        </div>
        <div className="tablewrap">
          <table className="cards">
            <thead>
              <tr>
                <th></th><th>Job</th><th>Location</th><th>Duration</th>
                <th>Min. Duration</th><th>Deadline</th><th>Apply</th><th>Date Posted</th><th>Source</th><th></th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j, i) => (
                <tr key={j.jobId}>
                  <td className="c-full">
                    {j.trackState === 'added' ? (
                      <span className="added"><Icon name="check" size={14} /> Added</span>
                    ) : j.trackState === 'untracked' ? (
                      <button className="btn sm addbtn" title="Add back to my jobs" onClick={() => onAdd(i)}>
                        <Icon name="refresh" size={13} /> Retrack
                      </button>
                    ) : (
                      <button className="btn sm addbtn" title="Add to my jobs" onClick={() => onAdd(i)}>
                        <Icon name="plus" size={13} /> Add
                      </button>
                    )}
                  </td>
                  <td className="c-job">
                    <button className="rowlink" title={`${j.title} · ${j.co}`} onClick={() => onOpenDrawer({ ...j, readOnly: true })}>
                      <span className="job-title">{j.title}</span>
                      <span className="job-co">{j.co}</span>
                    </button>
                  </td>
                  <td data-label="Location" className="clip" title={j.loc}>{j.loc}</td>
                  <td data-label="Duration" className="clip" title={j.dur}>{j.dur}</td>
                  <td data-label="Min. duration">{j.min}</td>
                  <td data-label="Deadline" className="num">{prettyDay(j.dl)}</td>
                  <td data-label="Apply">
                    <a className="textlink" href={j.applyLink} target="_blank" rel="noreferrer">Open <Icon name="external" size={13} /></a>
                  </td>
                  <td data-label="Posted" className="num">{prettyDay(j.posted)}</td>
                  <td data-label="Source"><span className="badge">{j.src}</span></td>
                  <td className="c-open">
                    <button className="iconbtn" aria-label="Show details" title="Show details" onClick={() => onOpenDrawer({ ...j, readOnly: true })}>
                      <Icon name="chevronRight" />
                    </button>
                  </td>
                </tr>
              ))}
              {jobs.length === 0 && (
                <tr className="empty-row"><td colSpan={10}>No jobs match these filters.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="pagination">
        <span>{pageSize} jobs per page</span>
        <div className="pagenums">
          <button aria-label="Previous page" disabled={page === 1} onClick={() => onPageChange(page - 1)}><Icon name="chevronLeft" size={15} /></button>
          {getPageNumbers(page, totalPages).map((p, i) =>
            p === '…' ? (
              <span key={`ellipsis-${i}`}>…</span>
            ) : (
              <button key={p} className={p === page ? 'active' : ''} aria-current={p === page ? 'page' : undefined} onClick={() => onPageChange(p)}>
                {p}
              </button>
            )
          )}
          <button aria-label="Next page" disabled={page === totalPages} onClick={() => onPageChange(page + 1)}><Icon name="chevronRight" size={15} /></button>
        </div>
        <span>{rangeStart}–{rangeEnd} of {total} jobs</span>
      </div>

      <InterestsModal open={interestsOpen} onClose={handleCloseInterests} />
    </section>
  )
}
