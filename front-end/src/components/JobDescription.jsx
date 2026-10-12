// Matches lines that start with a bullet character
const BULLET = /^\s*[•●▪◦·*–—-]\s+/
// Small words that may stay lowercase inside a Title Case heading
const SMALL_WORDS = new Set(['a', 'an', 'the', 'of', 'and', 'or', 'for', 'to', 'in', 'on', 'at', 'with', 'vs', '&'])

// A heading is a short line with no ending punctuation where every main word
// is capitalised ("Who May Apply"), or a short line that ends with ":"
function isHeading(line) {
  const text = line.trim()
  if (text.length > 60) return false
  const words = text.replace(/:$/, '').split(/\s+/)
  if (words.length > 8) return false
  if (text.endsWith(':')) return true
  if (/[.,;!?]$/.test(text)) return false
  return words.every(w => SMALL_WORDS.has(w.toLowerCase()) || /^[A-Z0-9(]/.test(w))
}

// Turns the raw text into blocks: { type: 'heading' | 'para' | 'list', ... }
function parseBlocks(text) {
  const blocks = []
  for (const raw of (text || '').replace(/\r\n?/g, '\n').split('\n')) {
    const line = raw.trim()
    if (!line) continue

    if (BULLET.test(raw)) {
      const item = line.replace(BULLET, '')
      const last = blocks[blocks.length - 1]
      if (last && last.type === 'list') last.items.push(item) // keep adding to the same list
      else blocks.push({ type: 'list', items: [item] })
    } else if (isHeading(line)) {
      blocks.push({ type: 'heading', text: line.replace(/:$/, '') })
    } else {
      blocks.push({ type: 'para', text: line })
    }
  }
  return blocks
}

// Bolds a short label before a colon: "KYC (Know Your Customer): helping..."
function Labeled({ text }) {
  const m = /^([^:]{3,45}):\s+(.+)$/.exec(text)
  if (m && m[1].split(/\s+/).length <= 6) {
    return (
      <>
        <strong>{m[1]}:</strong> {m[2]}
      </>
    )
  }
  return <>{text}</>
}

export default function JobDescription({ text }) {
  const blocks = parseBlocks(text)
  if (blocks.length === 0) return <div className="jd">No description.</div>

  return (
    <div className="jd-rich">
      {blocks.map((b, i) => {
        if (b.type === 'heading') return <h5 key={i}>{b.text}</h5>
        if (b.type === 'list') {
          return (
            <ul key={i}>
              {b.items.map((item, j) => (
                <li key={j}><Labeled text={item} /></li>
              ))}
            </ul>
          )
        }
        return <p key={i}><Labeled text={b.text} /></p>
      })}
    </div>
  )
}