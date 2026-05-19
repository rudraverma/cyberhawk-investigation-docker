import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { HudFrame, GlitchText, TypewriterText, C } from '../components/CyberHawkUI';
import { useBranding } from '../App';
import { FolderOpen, Upload, Plus, Terminal, AlertTriangle, CheckCircle } from 'lucide-react';

export default function Dashboard() {
  const { branding } = useBranding();
  const navigate = useNavigate();
  const [cases, setCases]     = useState([]);
  const [uploads, setUploads] = useState([]);
  const [skills, setSkills]   = useState([]);

  useEffect(() => {
    fetch('/api/files/cases').then(r => r.json()).then(setCases).catch(() => {});
    fetch('/api/files/upload').then(r => r.json()).then(setUploads).catch(() => {});
    fetch('/api/skills/').then(r => r.json()).then(setSkills).catch(() => {});
  }, []);

  const stats = [
    { label: 'OPEN CASES',       value: cases.length,   color: C.green,  icon: FolderOpen    },
    { label: 'PENDING EVIDENCE', value: uploads.length, color: C.orange, icon: Upload         },
    { label: 'SKILLS LOADED',    value: skills.length,  color: C.cyan,   icon: CheckCircle    },
    { label: 'THREATS ACTIVE',   value: uploads.length > 0 ? '!' : '0', color: uploads.length > 0 ? C.red : C.green, icon: AlertTriangle },
  ];

  return (
    <div className="cyber-fade-in" style={{ maxWidth: '1200px', margin: '0 auto' }}>

      {/* Hero */}
      <div style={{ textAlign: 'center', marginBottom: '2rem', padding: '2rem 0' }}>
        <GlitchText
          text={branding.heroTitle || 'THREAT INTEL PLATFORM'}
          style={{ fontFamily: "'Orbitron', monospace", fontWeight: 900, fontSize: 'clamp(1.5rem, 4vw, 2.5rem)', color: C.green, display: 'block', textShadow: `0 0 30px ${C.green}`, letterSpacing: '0.1em', marginBottom: '0.5rem' }}
        />
        <TypewriterText
          text={branding.tagline || 'HUNT. ANALYSE. REPORT.'}
          color={C.gold}
          speed={40}
          style={{ fontSize: '0.8rem', letterSpacing: '0.3em' }}
        />
        {branding.welcomeMessage && (
          <p style={{ fontFamily: "'Share Tech Mono', monospace", fontSize: '0.7rem', color: '#336633', marginTop: '1rem', lineHeight: 1.6 }}>
            {branding.welcomeMessage}
          </p>
        )}
      </div>

      {/* Stat cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem', marginBottom: '2rem' }}>
        {stats.map(({ label, value, color, icon: Icon }) => (
          <HudFrame key={label} accentColor={color}>
            <div style={{ padding: '1.25rem', display: 'flex', alignItems: 'center', gap: '1rem' }}>
              <Icon size={28} color={color} style={{ opacity: 0.8 }} />
              <div>
                <div style={{ fontFamily: "'VT323', monospace", fontSize: '2.5rem', color, lineHeight: 1, textShadow: `0 0 15px ${color}` }}>{value}</div>
                <div style={{ fontFamily: "'Share Tech Mono', monospace", fontSize: '0.55rem', color, opacity: 0.6, letterSpacing: '0.15em' }}>{label}</div>
              </div>
            </div>
          </HudFrame>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>

        {/* Recent cases */}
        <HudFrame title="RECENT INVESTIGATIONS" accentColor={C.green}>
          <div style={{ padding: '1rem' }}>
            {cases.length === 0 ? (
              <p style={{ fontFamily: "'Share Tech Mono', monospace", fontSize: '0.65rem', color: '#224422', textAlign: 'center', padding: '2rem 0' }}>
                NO CASES YET — START A NEW INVESTIGATION
              </p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                {cases.slice(0, 8).map(c => (
                  <button key={c.path} onClick={() => navigate(`/files/${c.path}`)}
                    style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.5rem 0.75rem', background: C.greenBg, border: `1px solid ${C.greenBdr}`, borderRadius: '0.375rem', cursor: 'pointer', width: '100%', textAlign: 'left' }}>
                    <div>
                      <span style={{ fontFamily: "'Share Tech Mono', monospace", fontSize: '0.7rem', color: C.green }}>{c.name}</span>
                      <span style={{ fontFamily: "'Share Tech Mono', monospace", fontSize: '0.55rem', color: '#336633', marginLeft: '0.5rem' }}>{c.date}</span>
                    </div>
                    <span style={{ fontFamily: "'Share Tech Mono', monospace", fontSize: '0.55rem', color: '#336633' }}>{c.files} files</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </HudFrame>

        {/* Quick actions */}
        <HudFrame title="QUICK ACTIONS" accentColor={C.gold}>
          <div style={{ padding: '1rem', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {[
              { label: 'NEW INVESTIGATION',  icon: Plus,      path: '/new',      color: C.red    },
              { label: 'UPLOAD EVIDENCE',    icon: Upload,    path: '/upload',   color: C.orange },
              { label: 'BROWSE FILES',       icon: FolderOpen,path: '/files',    color: C.green  },
              { label: 'OPEN TERMINAL',      icon: Terminal,  path: '/terminal', color: C.cyan   },
            ].map(({ label, icon: Icon, path, color }) => (
              <button key={path} onClick={() => navigate(path)}
                style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', padding: '0.75rem 1rem', background: `${color}0d`, border: `1px solid ${color}33`, borderRadius: '0.5rem', color, cursor: 'pointer', width: '100%', textAlign: 'left', fontFamily: "'Orbitron', monospace", fontSize: '0.65rem', letterSpacing: '0.1em', transition: 'all 0.15s' }}
                onMouseOver={e => e.currentTarget.style.background = `${color}1a`}
                onMouseOut={e => e.currentTarget.style.background  = `${color}0d`}>
                <Icon size={16} />{label}
              </button>
            ))}
          </div>
        </HudFrame>

      </div>

      {/* Upload queue alert */}
      {uploads.length > 0 && (
        <div className="cyber-fade-in" style={{ marginTop: '1.5rem', background: C.orangeBg, border: `1px solid ${C.orangeBdr}`, borderRadius: '0.75rem', padding: '1rem 1.25rem', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <AlertTriangle size={18} color={C.orange} />
          <span style={{ fontFamily: "'Share Tech Mono', monospace", fontSize: '0.7rem', color: C.orange }}>
            {uploads.length} file{uploads.length > 1 ? 's' : ''} waiting in upload queue — assign to a case to begin analysis
          </span>
          <button onClick={() => navigate('/upload')} style={{ marginLeft: 'auto', padding: '0.3rem 0.75rem', background: C.orangeBg, border: `1px solid ${C.orangeBdr}`, borderRadius: '0.25rem', color: C.orange, fontFamily: "'Share Tech Mono', monospace", fontSize: '0.6rem', cursor: 'pointer' }}>
            VIEW →
          </button>
        </div>
      )}
    </div>
  );
}
