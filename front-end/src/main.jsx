import React from 'react'
import ReactDOM from 'react-dom/client'
import { getUiStyle } from './uiStyle'

// Each look has its own App and stylesheet. They share class names, so only the
// chosen one is loaded. Settings on the Dashboard switches between them.
const loadApp =
  getUiStyle() === 'classic'
    ? () => Promise.all([import('./App'), import('./index.css')])
    : () => Promise.all([import('./v2/App'), import('./v2/v2.css')])

loadApp().then(([{ default: App }]) => {
  ReactDOM.createRoot(document.getElementById('root')).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>
  )
})
