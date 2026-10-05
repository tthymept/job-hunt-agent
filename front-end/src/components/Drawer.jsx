// Old version: openDrawer(i) reached into the DOM and set
// .textContent / .innerHTML on six different elements by id, then
// added a class to #app. Here, the drawer just renders based on the
// `job` prop - when it's null the drawer is empty and slid offscreen
// by CSS (.app without .drawer-open); when App sets a job, this
// component re-renders with that job's data automatically.
export default function Drawer({ job, onClose }) {
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
          {job?.skills.map(s => <span className="tag" key={s}>{s}</span>)}
        </div>
        <h4>Job Description</h4>
        <div className="jd">{job?.jd}</div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
          <h4 style={{ margin: 0 }}>Suggested Bullets</h4>
          <button className="btn sm">↻ Refresh</button>
        </div>
        <div>
          {job?.bullets.map((b, i) => <div className="bullet" key={i}>{b}</div>)}
        </div>
      </div>
      <div className="drawer-foot">
        <button className="btn">↗ Open posting</button>
        <button className="btn primary">✎ Edit job</button>
      </div>
    </aside>
  )
}
