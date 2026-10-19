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
let memoryKey = ''

export function getAccessKey() {
  try {
    return localStorage.getItem(KEY_STORAGE) || memoryKey
  } catch {
    return memoryKey
  }
}

export function setAccessKey(key) {
  memoryKey = key
  try {
    localStorage.setItem(KEY_STORAGE, key)
  } catch {
    // storage blocked: memoryKey still works for this visit
  }
}

export function accessKeyHeaders() {
  const key = getAccessKey()
  return key ? { 'X-Access-Key': key } : {}
}

// fetch() for the backend: adds the access key, and when the server says the
// key is missing or wrong (401), tells the app to show the unlock screen.
export async function apiFetch(path, options = {}) {
  const res = await fetch(`${API}${path}`, {
    ...options,
    headers: { ...accessKeyHeaders(), ...options.headers },
  })
  if (res.status === 401) window.dispatchEvent(new Event('access-key-needed'))
  return res
}

// For loaders: the JSON body, or an error for any non-2xx reply, so an error
// body like { detail } never ends up stored where a list is expected
export async function readJson(res) {
  if (!res.ok) throw new Error(`Request failed (${res.status})`)
  return res.json()
}
