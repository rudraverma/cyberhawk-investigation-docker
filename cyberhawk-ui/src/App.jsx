import { createContext, useContext, useEffect, useState } from 'react';
import { BrowserRouter, NavLink, Route, Routes } from 'react-router-dom';
import { CYBER_STYLES, C, MatrixRain, LOGO_URL } from './components/CyberHawkUI';
import { LayoutDashboard, Upload, FolderOpen, Terminal, Settings, Plus, Shield, Globe, Activity } from 'lucide-react';

import Dashboard        from './pages/Dashboard';
import UploadZone       from './pages/UploadZone';
import FileBrowser      from './pages/FileBrowser';
import ReportViewer     from './pages/ReportViewer';
import TerminalPage     from './pages/Terminal';
import SettingsPage     from './pages/Settings';
import NewInvestigation from './pages/NewInvestigation';
import SubmitUrl        from './pages/SubmitUrl';
import TriageFile       from './pages/TriageFile';
import MitmPage         from './pages/MitmPage';

// ── Branding context ──────────────────────────────────────────────────────────
export const BrandingCtx = createContext({});
export function useBranding() { return useContext(BrandingCtx); }

const NAV = [
  { to: '/',          icon: LayoutDashboard, label: 'DASHBOARD'   },
  { to: '/upload',    icon: Upload,          label: 'UPLOAD'       },
  { to: '/submit-url',icon: Globe,           label: 'SUBMIT URL'   },
  { to: '/triage',    icon: Shield,          label: 'TRIAGE'       },
  { to: '/files',     icon: FolderOpen,      label: 'FILES'        },
  { to: '/new',       icon: Plus,            label: 'NEW CASE'     },
  { to: '/terminal',  icon: Terminal,        label: 'TERMINAL'     },
  { to: '/settings',  icon: Settings,        label: 'SETTINGS'     },
  { to: '/mitm',      icon: Activity,        label: 'MITM'         },
];

export default function App() {
  const [branding, setBranding] = useState(null);

  useEffect(() => {
    fetch('/api/config/branding')
      .then(r => r.json())
      .then(setBranding)
      .catch(() => setBranding({ platformName: 'CyberHawk', heroTitle: 'THREAT INTEL PLATFORM', statusLabel: 'LIVE' }));
  }, []);

  if (!branding) {
    return (
      <div style={{ background: '#000', height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', color: C.green, fontFamily: "'Share Tech Mono', monospace" }}>
        INITIALISING...
      </div>
    );
  }

  const logoSrc = branding.logoOverride ? '/api/config/logo' : (branding.logoUrl || LOGO_URL);

  return (
    <BrandingCtx.Provider value={{ branding, setBranding }}>
      <BrowserRouter>
        <style>{CYBER_STYLES}</style>

        <div className="cyber-scanlines cyber-vignette cyber-grid-bg" style={{ background: C.bg, minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
          <MatrixRain opacity={0.15} />

          {/* ── Top bar ── */}
          <header style={{ position: 'relative', zIndex: 10, background: 'rgba(0,0,0,0.9)', borderBottom: `1px solid ${C.border}`, padding: '0.5rem 1.5rem', display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <div style={{ position: 'relative' }}>
                <div style={{ width: '36px', height: '36px', borderRadius: '50%', border: `1px solid ${C.gold}`, padding: '2px', boxShadow: `0 0 12px ${C.gold}44` }}>
                  <img src={logoSrc} alt="logo" style={{ width: '100%', height: '100%', objectFit: 'contain', borderRadius: '50%' }} onError={e => { e.target.style.display = 'none'; }} />
                </div>
                <div className="spin-slow" style={{ position: 'absolute', inset: '-4px', borderRadius: '50%', border: `1px dashed ${C.gold}44` }} />
              </div>
              <div>
                <div style={{ fontFamily: "'Orbitron', monospace", fontWeight: 900, fontSize: '0.75rem', color: C.green, letterSpacing: '0.1em', textShadow: `0 0 10px ${C.green}` }}>
                  {branding.platformName || 'CYBERHAWK'}
                </div>
                <div style={{ fontFamily: "'Share Tech Mono', monospace", fontSize: '0.55rem', color: C.gold, letterSpacing: '0.15em' }}>
                  {branding.heroSubtitle || 'THREAT INTEL PLATFORM'}
                </div>
              </div>
            </div>

            {/* Nav */}
            <nav style={{ display: 'flex', gap: '0.25rem', marginLeft: '1.5rem', flex: 1 }}>
              {NAV.map(({ to, icon: Icon, label }) => (
                <NavLink key={to} to={to} end={to === '/'}
                  style={({ isActive }) => ({
                    display: 'flex', alignItems: 'center', gap: '0.3rem',
                    padding: '0.3rem 0.7rem', borderRadius: '0.25rem',
                    fontFamily: "'Share Tech Mono', monospace", fontSize: '0.6rem',
                    letterSpacing: '0.1em', textDecoration: 'none',
                    color: isActive ? C.green : '#336633',
                    background: isActive ? C.greenBg : 'transparent',
                    border: `1px solid ${isActive ? C.greenBdr : 'transparent'}`,
                    transition: 'all 0.15s',
                  })}>
                  <Icon size={12} />{label}
                </NavLink>
              ))}
            </nav>

            {/* Status */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
              <span className="cyber-blink" style={{ width: '6px', height: '6px', borderRadius: '50%', background: C.green, display: 'inline-block', boxShadow: `0 0 6px ${C.green}` }} />
              <Shield size={12} color={C.green} />
              <span style={{ fontFamily: "'Share Tech Mono', monospace", fontSize: '0.6rem', color: C.green, letterSpacing: '0.15em' }}>
                {branding.statusLabel || 'LIVE'}
              </span>
            </div>
          </header>

          {/* ── Page content ── */}
          <main style={{ flex: 1, position: 'relative', zIndex: 5, padding: '1.5rem', overflowY: 'auto' }}>
            <Routes>
              <Route path="/"            element={<Dashboard />} />
              <Route path="/upload"      element={<UploadZone />} />
              <Route path="/submit-url"  element={<SubmitUrl />} />
              <Route path="/files/*"     element={<FileBrowser />} />
              <Route path="/view"        element={<ReportViewer />} />
              <Route path="/new"         element={<NewInvestigation />} />
              <Route path="/terminal"    element={<TerminalPage />} />
              <Route path="/settings"    element={<SettingsPage />} />
              <Route path="/triage"      element={<TriageFile />} />
              <Route path="/mitm"        element={<MitmPage />} />
            </Routes>
          </main>

          {/* ── Footer ── */}
          <footer style={{ position: 'relative', zIndex: 10, borderTop: `1px solid ${C.border}`, padding: '0.35rem 1.5rem', display: 'flex', justifyContent: 'space-between', background: 'rgba(0,0,0,0.8)' }}>
            <span style={{ fontFamily: "'Share Tech Mono', monospace", fontSize: '0.55rem', color: '#224422', letterSpacing: '0.1em' }}>
              {branding.footerText || 'CyberHawk Threat Intel'}
            </span>
            <span style={{ fontFamily: "'Share Tech Mono', monospace", fontSize: '0.55rem', color: '#224422' }}>
              {branding.tlpDefault || 'TLP:AMBER'}
            </span>
          </footer>
        </div>
      </BrowserRouter>
    </BrandingCtx.Provider>
  );
}
