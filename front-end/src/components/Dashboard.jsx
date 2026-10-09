import { useRef, useState } from 'react'
import { STATUS, ST_CLASS } from '../data'
import Calendar from './Calendar'

function UploadCell({ job, onUploadCv }) {
  const inputRef = useRef(null)
  if (job.myUploadUrl) {
    return <a className="filelink" href={job.myUploadUrl} target="_blank" rel="noreferrer">📎 View upload</a>
  }
  return (
    <>
      <button className="btn sm" onClick={() => inputRef.current.click()}>⬆ Upload</button>
      <input
        ref={inputRef}
        type="file"
        style={{ display: 'none' }}
        accept=".pdf,.docx"
        onChange={e => {
          const file = e.target.files[0]
          if (file) onUploadCv(job.trackingId, file)
        }}
      />
    </>
  )
}

export default function Dashboard({ jobs, onStatusChange, onOpenDrawer, onUploadCv, onOpenManualModal, onLoadFromUrl }) {
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
        <h2>Job tracker <span className="count">{jobs.length} jobs</span></h2>
        <div className="actions">
          <button className="btn sm">☰ Filter</button>
          <button className="btn sm">▤ Columns</button>
          <button className="btn sm primary" onClick={onOpenManualModal}>+ Add Job Manually</button>
        </div>
      </div>
      <div className="card tablewrap">
        <table>
          <thead>
            <tr>
              <th>Status</th><th>Company</th><th>Job Title</th><th>Location</th><th>Duration</th>
              <th>Min. Duration</th><th>Deadline</th><th>Apply Link</th><th>My Upload</th><th></th>
            </tr>
          </thead>
          <tbody>
            {jobs.map(j => (
              <tr key={j.trackingId}>
                <td>
                  <select
                    className={`pill st-${ST_CLASS[j.status]}`}
                    value={j.status}
                    onChange={e => onStatusChange(j.trackingId, e.target.value)}
                  >
                    {STATUS.map(s => <option key={s}>{s}</option>)}
                    <option value="Untracked" style={{ color: 'crimson' }}>🗑 Untrack</option>
                  </select>
                </td>
                <td>{j.co}</td>
                <td className="job-title">{j.title}</td>
                <td>{j.loc}</td>
                <td>{j.dur}</td>
                <td>{j.min}</td>
                <td>{j.dl}</td>
                <td><a className="applink" href={j.applyLink} target="_blank" rel="noreferrer">Open ↗</a></td>
                <td className="cvcell"><UploadCell job={j} onUploadCv={onUploadCv} /></td>
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