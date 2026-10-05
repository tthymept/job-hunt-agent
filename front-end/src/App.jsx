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

  // Refetches whenever explorePage changes - clicking a page number
  // just updates this one piece of state, and this effect does the rest.
  useEffect(() => {
    fetch(`http://localhost:8000/api/explore-jobs?page=${explorePage}&page_size=${EXPLORE_PAGE_SIZE}`)
      .then(res => res.json())
      .then(data => {
        setExploreJobs(data.jobs)
        setExploreTotal(data.total)
      })
      .catch(err => console.error('Failed to load jobs:', err))
  }, [explorePage])

  function handleStatusChange(index, status) {
    setJobs(prev => prev.map((j, i) => (i === index ? { ...j, status } : j)))
  }

  function handleAddToMyJobs(index) {
    setExploreJobs(prev => prev.map((j, i) => (i === index ? { ...j, added: true } : j)))
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
          />
        )}
        {view === 'cv' && <CVPage />}
      </main>

      <div className="overlay" onClick={() => setDrawerJob(null)} />
      <Drawer job={drawerJob} onClose={() => setDrawerJob(null)} />
    </div>
  )
}