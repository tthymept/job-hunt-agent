// Base URL for the backend. Empty by default: requests go to /api/... on the
// same host as the page. In development the Vite dev server proxies them to
// FastAPI; when deployed, FastAPI serves this app itself.
// Set VITE_API_URL (e.g. in front-end/.env.local) to call a backend elsewhere.
export const API = import.meta.env.VITE_API_URL || ''

export const JSON_HEADERS = { 'Content-Type': 'application/json' }

// The deployed app is locked with one access key. It is typed once per device
// and kept in this browser's storage. Storage can be unavailable (private mode),
// in which case the key only lasts until the page is reloaded.
const KEY_STORAGE = 'jobHuntAccessKey'
const GUEST_STORAGE = 'jobHuntGuest'
let memoryKey = ''
let memoryGuest = false

export function getAccessKey() {
  try {
    return localStorage.getItem(KEY_STORAGE) || memoryKey
  } catch {
    return memoryKey
  }
}

export function setAccessKey(key) {
  memoryKey = key
  memoryGuest = false
  try {
    localStorage.setItem(KEY_STORAGE, key)
    localStorage.removeItem(GUEST_STORAGE)
  } catch {
    // storage blocked: memoryKey still works for this visit
  }
}

// Logging out forgets the key (or the guest choice) on this device, so the
// next load shows the unlock screen again
export function clearAccess() {
  memoryKey = ''
  memoryGuest = false
  try {
    localStorage.removeItem(KEY_STORAGE)
    localStorage.removeItem(GUEST_STORAGE)
  } catch {
    // storage blocked: clearing the in-memory values is enough
  }
}

// Visitors without the key can choose to look around as a guest: the server
// lets them read everything but refuses any change (403).
export function isGuest() {
  if (getAccessKey()) return false
  try {
    return localStorage.getItem(GUEST_STORAGE) === '1' || memoryGuest
  } catch {
    return memoryGuest
  }
}

export function setGuest() {
  memoryGuest = true
  try {
    localStorage.setItem(GUEST_STORAGE, '1')
  } catch {
    // storage blocked: memoryGuest still works for this visit
  }
}

// Call at the start of anything that changes data. For a guest it shows the
// "access key needed" popup and returns true, so the caller stops there.
export function blockedForGuest() {
  if (!isGuest()) return false
  window.dispatchEvent(new Event('guest-blocked'))
  return true
}

export function accessKeyHeaders() {
  const key = getAccessKey()
  if (key) return { 'X-Access-Key': key }
  return isGuest() ? { 'X-Guest': '1' } : {}
}

// fetch() for the backend: adds the access key, and when the server says the
// key is missing or wrong (401), tells the app to show the unlock screen.
// A guest trying to change something (403) gets the access key popup instead.
export async function apiFetch(path, options = {}) {
  const res = await fetch(`${API}${path}`, {
    ...options,
    headers: { ...accessKeyHeaders(), ...options.headers },
  })
  if (res.status === 401) window.dispatchEvent(new Event('access-key-needed'))
  if (res.status === 403 && isGuest()) window.dispatchEvent(new Event('guest-blocked'))
  return res
}

// For loaders: the JSON body, or an error for any non-2xx reply, so an error
// body like { detail } never ends up stored where a list is expected
export async function readJson(res) {
  if (!res.ok) throw new Error(`Request failed (${res.status})`)
  return res.json()
}

// For actions: the JSON body, or an error carrying the server's message (its
// `detail`) for any non-2xx reply. A server crash answers with plain text, not
// JSON, so then the fallback message is used.
export async function readResult(res, fallback) {
  const data = await res.json().catch(() => null)
  if (!res.ok || !data) throw new Error(data?.detail || fallback)
  return data
}

// Opens a stored file (CV, cover letter) in a new tab. `path` is an endpoint that
// answers { url } with a link made just now, so a page left open for hours still
// opens files. The tab is opened right away, inside the click, so the browser
// doesn't block it as a popup; it is sent to the file once the link arrives.
export async function openFileLink(path) {
  const tab = window.open('', '_blank')
  try {
    const { url } = await readResult(await apiFetch(path), 'The file could not be opened.')
    if (!tab) {
      window.open(url, '_blank', 'noopener') // popups blocked: try a plain new tab
      return
    }
    tab.opener = null
    tab.location.href = url
  } catch (err) {
    tab?.close()
    console.error('Failed to open file:', err)
    alert(err.message)
  }
}
