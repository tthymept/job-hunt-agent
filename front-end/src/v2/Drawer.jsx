import { useEffect } from 'react'
import JobDescription from '../components/JobDescription'
import { ST_CLASS } from '../data'
import Icon from './Icon'
import { prettyDay } from './dates'

export default function Drawer({ job, onClose, onGenerate, onEdit, generating }) {
  // Jobs opened from Explore are flagged readOnly: no CV suggestions and no editing
  const readOnly = job?.readOnly

  // Esc closes the panel while it is open
  useEffect(() => {
    if (!job) return
    const onKey = e => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [job, onClose])

  const facts = job
    ? [
        ['Location', job.loc],
        ['Duration', job.dur],
        ['Min. duration', job.min],
        ['Deadline', prettyDay(job.dl)],
      ]
    : []

  return (
    <aside className="drawer" aria-hidden={!job}>
      <div className="drawer-head">
        <button className="iconbtn drawer-close" aria-label="Close details" onClick={onClose}><Icon name="close" /></button>
        <div className="co">{job?.co}</div>
        <h3>{job?.title}</h3>
        {job && !readOnly && job.status && (
          <span className={`status static st-${ST_CLASS[job.status]}`}>{job.status}</span>
        )}
      </div>
      <div className="drawer-body">
        <dl className="facts">
          {facts.map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{value || '—'}</dd>
            </div>
          ))}
        </dl>

        <h4>Required skills</h4>
        <div className="tags">
          {(job?.skills || []).map(s => <span className="tag" key={s}>{s}</span>)}
          {job && (job.skills || []).length === 0 && <span className="none">None listed.</span>}
        </div>

        <h4>Job description</h4>
        <JobDescription text={job?.jd} />

        {!readOnly && (
          <>
            <div className="drawer-row">
              <h4>Suggested bullets</h4>
              <button
                className={`btn sm${job?.bullets ? '' : ' primary'}`}
                disabled={generating}
                onClick={() => job && onGenerate(job.trackingId)}
              >
                {generating ? 'Generating…' : job?.bullets ? <><Icon name="refresh" size={13} /> Refresh</> : 'Generate'}
              </button>
            </div>
            <div>
              {job?.bullets ? (
                job.bullets.length > 0 ? (
                  job.bullets.map((g, i) => (
                    <div key={i} className="bullet-group">
                      <div className="bullet-label">{g.label}</div>
                      {g.lines.map((line, j) => <div className="bullet" key={j}>{line}</div>)}
                    </div>
                  ))
                ) : (
                  <div className="none">
                    None of your CV entries were close enough to this job to suggest changes.
                  </div>
                )
              ) : (
                <div className="none">Not generated yet. Click Generate to tailor your CV bullets to this job.</div>
              )}
            </div>
          </>
        )}
      </div>
      <div className="drawer-foot">
        <button className="btn" disabled={!job?.applyLink} onClick={() => job?.applyLink && window.open(job.applyLink, '_blank')}>
          <Icon name="external" size={15} /> Open posting
        </button>
        {!readOnly && (
          <button className="btn primary" onClick={() => job && onEdit(job)}><Icon name="pencil" size={15} /> Edit job</button>
        )}
      </div>
    </aside>
  )
}
