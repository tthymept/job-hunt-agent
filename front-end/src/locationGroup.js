// Cities we want to treat as one place, however the location text is written.
// Add more here as you track jobs in other cities: lowercase name -> display label.
const KNOWN_CITIES = {
  singapore: 'Singapore',
  bangkok: 'Bangkok',
}

// Turns any location text into { key, label }.
// "Bangkok", "Bangkok, Thailand" and "Bangkok, Huay Kwang" all give the key "bangkok".
export function locationGroup(loc) {
  if (!loc || loc === '—') return { key: 'none', label: 'No location' }

  const lower = loc.toLowerCase()
  for (const [name, label] of Object.entries(KNOWN_CITIES)) {
    if (lower.includes(name)) return { key: name, label }
  }

  // Unknown city: use the part before the first comma
  const first = loc.split(',')[0].trim()
  return { key: first.toLowerCase(), label: first }
}