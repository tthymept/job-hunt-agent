export default function Drawer({ job, onClose, onGenerate, onEdit, generating }) {
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
        <div className="jd">{job?.jd}</div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
          <h4 style={{ margin: 0 }}>Suggested Bullets</h4>
          <button
            className={`btn sm${job?.bullets ? '' : ' primary'}`}
            disabled={generating}
            onClick={() => job && onGenerate(job.trackingId)}
          >
            {generating ? '…' : job?.bullets ? '↻ Refresh' : '✨ Generate'}
          </button>
        </div>
        <div>
          {job?.bullets
            ? job.bullets.map((b, i) => <div className="bullet" key={i}>{b}</div>)
            : <div className="jd" style={{ marginBottom: 0 }}>Not generated yet — click Generate above.</div>}
        </div>
      </div>
      <div className="drawer-foot">
        <button className="btn" onClick={() => job?.applyLink && window.open(job.applyLink, '_blank')}>↗ Open posting</button>
        <button className="btn primary" onClick={() => job && onEdit(job)}>✎ Edit job</button>
      </div>
    </aside>
  )
}