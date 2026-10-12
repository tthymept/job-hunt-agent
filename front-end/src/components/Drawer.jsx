import JobDescription from './JobDescription'

export default function Drawer({ job, onClose, onGenerate, onEdit, generating }) {
  // Jobs opened from Explore are flagged readOnly: no CV suggestions and no editing
  const readOnly = job?.readOnly

  return (
    <aside className="drawer">
      <div className="drawer-head">
        <button className="drawer-close" onClick={onClose}>✕</button>
        <div className="co">{job?.co}</div>
        <h3>{job?.title}</h3>
        <div className="meta">{job ? `${job.loc} · ${job.dur}` : ''}</div>
      </div>
      <div className="drawer-body">
        <h4>Required Skills</h4>
        <div className="tags">
          {(job?.skills || []).map(s => <span className="tag" key={s}>{s}</span>)}
        </div>
        <h4>Job Description</h4>
        <JobDescription text={job?.jd} />
        {!readOnly && (
          <>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
              <h4 style={{ margin: 0 }}>Suggested Bullets</h4>
              <button
                className={`btn sm${job?.bullets ? '' : ' primary'}`}
                disabled={generating}
                onClick={() => job && onGenerate(job.trackingId)}
              >
                {generating ? 'Generating…' : job?.bullets ? '↻ Refresh' : '✨ Generate'}
              </button>
            </div>
            <div>
              {job?.bullets ? (
                job.bullets.length > 0 ? (
                  job.bullets.map((g, i) => (
                    <div key={i} style={{ marginBottom: 12 }}>
                      <div className="bullet-label">{g.label}</div>
                      {g.lines.map((line, j) => <div className="bullet" key={j}>{line}</div>)}
                    </div>
                  ))
                ) : (
                  <div className="jd" style={{ marginBottom: 0 }}>
                    None of your CV entries were close enough to this job to suggest changes.
                  </div>
                )
              ) : (
                <div className="jd" style={{ marginBottom: 0 }}>Not generated yet — click Generate above.</div>
              )}
            </div>
          </>
        )}
      </div>
      <div className="drawer-foot">
        <button className="btn" onClick={() => job?.applyLink && window.open(job.applyLink, '_blank')}>↗ Open posting</button>
        {!readOnly && (
          <button className="btn primary" onClick={() => job && onEdit(job)}>✎ Edit job</button>
        )}
      </div>
    </aside>
  )
}