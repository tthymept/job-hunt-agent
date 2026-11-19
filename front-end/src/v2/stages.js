import { dayOf, daysBetween, shortDay, timeOf, today } from './dates'

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

// The short line under a job's status in the table, or null when there is
// nothing worth saying: { text, tone ('' | 'warn' | 'muted'), title }
export function statusNote(job) {
  const history = job.history || []
  const stage = history.find(e => e.status === job.status)
  if (!stage) return null

  if (job.status === 'Submitted') {
    const days = daysBetween(dayOf(stage.at), today())
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
      const days = stage.doneAt ? daysBetween(dayOf(stage.doneAt), today()) : 0
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
