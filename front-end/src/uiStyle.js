// The app has two looks: the new one (src/v2) and the classic one (src/App.jsx
// with index.css). The choice is kept in this browser's storage and read once
// when the page loads, so switching means saving the choice and reloading.
const STYLE_STORAGE = 'jobHuntUiStyle'

export const UI_STYLES = [
  { value: 'new', label: 'New', hint: 'Light, neutral layout with stage tiles and an upcoming-deadlines list.' },
  { value: 'classic', label: 'Classic', hint: 'The original look.' },
]

// 'new' unless Classic was chosen on this device
export function getUiStyle() {
  try {
    return localStorage.getItem(STYLE_STORAGE) === 'classic' ? 'classic' : 'new'
  } catch {
    return 'new' // storage blocked (private mode): fall back to the default
  }
}

// Returns false when the choice could not be saved
export function setUiStyle(style) {
  try {
    localStorage.setItem(STYLE_STORAGE, style)
    return true
  } catch {
    return false
  }
}
