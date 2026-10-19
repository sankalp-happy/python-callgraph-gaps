import { StrictMode, useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import LiveDemo from './pages/LiveDemo.tsx'

// No router dependency: the live demo has exactly one other "page", so a
// hash check is enough and adds no new risk on presentation day.
const TITLES: Record<string, string> = {
  '#live': 'Watch the map miss a road — TraceWeave-Core',
  '': 'TraceWeave-Core — What we are building and why',
}

function Root() {
  const [hash, setHash] = useState(window.location.hash)
  useEffect(() => {
    const onChange = () => setHash(window.location.hash)
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  // Without this the tab still reads "What we are building and why" on the
  // demo -- which is what shows up when the presentation machine is mirrored
  // and someone is looking at the tab strip.
  useEffect(() => {
    document.title = TITLES[hash] ?? TITLES['']
  }, [hash])
  return hash === '#live' ? <LiveDemo /> : <App />
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Root />
  </StrictMode>,
)
