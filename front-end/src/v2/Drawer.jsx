import { useEffect, useRef, useState } from 'react'
import JobDescription from '../components/JobDescription'
import { ST_CLASS } from '../data'
import Icon from './Icon'
import { prettyDay } from './dates'

// Puts text on the clipboard. The Clipboard API only exists on https and
// localhost, so a phone opening the dev server by its network address falls
// back to the older copy command. Returns false when neither worked.
async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    const area = document.createElement('textarea')
    area.value = text
    area.setAttribute('readonly', '')
    area.style.position = 'fixed'
    area.style.opacity = '0'
    document.body.appendChild(area)
    area.select()
    const ok = document.execCommand('copy')
    area.remove()
    return ok
  }
}

// A copy button that shows a tick for a moment once the text is copied.
// With a label it is a small text button, without one an icon button.
function CopyButton({ text, label }) {
  const [copied, setCopied] = useState(false)
  const timer = useRef(null)
  useEffect(() => () => clearTimeout(timer.current), [])

  async function handleCopy() {
    if (!(await copyText(text))) return
    setCopied(true)
    clearTimeout(timer.current)
    timer.current = setTimeout(() => setCopied(false), 1500)
  }

  const icon = <Icon name={copied ? 'check' : 'copy'} size={label ? 13 : 14} />
  const title = copied ? 'Copied' : label || 'Copy this line'
  return label ? (
    <button className="btn sm quiet" title={title} onClick={handleCopy}>{icon} {copied ? 'Copied' : label}</button>
  ) : (
    <button className="iconbtn" title={title} aria-label={title} onClick={handleCopy}>{icon}</button>
  )
}

export default function Drawer({ job, tabs = [], onMoveJob, onClose, onGenerate, onEdit, generating }) {
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
          {/* Tracked jobs can be moved to another tab, as long as that tab accepts new jobs */}
          {job && !readOnly && tabs.length > 1 && (
            <div className="facts-wide">
              <dt><label htmlFor="drawerTab">Tab</label></dt>
              <dd>
                <select id="drawerTab" value={job.tabId} onChange={e => onMoveJob(job.trackingId, Number(e.target.value))}>
                  {tabs.map(t => (
                    <option key={t.id} value={t.id} disabled={!t.enabled && t.id !== job.tabId}>
                      {t.name}{t.enabled ? '' : ' (adding off)'}
                    </option>
                  ))}
                </select>
              </dd>
            </div>
          )}
        </dl>

        <h4>Required skills</h4>
        <div className="tags">
          {(job?.skills || []).map(s => <span className="tag" key={s}>{s}</span>)}
          {job && (job.skills || []).length === 0 && <span className="none">None listed.</span>}
        </div>

        <h4>Job description</h4>
        <JobDescription text={job?.jd} />

        {!readOnly && job?.locked && (
          <>
            <h4>Suggested bullets</h4>
            {/* The server leaves the bullets out for a guest: they are the owner's CV */}
            <div className="none">Hidden in guest mode. Enter the access key to see the tailored CV bullets.</div>
          </>
        )}
        {!readOnly && !job?.locked && (
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
                  <>
                    {/* Generated before rewrites were saved with their lines: nothing to compare yet */}
                    {!job.bullets.some(g => g.lines.some(line => line.original)) && (
                      <div className="none bullet-note">Click Refresh to see each rewrite next to your original line.</div>
                    )}
                    {job.bullets.map((g, i) => (
                      <div key={i} className="bullet-group">
                        <div className="bullet-head">
                          <span className="bullet-label">{g.label}</span>
                          <CopyButton text={g.lines.map(line => line.text).join('\n')} label="Copy all" />
                        </div>
                        {g.lines.map((line, j) => (
                          <div className="bullet" key={j}>
                            {line.original && (
                              <div className="bullet-was"><span className="bullet-tag">Original</span>{line.original}</div>
                            )}
                            <div className="bullet-now">
                              <span className="bullet-text">{line.text}</span>
                              <CopyButton text={line.text} />
                            </div>
                          </div>
                        ))}
                      </div>
                    ))}
                  </>
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
