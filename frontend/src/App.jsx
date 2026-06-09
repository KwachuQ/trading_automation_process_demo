import { NavLink, Routes, Route, useLocation } from 'react-router-dom'
import { LayoutDashboard, Activity, Database, ClipboardCheck } from 'lucide-react'
import PreMarketPage from './pages/PreMarketPage.jsx'
import SessionDashboard from './pages/SessionDashboard.jsx'
import FeatureStorePage from './pages/FeatureStorePage.jsx'
import ReviewPage from './pages/ReviewPage.jsx'
import { PreMarketProvider, usePreMarket } from './context/premarket.jsx'
import { Badge } from './components/ui.jsx'

const navItems = [
  { path: '/', label: 'Pre-Market', icon: LayoutDashboard },
  { path: '/session', label: 'Session', icon: Activity },
  { path: '/feature-store', label: 'Feature Store', icon: Database },
  { path: '/review', label: 'Review', icon: ClipboardCheck },
]

// Maps route paths to their console label
const CONSOLE_LABELS = {
  '/': 'Pre-Market',
  '/session': 'Session',
  '/feature-store': 'Feature Store',
  '/review': 'Review'
}

function NavConsole() {
  const { pipelineStatus, today } = usePreMarket()
  const { pathname } = useLocation()
  const label = CONSOLE_LABELS[pathname] || 'Pre-Market'
  return (
    <div className="nav-console">
      <span style={{ fontFamily: 'var(--font-ui)', fontSize: 12, fontWeight: 600, color: 'var(--c-muted)' }}>
        {label}
      </span>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--c-dim)' }}>{today}</span>
      <Badge status={pipelineStatus} />
    </div>
  )
}

export default function App() {
  return (
    <PreMarketProvider>
      <div className="app-shell">
        <nav className="app-nav">
          <span className="nav-brand">TPA</span>
          <div className="nav-links">
            {navItems.map(({ path, label, icon: Icon }) => (
              <NavLink
                key={path}
                to={path}
                end={path === '/'}
                className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
              >
                <Icon />
                {label}
              </NavLink>
            ))}
          </div>
          <NavConsole />
        </nav>
        <main className="app-main">
          <Routes>
            <Route path="/" element={<PreMarketPage />} />
            <Route path="/session" element={<SessionDashboard />} />
            <Route path="/feature-store" element={<FeatureStorePage />} />
            <Route path="/review" element={<ReviewPage />} />
          </Routes>
        </main>
      </div>
    </PreMarketProvider>
  )
}
