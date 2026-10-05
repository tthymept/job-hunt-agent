import { useState, useEffect } from 'react'
import Sidebar from './components/Sidebar'
import Dashboard from './components/Dashboard'
import Explore from './components/Explore'
import CVPage from './components/CVPage'
import Drawer from './components/Drawer'
import { initialJobs } from './data'

const EXPLORE_PAGE_SIZE = 20

export default function App() {
  const [view, setView] = useState('dashboard')
  const [jobs, setJobs] = useState(initialJobs)
  const [drawerJob, setDrawerJob] = useState(null)

  const [exploreJobs, setExploreJobs] = useState([])
  const [explorePage, setExplorePage] = useState(1)
  const [exploreTotal, setExploreTotal] = useState(0)
  const [exploreSort, setExploreSort] = useState('relevance')
  const [exploreFilters, setExploreFilters] = useState({ role: '', location: 'all', postedDate: 'all' })

  useEffect(() => {
    const params = new URLSearchParams({
      page: explorePage,
      page_size: EXPLORE_PAGE_SIZE,
      sort: exploreSort,
      role: exploreFilters.role,
      location: exploreFilters.location,
      posted_date: exploreFilters.postedDate,
    })
    fetch(`http://localhost:8000/api/explore-jobs?${params}`)
      .then(res => res.json())
      .then(data => {
        setExploreJobs(data.jobs)
        setExploreTotal(data.total)
      })
      .catch(err => console.error('Failed to load jobs:', err))
  }, [explorePage, exploreSort, exploreFilters])

  function handleStatusChange(index, status) {
    setJobs(prev => prev.map((j, i) => (i === index ? { ...j, status } : j)))
  }

  function handleAddToMyJobs(index) {
    setExploreJobs(prev => prev.map((j, i) => (i === index ? { ...j, added: true } : j)))
  }

  function handleSortChange(newSort) {
    setExploreSort(newSort)
    setExplorePage(1)
  }

  function handleApplyFilters(newFilters) {
    setExploreFilters(newFilters)
    setExplorePage(1)
  }

  return (
    <div className={`app${drawerJob ? ' drawer-open' : ''}`}>
      <Sidebar view={view} setView={setView} />

      <main className="main">
        {view === 'dashboard' && (
          <Dashboard jobs={jobs} onStatusChange={handleStatusChange} onOpenDrawer={setDrawerJob} />
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
      <Drawer job={drawerJob} onClose={() => setDrawerJob(null)} />
    </div>
  )
}