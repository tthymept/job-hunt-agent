import { dayOf, daysBetween, parseDay, shortDay, timeOf, today } from './dates'

// What each stage can hold besides the day it happened. scheduledKind picks the
// field: 'date' (OA due date, offer reply-by) or 'datetime' (an interview).
const INTERVIEW = {
  scheduledLabel: 'When',
  scheduledKind: 'datetime',
  doneLabel: 'Interview done',
  notePlaceholder: 'e.g. Who you met, what they asked',
}

export const STAGE_DETAILS = {
  'Submitted': { notePlaceholder: 'e.g. Applied through a referral' },
  'Online Assignment': {
    scheduledLabel: 'Due',
    scheduledKind: 'date',
    doneLabel: 'Assessment submitted',
    notePlaceholder: 'e.g. HackerRank, 90 minutes',
  },
  'Interview Round 1': INTERVIEW,
  'Interview Round 2': INTERVIEW,
  'Offered': { scheduledLabel: 'Reply by', scheduledKind: 'date', notePlaceholder: 'e.g. Pay, start date' },
  'Rejected': { notePlaceholder: 'e.g. The reason they gave' },
}

// No reply after this many days: the note under the status turns amber, as a nudge to follow up
export const FOLLOW_UP_DAYS = 21

function relativeDay(date) {
  const days = daysBetween(today(), date)
  if (days === 0) return 'today'
  if (days === 1) return 'tomorrow'
  return shortDay(date)
}

const capitalise = text => text.charAt(0).toUpperCase() + text.slice(1)

// The history row for the stage the job is at now, if any
function currentStage(job) {
  return (job.history || []).find(e => e.status === job.status) || null
}

// How many days the job has been waiting on the company: since applying (at
// Submitted) or since finishing an OA or interview. null when you aren't waiting.
export function waitingDays(job) {
  const stage = currentStage(job)
  if (!stage) return null
  if (job.status === 'Submitted') return daysBetween(dayOf(stage.at), today())
  if (stage.done && stage.doneAt) return daysBetween(dayOf(stage.doneAt), today())
  return null
}

// The short line under a job's status in the table, or null when there is
// nothing worth saying: { text, tone ('' | 'warn' | 'muted'), title }
export function statusNote(job) {
  const stage = currentStage(job)
  if (!stage) return null

  if (job.status === 'Submitted') {
    const days = waitingDays(job)
    if (days <= 0) return { text: 'Applied today', tone: '' }
    return {
      text: `Waiting ${days}d`,
      tone: days >= FOLLOW_UP_DAYS ? 'warn' : '',
      title: days >= FOLLOW_UP_DAYS ? `No reply ${days} days after applying. Worth a follow-up?` : `Applied ${days} days ago`,
    }
  }

  const details = STAGE_DETAILS[job.status]
  if (job.status === 'Online Assignment' || job.status.startsWith('Interview')) {
    if (stage.done) {
      const days = waitingDays(job) ?? 0
      if (days <= 0) return { text: 'Done', tone: '' }
      return {
        text: `Done · waiting ${days}d`,
        tone: days >= FOLLOW_UP_DAYS ? 'warn' : '',
        title: `No news ${days} days after finishing this stage`,
      }
    }
    if (!stage.scheduledAt) {
      return { text: details.scheduledKind === 'date' ? 'Add due date' : 'Add interview date', tone: 'muted' }
    }
    const when = new Date(stage.scheduledAt)
    const days = daysBetween(today(), dayOf(stage.scheduledAt))
    if (job.status === 'Online Assignment') {
      if (days < 0) return { text: `Overdue · was due ${shortDay(when)}`, tone: 'warn' }
      return { text: `Due ${relativeDay(when)}`, tone: days <= 2 ? 'warn' : '' }
    }
    if (days < 0) return { text: `Was ${shortDay(when)} · mark it done?`, tone: 'muted' }
    return { text: `${capitalise(relativeDay(when))}, ${timeOf(when)}`, tone: days <= 1 ? 'warn' : '' }
  }

  if (job.status === 'Offered' && stage.scheduledAt) {
    const when = new Date(stage.scheduledAt)
    const days = daysBetween(today(), dayOf(stage.scheduledAt))
    if (days < 0) return { text: `Reply was due ${shortDay(when)}`, tone: 'warn' }
    return { text: `Reply by ${relativeDay(when)}`, tone: days <= 3 ? 'warn' : '' }
  }
  return null
}

// ---------- Calendar and Upcoming ----------

// The kinds of dated item, in the order the calendar legend lists them.
// `tab` is the drawer tab an item opens on.
export const AGENDA_KINDS = {
  deadline: { label: 'Apply by', tab: 'details' },
  oa: { label: 'OA due', tab: 'progress' },
  interview: { label: 'Interview', tab: 'progress' },
  offer: { label: 'Offer reply', tab: 'progress' },
}

// Everything with a date that still needs doing: the application deadline
// while a job is unapplied, then the current stage's OA due date, interview or
// offer reply-by (until it is ticked done). Sorted by date, then time.
// [{ key, job, kind, date (local midnight), time ("14:30" or null) }]
export function agendaItems(jobs) {
  const items = []
  for (const job of jobs) {
    if (job.status === 'Saved / Not Applied') {
      const date = parseDay(job.dl)
      if (date) items.push({ key: `${job.trackingId}-deadline`, job, kind: 'deadline', date, time: null, sort: date.getTime() })
      continue
    }
    const stage = currentStage(job)
    if (!stage || !stage.scheduledAt || stage.done) continue
    const kind = job.status === 'Online Assignment' ? 'oa'
      : job.status.startsWith('Interview') ? 'interview'
      : job.status === 'Offered' ? 'offer'
      : null
    if (!kind) continue
    const when = new Date(stage.scheduledAt)
    items.push({
      key: `${job.trackingId}-${kind}`,
      job,
      kind,
      date: dayOf(stage.scheduledAt),
      time: kind === 'interview' ? timeOf(when) : null,
      sort: when.getTime(),
    })
  }
  return items.sort((a, b) => a.date - b.date || a.sort - b.sort)
}

// ---------- Stats ----------

// Fewer applications than this and the percentages would mislead, so the strip stays hidden
export const MIN_APPLIED_FOR_STATS = 3

const REPLY_STAGES = ['Online Assignment', 'Interview Round 1', 'Interview Round 2', 'Offered', 'Rejected']
const INTERVIEW_STAGES = ['Interview Round 1', 'Interview Round 2', 'Offered']

function median(numbers) {
  if (numbers.length === 0) return null
  const sorted = [...numbers].sort((a, b) => a - b)
  const mid = Math.floor(sorted.length / 2)
  return sorted.length % 2 ? sorted[mid] : Math.round((sorted[mid - 1] + sorted[mid]) / 2)
}

// What the history says about how applications are going:
// { applied, replied, responseRate, medianReplyDays, interviewed, interviewRate, waitingLong }
// "Replied" is any answer after applying, a rejection included. Reply time runs
// from the Submitted date to the first stage after it.
export function applicationStats(jobs) {
  const applied = jobs.filter(j => (j.history || []).length > 0)
  const replied = applied.filter(j => j.history.some(e => REPLY_STAGES.includes(e.status)))
  const replyDays = replied
    .map(j => {
      const submitted = j.history.find(e => e.status === 'Submitted')
      const reply = j.history.find(e => REPLY_STAGES.includes(e.status))
      return submitted ? daysBetween(dayOf(submitted.at), dayOf(reply.at)) : null
    })
    .filter(days => days != null && days >= 0)
  const interviewed = applied.filter(j => j.history.some(e => INTERVIEW_STAGES.includes(e.status)))
  const rate = count => (applied.length ? Math.round((count / applied.length) * 100) : 0)
  return {
    applied: applied.length,
    replied: replied.length,
    responseRate: rate(replied.length),
    medianReplyDays: median(replyDays),
    interviewed: interviewed.length,
    interviewRate: rate(interviewed.length),
    waitingLong: jobs.filter(j => (waitingDays(j) ?? 0) >= FOLLOW_UP_DAYS).length,
  }
}
