import { useState } from 'react'
import Sidebar from './components/Sidebar'
import Dashboard from './components/Dashboard'
import Explore from './components/Explore'
import CVPage from './components/CVPage'
import Drawer from './components/Drawer'
import { initialJobs, initialExploreJobs } from './data'

// This is the ONLY place job data lives now. Every component below
// just receives it as props and calls a function to change it -
// nobody pokes the DOM directly anymore.
export default function App() {
  const [view, setView] = useState('dashboard')
  const [jobs, setJobs] = useState(initialJobs)
  const [exploreJobs, setExploreJobs] = useState(initialExploreJobs)
  const [drawerJob, setDrawerJob] = useState(null)

  // Replaces the old changeStatus(sel) that mutated jobs[i] directly
  // and manually swapped the <select>'s className. Here we just
  // describe the new state; React re-renders the pill automatically.
  function handleStatusChange(index, status) {
    setJobs(prev => prev.map((j, i) => (i === index ? { ...j, status } : j)))
  }

  // Replaces the old addJob(i, btn) that mutated the array AND
  // manually replaced the button's outerHTML.
  function handleAddToMyJobs(index) {
    setExploreJobs(prev => prev.map((j, i) => (i === index ? { ...j, added: true } : j)))
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
          />
        )}
        {view === 'explore' && (
          <Explore jobs={exploreJobs} onAdd={handleAddToMyJobs} />
        )}
        {view === 'cv' && <CVPage />}
      </main>

      <div className="overlay" onClick={() => setDrawerJob(null)} />
      <Drawer job={drawerJob} onClose={() => setDrawerJob(null)} />
    </div>
  )
}
