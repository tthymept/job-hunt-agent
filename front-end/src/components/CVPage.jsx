import { useState, useEffect } from 'react'

const API = 'http://localhost:8000'

function formatDate(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' })
}

export default function CVPage() {
  // null while loading, { exists: false } when no CV, otherwise the saved CV
  const [cv, setCv] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [message, setMessage] = useState(null)

  // Load the saved CV from the backend every time this page opens,
  // so it is still there after a reload or switching tabs
  useEffect(() => {
    fetch(`${API}/api/cv`)
      .then(res => res.json())
      .then(setCv)
      .catch(() => setMessage('Could not load your CV. Is the backend running?'))
  }, [])

  async function uploadFile(file) {
    if (!file) return
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      setMessage('Please upload a PDF file.')
      return
    }
    if (file.size > 10 * 1024 * 1024) {
      setMessage('That file is over 10 MB.')
      return
    }
    setUploading(true)
    setMessage(null)
    const formData = new FormData()
    formData.append('file', file)
    try {
      const res = await fetch(`${API}/api/cv`, { method: 'POST', body: formData })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Upload failed')
      setCv(data)
      if (data.warning) setMessage(data.warning)
    } catch (err) {
      setMessage(err.message)
    } finally {
      setUploading(false)
    }
  }

  function handleFileChange(e) {
    uploadFile(e.target.files[0])
    e.target.value = '' // lets the same file be picked again later
  }

  function handleDrop(e) {
    e.preventDefault()
    uploadFile(e.dataTransfer.files[0])
  }

  function downloadCv() {
    if (cv?.downloadUrl) window.open(cv.downloadUrl, '_blank')
  }

  const hasCv = cv?.exists
  const sections = cv?.structure?.sections || []
  const fileMeta = [
    cv?.updatedAt && `Updated ${formatDate(cv.updatedAt)}`,
    cv?.sizeKb && `${cv.sizeKb} KB`,
  ].filter(Boolean).join(' · ')

  return (
    <section>
      <div className="pagehead">
        <div>
          <h1>My CV</h1>
          <p>Upload one master CV to preview, download, and tailor for applications.</p>
        </div>
        <button className="btn primary" disabled={!hasCv} onClick={downloadCv}>⬇ Download</button>
      </div>

      <label
        className="dropzone"
        htmlFor="fileInput"
        style={{ display: 'block' }}
        onDragOver={e => e.preventDefault()}
        onDrop={handleDrop}
      >
        <div className="ic">⬆</div>
        <div>
          <strong>{uploading ? 'Uploading and reading your CV…' : 'Drop your CV here or browse files'}</strong>
        </div>
        <div style={{ fontSize: 12, marginTop: 4 }}>PDF · Maximum 10 MB</div>
        <input
          id="fileInput"
          type="file"
          style={{ display: 'none' }}
          accept=".pdf"
          disabled={uploading}
          onChange={handleFileChange}
        />
      </label>

      {message && <div style={{ color: '#991b1b', fontSize: 13, margin: '12px 0' }}>{message}</div>}

      {hasCv && (
        <div className="fileinfo">
          <div>
            📄 <span className="name">{cv.fileName}</span><br />
            {fileMeta && <span className="sub">{fileMeta}</span>}
          </div>
          <div className="actions">
            <label className="btn sm" htmlFor="fileInput" style={{ cursor: 'pointer' }}>↻ Replace</label>
            <button className="btn sm" onClick={downloadCv}>⬇ Download</button>
          </div>
        </div>
      )}

      {cv && !hasCv && (
        <div className="card" style={{ padding: 30, textAlign: 'center', color: 'var(--sub)', fontSize: 13.5 }}>
          No CV uploaded yet. Upload a PDF above and a preview will appear here.
        </div>
      )}

      {hasCv && sections.length === 0 && (
        <div className="card" style={{ padding: 30, textAlign: 'center', color: 'var(--sub)', fontSize: 13.5 }}>
          Your CV is saved, but its text hasn't been read yet. Replace it to try again.
        </div>
      )}

      {hasCv && sections.length > 0 && (
        <>
          <p style={{ color: 'var(--sub)', fontSize: 12.5, margin: '0 0 10px' }}>
            Text read from your CV. This is what the tailor agent works from.
          </p>
          <div className="card" style={{ background: 'var(--row-hover)', padding: 30 }}>
            <div className="resume">
              {sections.map((s, i) => (
                <div key={i}>
                  <h3>{s.title}</h3>
                  {(s.entries || []).map((e, j) => {
                    const label = [e.heading, e.subheading].filter(Boolean).join(' — ')
                    return (
                      <div key={j}>
                        {label && label !== s.title && (
                          <div className="entry">
                            {label}
                            {e.dates && <span>{e.dates}</span>}
                          </div>
                        )}
                        {e.bullets?.length > 0 && (
                          <ul>{e.bullets.map((b, k) => <li key={k}>{b}</li>)}</ul>
                        )}
                      </div>
                    )
                  })}
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </section>
  )
}