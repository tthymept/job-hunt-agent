// Base URL for the backend. Empty by default: requests go to /api/... on the
// same host as the page, and the Vite dev server proxies them to FastAPI.
// That is what lets a phone or iPad on the same Wi-Fi use the app.
// Set VITE_API_URL (e.g. in front-end/.env.local) to call a backend elsewhere.
export const API = import.meta.env.VITE_API_URL || ''

export const JSON_HEADERS = { 'Content-Type': 'application/json' }
