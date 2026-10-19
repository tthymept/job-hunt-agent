import { useEffect, useRef, useState } from 'react'

// pdf.js is loaded only when a PDF is shown, so it doesn't slow down the other pages.
// The legacy build supports older Safari versions on iPhone and iPad.
async function loadPdfJs() {
  const [pdfjs, worker] = await Promise.all([
    import('pdfjs-dist/legacy/build/pdf.mjs'),
    import('pdfjs-dist/legacy/build/pdf.worker.min.mjs?url'),
  ])
  pdfjs.GlobalWorkerOptions.workerSrc = worker.default
  return pdfjs
}

// iOS Safari refuses canvases above ~16.7M pixels, so cap the sharpness
const MAX_PIXEL_RATIO = 2

// Renders every page of the PDF at `url` as a canvas that fits the container width.
// Canvases are used instead of an <iframe>, because iPhone/iPad Safari only shows
// the first page of a PDF inside an iframe and won't let you scroll it.
export default function PdfViewer({ url, headers }) {
  const containerRef = useRef(null)
  const [pdf, setPdf] = useState(null)
  const [error, setError] = useState(null)
  const [width, setWidth] = useState(0)

  // Load the document whenever the URL changes
  useEffect(() => {
    let cancelled = false
    let task = null
    setPdf(null)
    setError(null)
    loadPdfJs()
      .then(pdfjs => {
        if (cancelled) return null
        task = pdfjs.getDocument({ url, httpHeaders: headers })
        return task.promise
      })
      .then(doc => { if (!cancelled && doc) setPdf(doc) })
      .catch(err => {
        if (cancelled) return
        console.error('Failed to load PDF:', err)
        setError('Could not show the PDF preview.')
      })
    return () => {
      cancelled = true
      task?.destroy()
    }
  }, [url])

  // Track the container width, so pages re-render when the window or iPad rotates
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const observer = new ResizeObserver(entries => {
      setWidth(Math.floor(entries[0].contentRect.width))
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  // Draw every page at the current width
  useEffect(() => {
    const el = containerRef.current
    if (!pdf || !el || !width) return
    let cancelled = false
    const renderTasks = []

    async function renderPages() {
      const ratio = Math.min(window.devicePixelRatio || 1, MAX_PIXEL_RATIO)
      const canvases = []
      for (let n = 1; n <= pdf.numPages; n++) {
        const page = await pdf.getPage(n)
        if (cancelled) return
        const base = page.getViewport({ scale: 1 })
        const viewport = page.getViewport({ scale: (width / base.width) * ratio })
        const canvas = document.createElement('canvas')
        canvas.className = 'pdf-page'
        canvas.width = Math.floor(viewport.width)
        canvas.height = Math.floor(viewport.height)
        canvas.setAttribute('aria-label', `Page ${n} of ${pdf.numPages}`)
        const task = page.render({ canvas, canvasContext: canvas.getContext('2d'), viewport })
        renderTasks.push(task)
        await task.promise
        if (cancelled) return
        canvases.push(canvas)
      }
      // Swap all pages in at once so the preview doesn't flicker on resize
      el.replaceChildren(...canvases)
    }

    renderPages().catch(err => {
      if (cancelled || err?.name === 'RenderingCancelledException') return
      console.error('Failed to render PDF:', err)
      setError('Could not show the PDF preview.')
    })
    return () => {
      cancelled = true
      renderTasks.forEach(t => t.cancel())
    }
  }, [pdf, width])

  return (
    <div className="pdf-viewer">
      {error && <div className="pdf-status">{error}</div>}
      {!error && !pdf && <div className="pdf-status">Loading preview…</div>}
      <div ref={containerRef} className="pdf-pages" />
    </div>
  )
}
