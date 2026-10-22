import { useState, useEffect } from 'react'
import Sidebar from './components/Sidebar'
import Dashboard from './components/Dashboard'
import Explore from './components/Explore'
import CVPage from './components/CVPage'
import Drawer from './components/Drawer'
import JobFormModal from './components/JobFormModal'
import AccessKeyGate from './components/AccessKeyGate'
import LogoutModal from './components/LogoutModal'
import { apiFetch, readJson, isGuest, blockedForGuest } from './api'

const EXPLORE_PAGE_SIZE = 20

export default function App() {
  const [view, setView] = useState('dashboard')
  const [me, setMe] = useState(null)
  const [locked, setLocked] = useState(false) // true when the server rejected the access key
  const [guestBlocked, setGuestBlocked] = useState(false) // a guest tried to change something
  const [logoutOpen, setLogoutOpen] = useState(false)
  const [jobs, setJobs] = useState([])
  const [hiddenJobCount, setHiddenJobCount] = useState(0) // tracked jobs a guest can't see
  const [drawerJob, setDrawerJob] = useState(null)
  const [generatingId, setGeneratingId] = useState(null)
  const [jobModal, setJobModal] = useState(null) // null | { mode: 'add' } | { mode: 'edit', job }

  const [exploreJobs, setExploreJobs] = useState([])
  const [explorePage, setExplorePage] = useState(1)
  const [exploreTotal, setExploreTotal] = useState(0)
  const [exploreSort, setExploreSort] = useState('relevance')
  const [exploreFilters, setExploreFilters] = useState({ role: '', location: 'all', postedDate: 'all' })

  function loadTracker() {
    return apiFetch(`/api/tracker`)
      .then(async res => {
        const data = await readJson(res)
        const total = Number(res.headers.get('X-Total-Count')) || data.length
        setJobs(data)
        setHiddenJobCount(Math.max(0, total - data.length))
        return data
      })
      .catch(err => {
        console.error('Failed to load tracker:', err)
        return []
      })
  }

  // apiFetch fires this event on any 401 reply
  useEffect(() => {
    const lock = () => setLocked(true)
    const block = () => setGuestBlocked(true)
    window.addEventListener('access-key-needed', lock)
    window.addEventListener('guest-blocked', block)
    return () => {
      window.removeEventListener('access-key-needed', lock)
      window.removeEventListener('guest-blocked', block)
    }
  }, [])

  useEffect(() => {
    apiFetch(`/api/me`)
      .then(readJson)
      .then(setMe)
      .catch(err => console.error('Failed to load user:', err))
  }, [])

  // Refetches whenever Dashboard becomes the active tab - simplest way
  // to show jobs added from Explore without more complex cross-page sync.
  useEffect(() => {
    if (view === 'dashboard') loadTracker()
  }, [view])

  useEffect(() => {
    const params = new URLSearchParams({
      page: explorePage,
      page_size: EXPLORE_PAGE_SIZE,
      sort: exploreSort,
      role: exploreFilters.role,
      location: exploreFilters.location,
      posted_date: exploreFilters.postedDate,
    })
    apiFetch(`/api/explore-jobs?${params}`)
      .then(readJson)
      .then(data => {
        setExploreJobs(data.jobs)
        setExploreTotal(data.total)
      })
      .catch(err => console.error('Failed to load jobs:', err))
  }, [explorePage, exploreSort, exploreFilters])

  function handleStatusChange(trackingId, status) {
    if (blockedForGuest()) return
    if (status === 'Untracked') {
      setJobs(prev => prev.filter(j => j.trackingId !== trackingId))
    } else {
      setJobs(prev => prev.map(j => (j.trackingId === trackingId ? { ...j, status } : j)))
    }
    apiFetch(`/api/tracker/${trackingId}/status`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status }),
    }).catch(err => console.error('Failed to update status:', err))
  }

  function handleAddToMyJobs(index) {
    if (blockedForGuest()) return
    const job = exploreJobs[index]
    setExploreJobs(prev => prev.map((j, i) => (i === index ? { ...j, trackState: 'added' } : j)))
    apiFetch(`/api/tracker`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_id: job.jobId }),
    }).catch(err => console.error('Failed to add job:', err))
  }

  function handleSortChange(newSort) {
    setExploreSort(newSort)
    setExplorePage(1)
  }

  function handleApplyFilters(newFilters) {
    setExploreFilters(newFilters)
    setExplorePage(1)
  }
  function handleGenerateBullets(trackingId) {
    if (blockedForGuest()) return
    setGeneratingId(trackingId)
    apiFetch(`/api/tracker/${trackingId}/generate-bullets`, { method: 'POST' })
      .then(async res => {
        const data = await res.json()
        if (!res.ok) throw new Error(data.detail || 'Failed to generate suggestions')
        return data
      })
      .then(data => {
        setJobs(prev => prev.map(j => (j.trackingId === trackingId ? { ...j, bullets: data.bullets } : j)))
        setDrawerJob(prev => (prev && prev.trackingId === trackingId ? { ...prev, bullets: data.bullets } : prev))
      })
      .catch(err => {
        console.error('Failed to generate bullets:', err)
        alert(err.message)
      })
      .finally(() => setGeneratingId(null))
  }

  function handleUploadCv(trackingId, file) {
    const formData = new FormData()
    formData.append('file', file)
    apiFetch(`/api/tracker/${trackingId}/upload`, { method: 'POST', body: formData })
      .then(() => loadTracker())
      .catch(err => console.error('Failed to upload CV:', err))
  }

  function handleDeleteCv(trackingId) {
    setJobs(prev => prev.map(j => (j.trackingId === trackingId ? { ...j, myUploadUrl: null } : j)))
    apiFetch(`/api/tracker/${trackingId}/upload`, { method: 'DELETE' })
      .catch(err => {
        console.error('Failed to delete CV:', err)
        loadTracker()
      })
  }

  // Returns { ok, message } so the Dashboard can show feedback under the URL bar
  async function handleLoadFromUrl(url) {
    if (blockedForGuest()) return { ok: false }
    try {
      const res = await apiFetch(`/api/jobs/from-url`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url }),
      })
      if (res.status === 422) {
        const data = await res.json()
        // Couldn't read the page: open the manual form with the link filled in
        setJobModal({ mode: 'add', prefill: { apply_link: url } })
        return { ok: false, message: `${data.detail} I opened the form with your link filled in.` }
      }
      if (!res.ok) throw new Error('Request failed')
      await loadTracker()
      return { ok: true }
    } catch {
      return { ok: false, message: 'Something went wrong. Check that the backend is running.' }
    }
  }

  if (locked) return <AccessKeyGate />

  return (
    <div className={`app${drawerJob ? ' drawer-open' : ''}`}>
      <Sidebar view={view} setView={setView} me={me} guest={isGuest()} onUnlock={() => setGuestBlocked(true)} onLogout={() => setLogoutOpen(true)} />

      <main className="main">
        {view === 'dashboard' && (
          <Dashboard
            jobs={jobs}
            hiddenJobCount={hiddenJobCount}
            onUnlock={() => setGuestBlocked(true)}
            onStatusChange={handleStatusChange}
            onOpenDrawer={setDrawerJob}
            onUploadCv={handleUploadCv}
            onDeleteCv={handleDeleteCv}
            onOpenManualModal={() => setJobModal({ mode: 'add' })}
            onLoadFromUrl={handleLoadFromUrl}
          />
        )}
        {view === 'explore' && (
          <Explore
            jobs={exploreJobs}
            onAdd={handleAddToMyJobs}
            page={explorePage}
            pageSize={EXPLORE_PAGE_SIZE}
            total={exploreTotal}
            onPageChange={setExplorePage}
            sort={exploreSort}
            onSortChange={handleSortChange}
            filters={exploreFilters}
            onApplyFilters={handleApplyFilters}
            onOpenDrawer={setDrawerJob}
          />
        )}
        {view === 'cv' && <CVPage />}
      </main>

      <div className="overlay" onClick={() => setDrawerJob(null)} />
      <Drawer
        job={drawerJob}
        onEdit={job => setJobModal({ mode: 'edit', job })}
        onClose={() => setDrawerJob(null)}
        onGenerate={handleGenerateBullets}
        generating={drawerJob && generatingId === drawerJob.trackingId}
      />

      <JobFormModal
        open={jobModal !== null}
        mode={jobModal?.mode}
        initial={jobModal?.job?.edit || jobModal?.prefill}
        trackingId={jobModal?.job?.trackingId}
        onClose={() => setJobModal(null)}
        onSaved={() => {
          setJobModal(null)
          // Reload, then refresh the open drawer so it shows the edited values
          loadTracker().then(data =>
            setDrawerJob(prev => (prev ? data.find(j => j.trackingId === prev.trackingId) || prev : prev))
          )
        }}
      />

      {guestBlocked && <AccessKeyGate blocked onClose={() => setGuestBlocked(false)} />}
      {logoutOpen && <LogoutModal guest={isGuest()} onClose={() => setLogoutOpen(false)} />}
    </div>
  )
}