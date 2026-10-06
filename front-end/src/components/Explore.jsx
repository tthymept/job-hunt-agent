import { useState } from 'react'

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
  { value: '3days', label: '3 Days' },
  { value: 'week', label: 'Week' },
  { value: 'month', label: 'Month' },
  { value: 'all', label: 'All' },
]

export default function Explore({ jobs, onAdd, page, pageSize, total, onPageChange, sort, onSortChange, filters, onApplyFilters }) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const rangeStart = total === 0 ? 0 : (page - 1) * pageSize + 1
  const rangeEnd = Math.min(page * pageSize, total)

  // Draft values - what the user is currently typing/selecting, separate
  // from `filters`, which is what's actually been applied to the fetch.
  const [draftRole, setDraftRole] = useState(filters.role)
  const [draftLocation, setDraftLocation] = useState(filters.location)
  const [draftPostedDate, setDraftPostedDate] = useState(filters.postedDate)

  function handleSearch() {
    onApplyFilters({ role: draftRole, location: draftLocation, postedDate: draftPostedDate })
  }

  return (
    <section>
      <div className="pagehead">
        <div>
          <h1>Explore Jobs</h1>
          <p>Find relevant internships and add them directly to your pipeline.</p>
        </div>
        <button className="btn">📑 Saved searches</button>
      </div>

      <div className="card filterbar">
        <div className="f">
          <label>Role</label>
          <input
            type="search"
            placeholder="Data, analytics, engineering..."
            value={draftRole}
            onChange={e => setDraftRole(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleSearch()}
            style={{ width: 220 }}
          />
        </div>
        <div className="f">
          <label>Location</label>
          <select value={draftLocation} onChange={e => setDraftLocation(e.target.value)}>
            <option value="all">All locations</option>
            <option value="singapore">Singapore</option>
            <option value="bangkok">Bangkok</option>
          </select>
        </div>
        <div className="f">
          <label>Posted Date</label>
          <div className="seg">
            {POSTED_DATE_OPTIONS.map(opt => (
              <button
                key={opt.value}
                className={draftPostedDate === opt.value ? 'active' : ''}
                onClick={() => setDraftPostedDate(opt.value)}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
        <div className="f" style={{ justifyContent: 'flex-end' }}>
          <label>&nbsp;</label>
          <button className="btn primary" onClick={handleSearch}>🔍 Search</button>
        </div>
      </div>

      <div className="sectionhead">
        <h2>Recommended roles <span className="count">{total} jobs found</span></h2>
        <select value={sort} onChange={e => onSortChange(e.target.value)}>
          <option value="relevance">Sort: Most relevant</option>
          <option value="deadline">Sort: Deadline soonest</option>
        </select>
      </div>

      <div className="card tablewrap">
        <table>
          <thead>
            <tr>
              <th></th><th>Company</th><th>Job Title</th><th>Location</th><th>Duration</th>
              <th>Min. Duration</th><th>Deadline</th><th>Apply</th><th>Source</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((j, i) => (
              <tr key={j.jobId}>
                <td>
                  {j.trackState === 'added' ? (
                    <button className="addbtn added" disabled>
                      <span className="icon">✓</span><span className="label">Added</span>
                    </button>
                  ) : j.trackState === 'untracked' ? (
                    <button className="addbtn" onClick={() => onAdd(i)}>
                      <span className="icon">↺</span><span className="label">Retrack</span>
                    </button>
                  ) : (
                    <button className="addbtn" onClick={() => onAdd(i)}>
                      <span className="icon">+</span><span className="label">Add to My Jobs</span>
                    </button>
                  )}
                </td>
                <td>{j.co}</td><td className="job-title">{j.title}</td><td>{j.loc}</td>
                <td>{j.dur}</td><td>{j.min}</td><td>{j.dl}</td>
                <td><a className="applink" href={j.applyLink} target="_blank" rel="noreferrer">Open ↗</a></td>
                <td><span className="badge">{j.src}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="pagination">
        <span>{pageSize} jobs per page</span>
        <div className="pagenums">
          <button disabled={page === 1} onClick={() => onPageChange(page - 1)}>‹</button>
          {getPageNumbers(page, totalPages).map((p, i) =>
            p === '…' ? (
              <span key={`ellipsis-${i}`}>…</span>
            ) : (
              <button key={p} className={p === page ? 'active' : ''} onClick={() => onPageChange(p)}>
                {p}
              </button>
            )
          )}
          <button disabled={page === totalPages} onClick={() => onPageChange(page + 1)}>›</button>
        </div>
        <span>{rangeStart}–{rangeEnd} of {total} jobs</span>
      </div>
    </section>
  )
}