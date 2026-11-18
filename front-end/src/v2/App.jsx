import { useState, useEffect } from 'react'
import Sidebar from './Sidebar'
import Dashboard from './Dashboard'
import Explore from './Explore'
import CVPage from './CVPage'
import Drawer from './Drawer'
import TabPickerModal from './TabPickerModal'
import JobFormModal from '../components/JobFormModal'
import AccessKeyGate from './AccessKeyGate'
import LogoutModal from '../components/LogoutModal'
import { apiFetch, readJson, readResult, isGuest, blockedForGuest, JSON_HEADERS } from '../api'

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
  // null | { mode: 'add', tabId, prefill } | { mode: 'edit', job }
  const [jobModal, setJobModal] = useState(null)

  // Dashboard tabs: [{ id, name, enabled, isDefault }]. Every tracked job has a tabId.
  const [tabs, setTabs] = useState([])
  const [activeTabId, setActiveTabId] = useState(null)
  const [tabError, setTabError] = useState(null)
  // While the "which tab?" popup is open: { resolve }, called with the chosen tab id or undefined
  const [tabPicker, setTabPicker] = useState(null)

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

  // Stores a fresh tab list. If the tab being viewed is gone (or none is chosen
  // yet), the default tab becomes the one on screen.
  function applyTabs(list) {
    setTabs(list)
    setActiveTabId(prev => (list.some(t => t.id === prev) ? prev : (list.find(t => t.isDefault) || list[0])?.id ?? null))
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
    apiFetch(`/api/tabs`)
      .then(readJson)
      .then(applyTabs)
      .catch(err => console.error('Failed to load tabs:', err))
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

  // ---------- Tabs ----------

  // Sends one tab change. Every tab endpoint answers with the full tab list.
  // Returns that list, or null (with a message under the tab bar) when it failed.
  async function tabRequest(method, path, body) {
    if (blockedForGuest()) return null
    setTabError(null)
    try {
      const res = await apiFetch(path, {
        method,
        headers: JSON_HEADERS,
        body: body ? JSON.stringify(body) : undefined,
      })
      // A server crash answers with plain text, not JSON
      const data = await res.json().catch(() => null)
      if (!res.ok || !data) throw new Error(data?.detail || 'That change could not be saved. Check that the backend is running.')
      applyTabs(data)
      return data
    } catch (err) {
      setTabError(err.message)
      return null
    }
  }

  const tabActions = {
    async create(name) {
      const list = await tabRequest('POST', `/api/tabs`, { name })
      // The new tab has the highest id: show it straight away
      if (list) setActiveTabId(Math.max(...list.map(t => t.id)))
      return Boolean(list)
    },
    async rename(id, name) {
      return Boolean(await tabRequest('PATCH', `/api/tabs/${id}`, { name }))
    },
    setDefault(id) {
      return tabRequest('PATCH', `/api/tabs/${id}`, { is_default: true })
    },
    setEnabled(id, enabled) {
      return tabRequest('PATCH', `/api/tabs/${id}`, { enabled })
    },
    remove(id) {
      return tabRequest('DELETE', `/api/tabs/${id}`)
    },
  }

  // Works out which tab a new job goes into. With one tab accepting jobs there
  // is nothing to ask. With more, the "which tab?" popup opens.
  // Resolves to { tabId }, or null when the popup was cancelled.
  function chooseTab() {
    const open = tabs.filter(t => t.enabled)
    // tabId null (tabs not loaded yet) lets the server pick the default tab
    if (open.length <= 1) return Promise.resolve({ tabId: open[0]?.id ?? null })
    return new Promise(resolve => setTabPicker({ resolve }))
  }

  function closeTabPicker(tabId) {
    tabPicker.resolve(tabId === undefined ? null : { tabId })
    setTabPicker(null)
  }

  function handleMoveJob(trackingId, tabId) {
    if (blockedForGuest()) return
    apiFetch(`/api/tracker/${trackingId}/tab`, {
      method: 'PATCH',
      headers: JSON_HEADERS,
      body: JSON.stringify({ tab_id: tabId }),
    })
      .then(async res => {
        const data = await res.json()
        if (!res.ok) throw new Error(data.detail || 'The job could not be moved.')
        setJobs(prev => prev.map(j => (j.trackingId === trackingId ? { ...j, tabId: data.tabId } : j)))
        setDrawerJob(prev => (prev && prev.trackingId === trackingId ? { ...prev, tabId: data.tabId } : prev))
      })
      .catch(err => {
        console.error('Failed to move job:', err)
        alert(err.message)
      })
  }

  // ---------- Jobs ----------

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
    })
      .then(readJson)
      .then(data => {
        setJobs(prev => prev.map(j => (j.trackingId === trackingId ? { ...j, submittedAt: data.submittedAt } : j)))
      })
      .catch(err => {
        console.error('Failed to update status:', err)
        loadTracker()
      })
  }

  async function handleAddToMyJobs(index) {
    if (blockedForGuest()) return
    const job = exploreJobs[index]
    const choice = await chooseTab()
    if (!choice) return
    const setTrackState = trackState =>
      setExploreJobs(prev => prev.map(j => (j.jobId === job.jobId ? { ...j, trackState } : j)))
    setTrackState('added')
    apiFetch(`/api/tracker`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_id: job.jobId, tab_id: choice.tabId }),
    })
      .then(res => readResult(res, 'The job could not be added.'))
      .catch(err => {
        console.error('Failed to add job:', err)
        setTrackState(job.trackState) // back to Add, so it can be tried again
        alert(err.message)
      })
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

  // kind is 'cv' or 'cover_letter': the two files a tracked job can hold
  function handleUploadCv(trackingId, file, kind = 'cv') {
    const formData = new FormData()
    formData.append('file', file)
    apiFetch(`/api/tracker/${trackingId}/upload?kind=${kind}`, { method: 'POST', body: formData })
      .then(res => readResult(res, 'The file could not be uploaded.'))
      .then(() => loadTracker())
      .catch(err => {
        console.error('Failed to upload file:', err)
        alert(err.message)
      })
  }

  function handleDeleteCv(trackingId, kind = 'cv') {
    const field = kind === 'cover_letter' ? 'hasCoverLetter' : 'hasMyUpload'
    setJobs(prev => prev.map(j => (j.trackingId === trackingId ? { ...j, [field]: false } : j)))
    apiFetch(`/api/tracker/${trackingId}/upload?kind=${kind}`, { method: 'DELETE' })
      .then(res => readResult(res, 'The file could not be deleted.'))
      .catch(err => {
        console.error('Failed to delete file:', err)
        alert(err.message)
        loadTracker() // the file is still there: show it again
      })
  }

  async function handleOpenManualModal() {
    if (blockedForGuest()) return
    const choice = await chooseTab()
    if (choice) setJobModal({ mode: 'add', tabId: choice.tabId })
  }

  // Returns { ok, message } so the Dashboard can show feedback under the URL bar
  async function handleLoadFromUrl(url) {
    if (blockedForGuest()) return { ok: false }
    const choice = await chooseTab()
    if (!choice) return { ok: false }
    try {
      const res = await apiFetch(`/api/jobs/from-url`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, tab_id: choice.tabId }),
      })
      if (res.status === 422) {
        const data = await res.json()
        // Couldn't read the page: open the manual form with the link filled in
        setJobModal({ mode: 'add', tabId: choice.tabId, prefill: { apply_link: url } })
        return { ok: false, message: `${data.detail} I opened the form with your link filled in.` }
      }
      if (res.status === 400) {
        const data = await res.json()
        return { ok: false, message: data.detail }
      }
      if (!res.ok) throw new Error('Request failed')
      await loadTracker()
      if (choice.tabId) setActiveTabId(choice.tabId) // show the tab the job went into
      return { ok: true }
    } catch {
      return { ok: false, message: 'Something went wrong. Check that the backend is running.' }
    }
  }

  if (locked) return <AccessKeyGate />

  const activeTab = tabs.find(t => t.id === activeTabId) || null
  // Until the tabs have loaded there is nothing to filter by, so show every job
  const tabJobs = activeTab ? jobs.filter(j => j.tabId === activeTab.id) : jobs
  const tabCounts = {}
  for (const j of jobs) tabCounts[j.tabId] = (tabCounts[j.tabId] || 0) + 1
  const openTabs = tabs.filter(t => t.enabled)

  return (
    <div className={`app${drawerJob ? ' drawer-open' : ''}`}>
      <Sidebar view={view} setView={setView} me={me} guest={isGuest()} onUnlock={() => setGuestBlocked(true)} onLogout={() => setLogoutOpen(true)} />

      <main className="main">
        {view === 'dashboard' && (
          <Dashboard
            jobs={tabJobs}
            hiddenJobCount={hiddenJobCount}
            tabs={tabs}
            activeTab={activeTab}
            tabCounts={tabCounts}
            onSelectTab={setActiveTabId}
            tabActions={tabActions}
            tabError={tabError}
            onDismissTabError={() => setTabError(null)}
            onUnlock={() => setGuestBlocked(true)}
            onStatusChange={handleStatusChange}
            onOpenDrawer={setDrawerJob}
            onUploadCv={handleUploadCv}
            onDeleteCv={handleDeleteCv}
            onOpenManualModal={handleOpenManualModal}
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
        tabs={tabs}
        onMoveJob={handleMoveJob}
        onEdit={job => !blockedForGuest() && setJobModal({ mode: 'edit', job })}
        onClose={() => setDrawerJob(null)}
        onGenerate={handleGenerateBullets}
        generating={drawerJob && generatingId === drawerJob.trackingId}
      />

      <JobFormModal
        open={jobModal !== null}
        mode={jobModal?.mode}
        initial={jobModal?.job?.edit || jobModal?.prefill}
        trackingId={jobModal?.job?.trackingId}
        tabId={jobModal?.tabId}
        onClose={() => setJobModal(null)}
        onSaved={() => {
          const addedTo = jobModal?.mode === 'add' ? jobModal.tabId : null
          setJobModal(null)
          if (addedTo) setActiveTabId(addedTo) // show the tab the job went into
          // Reload, then refresh the open drawer so it shows the edited values
          loadTracker().then(data =>
            setDrawerJob(prev => (prev ? data.find(j => j.trackingId === prev.trackingId) || prev : prev))
          )
        }}
      />

      {tabPicker && (
        <TabPickerModal
          tabs={openTabs}
          initialId={(openTabs.find(t => t.isDefault) || openTabs[0]).id}
          onPick={closeTabPicker}
          onCancel={() => closeTabPicker(undefined)}
        />
      )}
      {guestBlocked && <AccessKeyGate blocked onClose={() => setGuestBlocked(false)} />}
      {logoutOpen && <LogoutModal guest={isGuest()} onClose={() => setLogoutOpen(false)} />}
    </div>
  )
}
