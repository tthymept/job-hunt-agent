import { useState, useEffect } from 'react'
import Sidebar from './components/Sidebar'
import Dashboard from './components/Dashboard'
import Explore from './components/Explore'
import CVPage from './components/CVPage'
import Drawer from './components/Drawer'
import JobFormModal from './components/JobFormModal'

const EXPLORE_PAGE_SIZE = 20
const API = 'http://localhost:8000'

export default function App() {
  const [view, setView] = useState('dashboard')
  const [jobs, setJobs] = useState([])
  const [drawerJob, setDrawerJob] = useState(null)
  const [generatingId, setGeneratingId] = useState(null)
  const [jobModal, setJobModal] = useState(null) // null | { mode: 'add' } | { mode: 'edit', job }

  const [exploreJobs, setExploreJobs] = useState([])
  const [explorePage, setExplorePage] = useState(1)
  const [exploreTotal, setExploreTotal] = useState(0)
  const [exploreSort, setExploreSort] = useState('relevance')
  const [exploreFilters, setExploreFilters] = useState({ role: '', location: 'all', postedDate: 'all' })

  function loadTracker() {
    return fetch(`${API}/api/tracker`)
      .then(res => res.json())
      .then(data => {
        setJobs(data)
        return data
      })
      .catch(err => {
        console.error('Failed to load tracker:', err)
        return []
      })
  }

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
    fetch(`${API}/api/explore-jobs?${params}`)
      .then(res => res.json())
      .then(data => {
        setExploreJobs(data.jobs)
        setExploreTotal(data.total)
      })
      .catch(err => console.error('Failed to load jobs:', err))
  }, [explorePage, exploreSort, exploreFilters])

  function handleStatusChange(trackingId, status) {
    if (status === 'Untracked') {
      setJobs(prev => prev.filter(j => j.trackingId !== trackingId))
    } else {
      setJobs(prev => prev.map(j => (j.trackingId === trackingId ? { ...j, status } : j)))
    }
    fetch(`${API}/api/tracker/${trackingId}/status`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status }),
    }).catch(err => console.error('Failed to update status:', err))
  }

  function handleAddToMyJobs(index) {
    const job = exploreJobs[index]
    setExploreJobs(prev => prev.map((j, i) => (i === index ? { ...j, trackState: 'added' } : j)))
    fetch(`${API}/api/tracker`, {
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
    setGeneratingId(trackingId)
    fetch(`${API}/api/tracker/${trackingId}/generate-bullets`, { method: 'POST' })
      .then(res => res.json())
      .then(data => {
        setJobs(prev => prev.map(j => (j.trackingId === trackingId ? { ...j, bullets: data.bullets } : j)))
        setDrawerJob(prev => (prev && prev.trackingId === trackingId ? { ...prev, bullets: data.bullets } : prev))
      })
      .catch(err => console.error('Failed to generate bullets:', err))
      .finally(() => setGeneratingId(null))
  }

  function handleUploadCv(trackingId, file) {
    const formData = new FormData()
    formData.append('file', file)
    fetch(`${API}/api/tracker/${trackingId}/upload`, { method: 'POST', body: formData })
      .then(() => loadTracker())
      .catch(err => console.error('Failed to upload CV:', err))
  }

  return (
    <div className={`app${drawerJob ? ' drawer-open' : ''}`}>
      <Sidebar view={view} setView={setView} />

      <main className="main">
        {view === 'dashboard' && (
          <Dashboard
            jobs={jobs}
            onStatusChange={handleStatusChange}
            onOpenDrawer={setDrawerJob}
            onUploadCv={handleUploadCv}
            onOpenManualModal={() => setJobModal({ mode: 'add' })}
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
        initial={jobModal?.job?.edit}
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
    </div>
  )
}