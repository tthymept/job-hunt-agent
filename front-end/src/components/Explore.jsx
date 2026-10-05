// Old version: addJob(i, btn) mutated exploreJobs[i].added AND manually
// replaced the clicked button's outerHTML with a disabled one. Here,
// onAdd(i) just flips `added` in state; the ternary below decides
// which button to render. React swaps them for you.
export default function Explore({ jobs, onAdd }) {
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
        <h2>Recommended roles <span className="count">228 matches based on your CV and preferences</span></h2>
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
                <td><a className="applink" href="#" onClick={e => e.preventDefault()}>Open ↗</a></td>
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
        <span>20 jobs per page</span>
        <div className="pagenums">
          <button className="active">1</button><button>2</button><button>3</button>
          <span>…</span><button>12</button>
        </div>
        <span>1–20 of 228 jobs</span>
      </div>
    </section>
  )
}
