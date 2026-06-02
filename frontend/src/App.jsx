import { useState, useCallback } from 'react'
import './App.css'
import Dashboard from './pages/Dashboard'
import Suppliers from './pages/Suppliers'
import FetchOrders from './pages/FetchOrders'
import RunLogs from './pages/RunLogs'
import Settings from './pages/Settings'

const PAGES = [
  { id: 'dashboard',    label: 'Dashboard' },
  { id: 'suppliers',    label: 'Suppliers' },
  { id: 'fetch-orders', label: 'Fetch Orders' },
  { id: 'run-logs',     label: 'Run Logs' },
  { id: 'settings',     label: 'Settings' },
]

function App() {
  const [activePage, setActivePage] = useState('dashboard')
  const [adminKey, setAdminKey] = useState('')
  const [sidebarOpen, setSidebarOpen] = useState(true)

  const navigate = useCallback((pageId) => setActivePage(pageId), [])

  return (
    <div className={`shell ${sidebarOpen ? 'sidebar-open' : 'sidebar-closed'}`}>
      <aside className="sidebar">
        <div className="sidebar-brand">
          <span className="brand-icon">BC</span>
          <span className="brand-name">Better Crafter</span>
          <button
            className="sidebar-toggle"
            onClick={() => setSidebarOpen((o) => !o)}
            aria-label="Toggle sidebar"
            type="button"
          >
            {sidebarOpen ? '◀' : '▶'}
          </button>
        </div>

        <nav className="sidebar-nav">
          {PAGES.map((page) => (
            <button
              key={page.id}
              className={`nav-item ${activePage === page.id ? 'active' : ''}`}
              onClick={() => navigate(page.id)}
              type="button"
            >
              {page.label}
            </button>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="admin-key-field">
            <label htmlFor="sidebar-admin-key">Admin Key</label>
            <input
              id="sidebar-admin-key"
              type="password"
              value={adminKey}
              onChange={(e) => setAdminKey(e.target.value)}
              placeholder="Enter admin key"
              autoComplete="off"
              spellCheck="false"
            />
            <p className="field-note">In-memory only. Not stored.</p>
          </div>
        </div>
      </aside>

      <main className="main-content">
        {activePage === 'dashboard'    && <Dashboard    adminKey={adminKey} navigate={navigate} />}
        {activePage === 'suppliers'    && <Suppliers    adminKey={adminKey} />}
        {activePage === 'fetch-orders' && <FetchOrders  adminKey={adminKey} />}
        {activePage === 'run-logs'     && <RunLogs      adminKey={adminKey} />}
        {activePage === 'settings'     && <Settings />}
      </main>
    </div>
  )
}

export default App
