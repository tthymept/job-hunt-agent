import { useEffect, useState } from 'react'
import { ST_CLASS } from '../data'
import { STAGE_DETAILS } from './stages'
import { dayOf, daysBetween, formatDay, shortDay, timeOf, toDateInput, toDateTimeInput } from './dates'

// A field that keeps what you type and saves when you leave it (or press Enter
// in a one-line field), so a half-typed date is never sent. onSave may return
// false (or a promise of false) when saving failed: the field then goes back.
function SavedField({ value, onSave, as: Tag = 'input', ...props }) {
  const [draft, setDraft] = useState(value)
  useEffect(() => setDraft(value), [value])

  function commit() {
    if (draft === value) return
    Promise.resolve(onSave(draft)).then(ok => {
      if (ok === false) setDraft(value)
    })
  }

  return (
    <Tag
      {...props}
      value={draft}
      onChange={e => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={Tag === 'input' ? e => { if (e.key === 'Enter') e.currentTarget.blur() } : undefined}
    />
  )
}

// "9 days after Submitted"
function gapLabel(days, previous) {
  if (days < 0) return { text: `Dated before ${previous}`, warn: true }
  if (days === 0) return { text: `Same day as ${previous}` }
  return { text: `${days} day${days === 1 ? '' : 's'} after ${previous}` }
}

function scheduledText(stage, kind) {
  if (!stage.scheduledAt) return null
  const when = new Date(stage.scheduledAt)
  return kind === 'datetime' ? `${shortDay(when)}, ${timeOf(when)}` : formatDay(when)
}

// A stage's own details: when it is due or happening, whether it is done, a note
function StageDetails({ job, stage, locked, onStageChange }) {
  const config = STAGE_DETAILS[stage.status] || {}
  const save = changes => onStageChange(job.trackingId, stage.id, changes)

  if (locked) {
    const when = scheduledText(stage, config.scheduledKind)
    if (!when && !stage.done) return null
    return (
      <div className="tl-summary">
        {when && `${config.scheduledLabel} ${when}`}
        {when && stage.done && ' · '}
        {stage.done && config.doneLabel}
      </div>
    )
  }

  return (
    <div className="stage-details">
      {config.scheduledLabel && (
        <label className="stage-field">
          <span>{config.scheduledLabel}</span>
          {config.scheduledKind === 'datetime' ? (
            <SavedField
              type="datetime-local"
              value={toDateTimeInput(stage.scheduledAt)}
              onSave={v => save({ scheduled_at: v ? new Date(v).toISOString() : null })}
            />
          ) : (
            <SavedField
              type="date"
              value={toDateInput(stage.scheduledAt)}
              onSave={v => save({ scheduled_at: v || null })}
            />
          )}
        </label>
      )}
      {config.doneLabel && (
        <label className="stage-check">
          <input type="checkbox" checked={stage.done} onChange={e => save({ done: e.target.checked })} />
          {config.doneLabel}
        </label>
      )}
      <SavedField
        as="textarea"
        rows={2}
        aria-label={`Note for ${stage.status}`}
        placeholder={config.notePlaceholder || 'Note'}
        value={stage.note || ''}
        onSave={v => save({ note: v })}
      />
    </div>
  )
}

// The Progress tab of the drawer: the path the application took, with a date on
// every stage, then your notes and contact for the job
export default function Progress({ job, onStageChange, onNotesChange }) {
  const locked = job.locked // guest: dates and stages only, nothing you wrote
  const history = job.history || []
  // Earlier stages are folded to one line; these are the ones opened to edit
  const [openIds, setOpenIds] = useState([])
  const todayInput = toDateInput(new Date().toISOString())

  function toggle(id) {
    setOpenIds(prev => (prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]))
  }

  return (
    <div className="progress">
      <h4>Timeline</h4>
      {history.length === 0 ? (
        <p className="none progress-empty">
          Not applied yet. Set the status to Submitted when you apply, and the timeline starts here.
        </p>
      ) : (
        <ol className="timeline">
          {history.map((stage, i) => {
            const previous = history[i - 1]
            const gap = previous ? gapLabel(daysBetween(dayOf(previous.at), dayOf(stage.at)), previous.status) : null
            const current = i === history.length - 1
            const open = current || openIds.includes(stage.id)
            const config = STAGE_DETAILS[stage.status] || {}
            const summary = [
              scheduledText(stage, config.scheduledKind) && `${config.scheduledLabel} ${scheduledText(stage, config.scheduledKind)}`,
              stage.done && config.doneLabel,
              !locked && stage.note,
            ].filter(Boolean).join(' · ')
            return (
              <li key={stage.id} className={`tl-item${current ? ' current' : ''}`}>
                <span className={`dot st-${ST_CLASS[stage.status]}`} />
                <div className="tl-main">
                  <div className="tl-head">
                    <span className="tl-status">{stage.status}</span>
                    {gap && <span className={`tl-gap${gap.warn ? ' warn' : ''}`}>{gap.text}</span>}
                  </div>
                  <div className="tl-date">
                    {locked ? (
                      formatDay(dayOf(stage.at))
                    ) : (
                      <SavedField
                        type="date"
                        aria-label={`Date of ${stage.status}`}
                        max={todayInput}
                        value={toDateInput(stage.at)}
                        onSave={v => (v ? onStageChange(job.trackingId, stage.id, { at: v }) : false)}
                      />
                    )}
                    {!current && !locked && (
                      <button className="textlink tl-toggle" aria-expanded={open} onClick={() => toggle(stage.id)}>
                        {open ? 'Hide details' : 'Details'}
                      </button>
                    )}
                  </div>
                  {open ? (
                    <StageDetails job={job} stage={stage} locked={locked} onStageChange={onStageChange} />
                  ) : (
                    summary && <div className="tl-summary">{summary}</div>
                  )}
                </div>
              </li>
            )
          })}
        </ol>
      )}

      {locked ? (
        <p className="none">Notes and contacts are hidden in guest mode.</p>
      ) : (
        <div className="progress-notes">
          <h4>Notes</h4>
          <SavedField
            as="textarea"
            rows={4}
            aria-label="Notes"
            placeholder="Anything worth remembering: questions to ask, how it went, next steps"
            value={job.notes || ''}
            onSave={v => onNotesChange(job.trackingId, { notes: v })}
          />
          <h4>Contact</h4>
          <SavedField
            aria-label="Contact"
            placeholder="e.g. Jane Tan, recruiter · jane@company.com"
            value={job.contact || ''}
            onSave={v => onNotesChange(job.trackingId, { contact: v })}
          />
          <p className="field-hint">Everything here saves when you click away from the field.</p>
        </div>
      )}
    </div>
  )
}
