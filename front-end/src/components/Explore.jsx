// Builds a page-number list like [1, '…', 4, 5, 6, '…', 12] so we don't
// render 200+ page buttons when there are many pages.
function getPageNumbers(current, total) {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1)
  const pages = [1]
  if (current > 3) pages.push('…')
  for (let p = Math.max(2, current - 1); p <= Math.min(total - 1, current + 1); p++) pages.push(p)
  if (current < total - 2) pages.push('…')
  pages.push(total)
  return pages
}

export default function Explore({ jobs, onAdd, page, pageSize, total, onPageChange }) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const rangeStart = total === 0 ? 0 : (page - 1) * pageSize + 1
  const rangeEnd = Math.min(page * pageSize, total)

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
          <input type="search" defaultValue="Data, analytics, engineering..." style={{ width: 220 }} />
        </div>
        <div className="f">
          <label>Location</label>
          <select>
            <option>Singapore, Bangkok</option>
            <option>Singapore</option>
            <option>Bangkok</option>
          </select>
        </div>
        <div className="f">
          <label>Posted Date</label>
          <div className="seg">
            <button>Today</button><button>3 Days</button>
            <button className="active">Week</button>
            <button>Month</button><button>All</button>
          </div>
        </div>
        <div className="f" style={{ justifyContent: 'flex-end' }}>
          <label>&nbsp;</label>
          <button className="btn primary">🔍 Search</button>
        </div>
      </div>

      <div className="sectionhead">
        <h2>Recommended roles <span className="count">{total} jobs found</span></h2>
        <select>
          <option>Sort: Most relevant</option>
          <option>Sort: Deadline soonest</option>
        </select>
      </div>

      <div className="card tablewrap">
        <table>
          <thead>
            <tr>
              <th>Job #</th><th>Company</th><th>Job Title</th><th>Location</th><th>Duration</th>
              <th>Min. Duration</th><th>Deadline</th><th>Apply</th><th>Source</th><th></th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((j, i) => (
              <tr key={j.num}>
                <td>{j.num}</td><td>{j.co}</td><td className="job-title">{j.title}</td><td>{j.loc}</td>
                <td>{j.dur}</td><td>{j.min}</td><td>{j.dl}</td>
                <td><a className="applink" href={j.applyLink} target="_blank" rel="noreferrer">Open ↗</a></td>
                <td><span className="badge">{j.src}</span></td>
                <td>
                  {j.added ? (
                    <button className="addbtn added" disabled>✓ Added</button>
                  ) : (
                    <button className="addbtn" onClick={() => onAdd(i)}>+ Add to My Jobs</button>
                  )}
                </td>
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