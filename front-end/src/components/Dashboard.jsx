import { STATUS, ST_CLASS } from '../data'
import Calendar from './Calendar'

function FileLink({ name }) {
  if (!name) return <span style={{ color: 'var(--muted)', fontSize: '12.5px' }}>No file</span>
  return <a className="filelink" href="#" onClick={e => e.preventDefault()}>📎 {name}</a>
}

// Old version: renderJobs() rebuilt the ENTIRE <tbody> as an HTML
// string every time anything changed, and changeStatus(sel) mutated
// jobs[i].status directly then manually fixed up one <select>'s
// className. Here, the table is just "jobs.map(...) -> <tr>"; when
// App's `jobs` state changes, React figures out only the one <select>
// and its pill color actually changed and updates just that - you
// never touch the DOM yourself.
export default function Dashboard({ jobs, onStatusChange, onOpenDrawer }) {
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
        <input type="text" placeholder="Paste job posting URL..." />
        <button className="btn">⬇ Load Job</button>
        <button className="btn primary">+ Add Job</button>
      </div>

      <div className="sectionhead">
        <h2>Job tracker <span className="count">{jobs.length} jobs</span></h2>
        <div className="actions">
          <button className="btn sm">☰ Filter</button>
          <button className="btn sm">▤ Columns</button>
        </div>
      </div>
      <div className="card tablewrap">
        <table>
          <thead>
            <tr>
              <th>Status</th><th>Company</th><th>Job Title</th><th>Location</th><th>Duration</th>
              <th>Min. Duration</th><th>Deadline</th><th>Apply Link</th><th>Agent CV</th><th>My Upload</th><th></th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((j, i) => (
              <tr key={j.co + j.title}>
                <td>
                  <select
                    className={`pill st-${ST_CLASS[j.status]}`}
                    value={j.status}
                    onChange={e => onStatusChange(i, e.target.value)}
                  >
                    {STATUS.map(s => <option key={s}>{s}</option>)}
                  </select>
                </td>
                <td>{j.co}</td>
                <td className="job-title">{j.title}</td>
                <td>{j.loc}</td>
                <td>{j.dur}</td>
                <td>{j.min}</td>
                <td>{j.dl}</td>
                <td><a className="applink" href="#" onClick={e => e.preventDefault()}>Open ↗</a></td>
                <td className="cvcell"><FileLink name={j.agent} /><span className="ai">AI-tailored</span></td>
                <td className="cvcell"><FileLink name={j.upload} /></td>
                <td><button className="chev" onClick={() => onOpenDrawer(j)}>›</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="sectionhead"><h2>Deadline calendar</h2></div>
      <div className="card" style={{ padding: 16 }}>
        <Calendar deadlineDays={[24, 28]} />
      </div>
    </section>
  )
}
