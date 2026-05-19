/**
 * CyberHawkUI.js
 * Shared cinematic hacker UI system for all CyberHawk tools.
 * Drop this in src/components/tools/CyberHawkUI.js
 *
 * Exports:
 *   CYBER_STYLES   — inject once into any tool component
 *   MatrixRain     — canvas background effect
 *   SkullLoader    — animated skull during API calls
 *   HudFrame       — tactical corner-bracket card wrapper
 *   GlitchText     — text with glitch animation
 *   TypewriterText — text that types itself in
 *   ScanBar        — animated scanning progress bar
 *   IndicatorBadge — threat indicator row (critical/warning/pass/info)
 *   CopyBtn        — copy to clipboard button
 *   StatusBar      — top status strip with pulsing dot
 *   ToolHeader     — standard CyberHawk tool header
 *   HuntBtn        — "Hunt" external link button
 */

import { useState, useEffect, useRef } from 'react';
import { Copy, Check, ExternalLink, Shield } from 'lucide-react';

// ─── Palette ────────────────────────────────────────────────────────────────
export const C = {
  green:    '#00ff41',
  greenDim: '#00cc33',
  greenBg:  'rgba(0,255,65,0.06)',
  greenBdr: 'rgba(0,255,65,0.25)',
  red:      '#ff0040',
  redDim:   '#cc0033',
  redBg:    'rgba(255,0,64,0.08)',
  redBdr:   'rgba(255,0,64,0.3)',
  orange:   '#ff6600',
  orangeBg: 'rgba(255,102,0,0.08)',
  orangeBdr:'rgba(255,102,0,0.3)',
  yellow:   '#ffd700',
  yellowBg: 'rgba(255,215,0,0.08)',
  yellowBdr:'rgba(255,215,0,0.25)',
  gold:     '#d4af37',
  goldDim:  '#a07820',
  cyan:     '#00d4ff',
  cyanBg:   'rgba(0,212,255,0.06)',
  cyanBdr:  'rgba(0,212,255,0.25)',
  purple:   '#bf00ff',
  purpleBg: 'rgba(191,0,255,0.06)',
  purpleBdr:'rgba(191,0,255,0.25)',
  bg:       '#000000',
  bg1:      '#050a05',
  bg2:      '#080d08',
  bg3:      '#0d150d',
  border:   'rgba(0,255,65,0.12)',
  borderMid:'rgba(0,255,65,0.2)',
};

export const LOGO_URL = 'https://media.cyberhawkthreatintel.com/general/1771234479938-y9566.png';

// ─── Global CSS injection ────────────────────────────────────────────────────
export const CYBER_STYLES = `
  @import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Orbitron:wght@400;700;900&family=VT323&display=swap');

  .cyber-font-mono  { font-family: 'Share Tech Mono', monospace; }
  .cyber-font-title { font-family: 'Orbitron', monospace; }
  .cyber-font-vt    { font-family: 'VT323', monospace; }

  .cyber-scanlines::after {
    content: '';
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,0,0,0.03) 2px, rgba(0,0,0,0.03) 4px);
    pointer-events: none;
    z-index: 9999;
  }

  .cyber-vignette::before {
    content: '';
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: radial-gradient(ellipse at center, transparent 60%, rgba(0,0,0,0.7) 100%);
    pointer-events: none;
    z-index: 9998;
  }

  .cyber-grid-bg {
    background-image:
      linear-gradient(rgba(0,255,65,0.03) 1px, transparent 1px),
      linear-gradient(90deg, rgba(0,255,65,0.03) 1px, transparent 1px);
    background-size: 40px 40px;
  }

  @keyframes glitch {
    0%,100% { clip-path: none; transform: none; }
    20% { clip-path: polygon(0 15%, 100% 15%, 100% 25%, 0 25%); transform: translateX(-3px); color: #ff0040; }
    40% { clip-path: polygon(0 55%, 100% 55%, 100% 65%, 0 65%); transform: translateX(3px); color: #00d4ff; }
    60% { clip-path: polygon(0 80%, 100% 80%, 100% 90%, 0 90%); transform: translateX(-2px); }
    80% { clip-path: none; transform: none; }
  }
  .cyber-glitch { animation: glitch 4s infinite; }

  .hud-bracket { position: absolute; width: 16px; height: 16px; border-color: ${C.gold}; border-style: solid; }
  .hud-tl { top: -1px; left: -1px; border-width: 2px 0 0 2px; }
  .hud-tr { top: -1px; right: -1px; border-width: 2px 2px 0 0; }
  .hud-bl { bottom: -1px; left: -1px; border-width: 0 0 2px 2px; }
  .hud-br { bottom: -1px; right: -1px; border-width: 0 2px 2px 0; }

  @keyframes blink { 0%,100%{opacity:1} 50%{opacity:0} }
  .cyber-blink { animation: blink 1s infinite; }

  @keyframes pulseGlow {
    0%,100% { box-shadow: 0 0 4px currentColor, 0 0 8px currentColor; }
    50% { box-shadow: 0 0 12px currentColor, 0 0 24px currentColor, 0 0 40px currentColor; }
  }
  .cyber-pulse { animation: pulseGlow 2s infinite; }

  @keyframes scanSweep {
    0% { transform: translateY(-100%); opacity: 0.6; }
    100% { transform: translateY(100%); opacity: 0; }
  }
  .scan-sweep { animation: scanSweep 1.5s linear infinite; }

  @keyframes fadeInUp { from { opacity:0; transform:translateY(12px); } to { opacity:1; transform:translateY(0); } }
  .cyber-fade-in { animation: fadeInUp 0.4s ease both; }

  @keyframes cursorBlink { 0%,100%{border-right-color:${C.green}} 50%{border-right-color:transparent} }
  .typewriter-cursor { border-right: 2px solid ${C.green}; animation: cursorBlink 0.7s infinite; }

  @keyframes skullPulse {
    0%,100% { filter: drop-shadow(0 0 4px #ff0040) drop-shadow(0 0 8px #ff0040); transform: scale(1); }
    50% { filter: drop-shadow(0 0 20px #ff0040) drop-shadow(0 0 40px #ff0040) drop-shadow(0 0 60px #ff0040); transform: scale(1.06); }
  }
  .skull-pulse { animation: skullPulse 0.8s ease-in-out infinite; }

  @keyframes alertFlash { 0%,100%{opacity:1} 50%{opacity:0.5} }
  .alert-flash { animation: alertFlash 0.5s infinite; }

  @keyframes slideIn { from{opacity:0;transform:translateX(-10px)} to{opacity:1;transform:translateX(0)} }
  .slide-in { animation: slideIn 0.35s ease both; }

  .exec-btn {
    position: relative; overflow: hidden;
    font-family: 'Orbitron', monospace; font-weight: 700;
    letter-spacing: 0.1em; text-transform: uppercase; transition: all 0.2s;
  }
  .exec-btn::before {
    content: ''; position: absolute; top: -2px; left: -100%;
    width: 60%; height: calc(100% + 4px);
    background: linear-gradient(90deg, transparent, rgba(255,255,255,0.15), transparent);
  }
  .exec-btn:hover::before { animation: btnShine 0.6s ease forwards; }
  @keyframes btnShine { to { left: 150%; } }
  .exec-btn:hover { box-shadow: 0 0 20px rgba(255,0,64,0.6), 0 0 40px rgba(255,0,64,0.3); transform: translateY(-1px); }
  .exec-btn:active { transform: translateY(0); }

  .cyber-input:focus {
    outline: none; border-color: ${C.green} !important;
    box-shadow: 0 0 0 1px ${C.green}, 0 0 20px rgba(0,255,65,0.15), inset 0 0 20px rgba(0,255,65,0.03);
  }
  .cyber-input { caret-color: ${C.green}; }

  ::-webkit-scrollbar { width: 4px; height: 4px; }
  ::-webkit-scrollbar-track { background: ${C.bg1}; }
  ::-webkit-scrollbar-thumb { background: ${C.greenDim}; border-radius: 2px; }

  .hud-card { border: 1px solid ${C.border}; position: relative; background: ${C.bg2}; }
  .hud-card::before {
    content: ''; position: absolute; inset: 0;
    background: linear-gradient(135deg, rgba(0,255,65,0.03) 0%, transparent 50%);
    pointer-events: none;
  }

  @keyframes rotate { to { transform: rotate(360deg); } }
  .spin-slow { animation: rotate 3s linear infinite; }
  .spin-fast { animation: rotate 0.6s linear infinite; }

  @keyframes dataStream {
    0% { opacity: 0; transform: translateY(-5px); }
    10% { opacity: 1; } 90% { opacity: 1; }
    100% { opacity: 0; transform: translateY(5px); }
  }
  .data-stream { animation: dataStream 2s ease infinite; }
`;

// ─── Matrix Rain ─────────────────────────────────────────────────────────────
export function MatrixRain({ opacity = 0.4 }) {
  const canvasRef = useRef(null);
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let W = canvas.width  = window.innerWidth;
    let H = canvas.height = window.innerHeight;
    const CHARS = 'アイウエオカキクケコサシスセソタチツテトナニヌネノ0123456789ABCDEF<>{}[]';
    const cols  = Math.floor(W / 16);
    const drops = Array(cols).fill(1);
    let frame = 0;
    const draw = () => {
      ctx.fillStyle = 'rgba(0,0,0,0.05)';
      ctx.fillRect(0, 0, W, H);
      frame++;
      drops.forEach((y, i) => {
        if (frame % 2 !== 0 && i % 3 !== 0) return;
        const char   = CHARS[Math.floor(Math.random() * CHARS.length)];
        const bright = y * 16 < 30 ? '#ffffff' : y * 16 < 60 ? '#88ff88' : '#00cc33';
        ctx.fillStyle = bright;
        ctx.font = "14px 'Share Tech Mono', monospace";
        ctx.fillText(char, i * 16, y * 16);
        if (y * 16 > H && Math.random() > 0.975) drops[i] = 0;
        drops[i]++;
      });
    };
    const id = setInterval(draw, 50);
    const onResize = () => { W = canvas.width = window.innerWidth; H = canvas.height = window.innerHeight; };
    window.addEventListener('resize', onResize);
    return () => { clearInterval(id); window.removeEventListener('resize', onResize); };
  }, []);
  return <canvas ref={canvasRef} style={{ position: 'fixed', top: 0, left: 0, width: '100%', height: '100%', opacity, pointerEvents: 'none', zIndex: 0 }} />;
}

// ─── Skull Loader ─────────────────────────────────────────────────────────────
const SKULL_PHASES = [
  'INITIALISING SCAN SEQUENCE','PENETRATING DEFENCES',
  'EXTRACTING PAYLOAD DATA','RUNNING DETECTION ENGINE',
  'CROSS-REFERENCING THREAT DB','COMPILING ANALYSIS REPORT',
];

export function SkullLoader({ active, phase = 0 }) {
  const [dots, setDots]         = useState('');
  const [phaseText, setPhaseText] = useState(SKULL_PHASES[0]);
  const [glitch, setGlitch]     = useState(false);
  const [counter, setCounter]   = useState(0);

  useEffect(() => {
    if (!active) return;
    const d = setInterval(() => setDots(p => p.length >= 3 ? '' : p + '.'), 400);
    const p = setInterval(() => setPhaseText(SKULL_PHASES[Math.floor(Math.random() * SKULL_PHASES.length)]), 1200);
    const g = setInterval(() => { setGlitch(true); setTimeout(() => setGlitch(false), 150); }, 2000);
    const c = setInterval(() => setCounter(n => (n + Math.floor(Math.random() * 7)) % 100), 120);
    return () => { clearInterval(d); clearInterval(p); clearInterval(g); clearInterval(c); };
  }, [active]);

  if (!active) return null;
  return (
    <div className="hud-card rounded-xl overflow-hidden my-4 cyber-fade-in" style={{ fontFamily: "'Share Tech Mono', monospace" }}>
      <div style={{ background: 'rgba(255,0,64,0.05)', border: '1px solid rgba(255,0,64,0.3)', borderRadius: '0.75rem', padding: '2rem' }}>
        <div style={{ position: 'relative', height: '2px', background: 'rgba(255,0,64,0.15)', marginBottom: '1.5rem', overflow: 'hidden', borderRadius: '1px' }}>
          <div className="scan-sweep" style={{ position: 'absolute', inset: 0, background: 'linear-gradient(90deg, transparent, #ff0040, transparent)' }} />
        </div>
        <div style={{ display: 'flex', gap: '2rem', alignItems: 'center' }}>
          <div className="skull-pulse" style={{ flexShrink: 0 }}>
            <svg width="72" height="72" viewBox="0 0 100 100" fill="none">
              <circle cx="50" cy="50" r="48" stroke="#ff0040" strokeWidth="1" strokeDasharray="4 4" opacity="0.4" />
              <ellipse cx="50" cy="42" rx="26" ry="24" fill="#1a0000" stroke="#ff0040" strokeWidth="1.5" />
              <ellipse cx="40" cy="38" rx="7" ry="8" fill="#ff0040" opacity="0.9" />
              <ellipse cx="60" cy="38" rx="7" ry="8" fill="#ff0040" opacity="0.9" />
              <path d="M47 47 L53 47 L50 52 Z" fill="#ff0040" opacity="0.7" />
              <rect x="30" y="60" width="40" height="14" rx="4" fill="#1a0000" stroke="#ff0040" strokeWidth="1.5" />
              {[33,39,45,51,57,63].map(x => <rect key={x} x={x} y="60" width="4" height="8" rx="1" fill="#ff0040" opacity="0.8" />)}
              <circle cx="50" cy="50" r="48" stroke="#ff0040" strokeWidth="1.5" strokeDasharray="15 5" opacity="0.3" className="spin-slow" style={{transformOrigin:'50px 50px'}}/>
            </svg>
          </div>
          <div style={{ flex: 1 }}>
            <div className={glitch ? 'cyber-glitch' : ''} style={{ fontFamily: "'Orbitron', monospace", fontWeight: 900, fontSize: '0.85rem', color: '#ff0040', letterSpacing: '0.15em', marginBottom: '0.5rem', textShadow: '0 0 10px #ff0040' }}>
              ⚠ THREAT ANALYSIS IN PROGRESS ⚠
            </div>
            <div style={{ color: C.green, fontSize: '0.7rem', marginBottom: '0.75rem', letterSpacing: '0.1em' }}>{phaseText}{dots}</div>
            <div style={{ background: 'rgba(255,0,64,0.1)', height: '6px', borderRadius: '3px', overflow: 'hidden', border: '1px solid rgba(255,0,64,0.2)', position: 'relative' }}>
              <div style={{ height: '100%', background: 'linear-gradient(90deg, #ff0040, #ff6600)', width: `${counter}%`, transition: 'width 0.1s', borderRadius: '3px', boxShadow: '0 0 8px #ff0040' }} />
            </div>
          </div>
          <div style={{ flexShrink: 0, textAlign: 'center' }}>
            <div style={{ fontFamily: "'VT323', monospace", fontSize: '3rem', color: '#ff0040', lineHeight: 1, textShadow: '0 0 20px #ff0040' }}>{String(counter).padStart(2,'0')}</div>
            <div style={{ fontSize: '0.55rem', color: '#660020', letterSpacing: '0.1em' }}>PROGRESS</div>
          </div>
        </div>
        <div style={{ position: 'relative', height: '2px', background: 'rgba(255,0,64,0.15)', marginTop: '1.5rem', overflow: 'hidden', borderRadius: '1px' }}>
          <div className="scan-sweep" style={{ position: 'absolute', inset: 0, background: 'linear-gradient(90deg, transparent, #ff0040, transparent)', animationDelay: '0.75s' }} />
        </div>
      </div>
    </div>
  );
}

// ─── HUD Frame ────────────────────────────────────────────────────────────────
export function HudFrame({ children, title, subtitle, accentColor = C.green, className = '' }) {
  return (
    <div className={`hud-card rounded-xl overflow-visible relative ${className}`} style={{ border: `1px solid ${accentColor}22`, background: C.bg2 }}>
      <div className="hud-tl" style={{ borderColor: C.gold }} />
      <div className="hud-tr" style={{ borderColor: C.gold }} />
      <div className="hud-bl" style={{ borderColor: C.gold }} />
      <div className="hud-br" style={{ borderColor: C.gold }} />
      {title && (
        <div style={{ background: `linear-gradient(90deg, ${accentColor}15, transparent)`, borderBottom: `1px solid ${accentColor}22`, padding: '0.6rem 1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <div style={{ width: '6px', height: '6px', borderRadius: '50%', background: accentColor, boxShadow: `0 0 8px ${accentColor}` }} className="cyber-blink" />
          <span style={{ fontFamily: "'Share Tech Mono', monospace", fontSize: '0.65rem', color: accentColor, textTransform: 'uppercase', letterSpacing: '0.15em' }}>{title}</span>
          {subtitle && <span style={{ fontFamily: "'Share Tech Mono', monospace", fontSize: '0.6rem', color: accentColor, opacity: 0.4, marginLeft: 'auto' }}>{subtitle}</span>}
        </div>
      )}
      {children}
    </div>
  );
}

// ─── Glitch Text ──────────────────────────────────────────────────────────────
export function GlitchText({ text, className = '', style = {} }) {
  const [glitching, setGlitching] = useState(false);
  useEffect(() => {
    const t = setInterval(() => { setGlitching(true); setTimeout(() => setGlitching(false), 200); }, 3000 + Math.random() * 4000);
    return () => clearInterval(t);
  }, []);
  return <span className={`${glitching ? 'cyber-glitch' : ''} ${className}`} style={style}>{text}</span>;
}

// ─── Typewriter Text ──────────────────────────────────────────────────────────
export function TypewriterText({ text, delay = 0, speed = 18, color = C.green, className = '' }) {
  const [displayed, setDisplayed] = useState('');
  const [done, setDone]           = useState(false);
  useEffect(() => {
    setDisplayed(''); setDone(false);
    if (!text) return;
    const t = setTimeout(() => {
      let i = 0;
      const id = setInterval(() => {
        setDisplayed(text.slice(0, ++i));
        if (i >= text.length) { clearInterval(id); setDone(true); }
      }, speed);
      return () => clearInterval(id);
    }, delay);
    return () => clearTimeout(t);
  }, [text, delay, speed]);
  return <span className={`${!done ? 'typewriter-cursor' : ''} ${className}`} style={{ color, fontFamily: "'Share Tech Mono', monospace" }}>{displayed}</span>;
}

// ─── Scan Bar ─────────────────────────────────────────────────────────────────
export function ScanBar({ label, value, max = 100, color = C.green, animate = false }) {
  const pct = Math.min(100, (value / max) * 100);
  return (
    <div style={{ fontFamily: "'Share Tech Mono', monospace" }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.25rem' }}>
        <span style={{ fontSize: '0.6rem', color, opacity: 0.7, textTransform: 'uppercase', letterSpacing: '0.1em' }}>{label}</span>
        <span style={{ fontSize: '0.65rem', color, fontWeight: 'bold' }}>{value}</span>
      </div>
      <div style={{ height: '4px', background: `${color}18`, borderRadius: '2px', overflow: 'hidden', position: 'relative', border: `1px solid ${color}20` }}>
        {animate && <div className="scan-sweep" style={{ position: 'absolute', inset: 0, background: `linear-gradient(90deg, transparent, ${color}60, transparent)` }} />}
        <div style={{ height: '100%', width: `${pct}%`, background: `linear-gradient(90deg, ${color}88, ${color})`, boxShadow: `0 0 6px ${color}`, borderRadius: '2px', transition: 'width 0.8s ease' }} />
      </div>
    </div>
  );
}

// ─── Indicator Badge ──────────────────────────────────────────────────────────
const IND_CFG = {
  critical: { color: '#ff0040', bg: 'rgba(255,0,64,0.08)',  border: 'rgba(255,0,64,0.3)',  icon: '☠', label: 'CRITICAL THREAT' },
  warning:  { color: '#ff6600', bg: 'rgba(255,102,0,0.08)', border: 'rgba(255,102,0,0.3)', icon: '⚠', label: 'WARNING'         },
  info:     { color: '#ffd700', bg: 'rgba(255,215,0,0.06)', border: 'rgba(255,215,0,0.2)', icon: '◈', label: 'INFO'            },
  pass:     { color: '#00ff41', bg: 'rgba(0,255,65,0.06)',  border: 'rgba(0,255,65,0.2)',  icon: '✓', label: 'CLEAN'           },
};

export function IndicatorBadge({ ind, idx = 0 }) {
  const cfg    = IND_CFG[ind.type] || IND_CFG.info;
  const isCrit = ind.type === 'critical';
  return (
    <div className={`slide-in ${isCrit ? 'alert-flash' : ''}`}
      style={{ background: cfg.bg, border: `1px solid ${cfg.border}`, borderRadius: '0.5rem', padding: '0.75rem 1rem', display: 'flex', alignItems: 'flex-start', gap: '0.75rem', animationDelay: `${idx * 80}ms`, fontFamily: "'Share Tech Mono', monospace", position: 'relative', overflow: 'hidden' }}>
      {isCrit && <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: '3px', background: cfg.color, boxShadow: `0 0 8px ${cfg.color}` }} />}
      <span style={{ color: cfg.color, fontSize: '1rem', flexShrink: 0, textShadow: `0 0 8px ${cfg.color}` }}>{cfg.icon}</span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ color: cfg.color, fontSize: '0.6rem', fontWeight: 'bold', letterSpacing: '0.15em', marginBottom: '0.15rem' }}>[{cfg.label}]</div>
        <p style={{ color: cfg.color, fontSize: '0.7rem', opacity: 0.9, lineHeight: 1.4 }}>{ind.message}</p>
        {ind.detail && <p style={{ color: cfg.color, fontSize: '0.65rem', opacity: 0.55, marginTop: '0.2rem' }}>{ind.detail}</p>}
      </div>
    </div>
  );
}

// ─── Copy Button ──────────────────────────────────────────────────────────────
export function CopyBtn({ text, label = 'COPY', size = 'sm' }) {
  const [c, setC] = useState(false);
  return (
    <button onClick={async () => { try { await navigator.clipboard.writeText(text); } catch {} setC(true); setTimeout(() => setC(false), 1500); }}
      style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', padding: size === 'sm' ? '0.2rem 0.6rem' : '0.35rem 0.75rem', borderRadius: '0.25rem', border: `1px solid ${c ? C.green : C.border}`, background: c ? C.greenBg : 'transparent', color: c ? C.green : '#334433', fontFamily: "'Share Tech Mono', monospace", fontSize: '0.6rem', letterSpacing: '0.1em', cursor: 'pointer', transition: 'all 0.2s', flexShrink: 0 }}>
      {c ? <Check size={10} /> : <Copy size={10} />}
      {c ? 'COPIED' : label}
    </button>
  );
}

// ─── Hunt Button ──────────────────────────────────────────────────────────────
export function HuntBtn({ value, route = '/ioc-scanner' }) {
  return (
    <button onClick={() => window.open(`${route}?q=${encodeURIComponent(value)}`, '_blank', 'noopener')}
      style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', padding: '0.2rem 0.6rem', borderRadius: '0.25rem', border: '1px solid rgba(255,102,0,0.4)', background: 'rgba(255,102,0,0.1)', color: '#ff6600', fontFamily: "'Share Tech Mono', monospace", fontSize: '0.6rem', letterSpacing: '0.1em', cursor: 'pointer', transition: 'all 0.2s', flexShrink: 0 }}>
      <ExternalLink size={10} />HUNT
    </button>
  );
}

// ─── Status Bar ───────────────────────────────────────────────────────────────
export function StatusBar({ path, status = 'LIVE', statusColor = '#00ff41' }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0.4rem 1.2rem', background: '#000', borderBottom: `1px solid ${C.border}`, fontFamily: "'Share Tech Mono', monospace" }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
        {['#ff3300','#ff9900','#00cc00'].map((c, i) => <span key={i} style={{ width: '8px', height: '8px', borderRadius: '50%', background: c, display: 'inline-block' }} />)}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#334433', fontSize: '0.6rem' }}>
        <span className="cyber-blink" style={{ width: '5px', height: '5px', borderRadius: '50%', background: statusColor, display: 'inline-block', boxShadow: `0 0 6px ${statusColor}` }} />
        <span style={{ color: '#336633' }}>{path}</span>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
        <Shield size={10} color={statusColor} />
        <span style={{ fontSize: '0.6rem', color: statusColor, fontWeight: 'bold', letterSpacing: '0.15em', textShadow: `0 0 8px ${statusColor}` }}>{status}</span>
      </div>
    </div>
  );
}

// ─── Tool Header ──────────────────────────────────────────────────────────────
export function ToolHeader({ toolName, toolPath, description, accentColor = C.green }) {
  return (
    <div style={{ background: C.bg1, border: `1px solid ${C.border}`, borderRadius: '0.75rem', overflow: 'hidden', marginBottom: '1.5rem', position: 'relative' }}>
      <div className="hud-tl" style={{ borderColor: C.gold, width: '20px', height: '20px' }} />
      <div className="hud-tr" style={{ borderColor: C.gold, width: '20px', height: '20px' }} />
      <StatusBar path={toolPath} />
      <div style={{ padding: '1.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1.25rem', marginBottom: '1rem' }}>
          <div style={{ position: 'relative', flexShrink: 0 }}>
            <div style={{ width: '56px', height: '56px', borderRadius: '50%', border: `2px solid ${C.gold}`, padding: '3px', boxShadow: `0 0 20px ${C.gold}44` }}>
              <img src={LOGO_URL} alt="CyberHawk" style={{ width: '100%', height: '100%', objectFit: 'contain', borderRadius: '50%' }} onError={e => { e.target.style.display='none'; }} />
            </div>
            <div className="spin-slow" style={{ position: 'absolute', inset: '-6px', borderRadius: '50%', border: `1px dashed ${C.gold}44` }} />
          </div>
          <div style={{ borderLeft: `2px solid ${C.gold}44`, paddingLeft: '1.25rem' }}>
            <GlitchText text={toolName.toUpperCase()} style={{ fontFamily: "'Orbitron', monospace", fontWeight: 900, fontSize: '1.3rem', color: accentColor, letterSpacing: '0.08em', display: 'block', textShadow: `0 0 20px ${accentColor}` }} />
            <div style={{ fontFamily: "'Share Tech Mono', monospace", fontSize: '0.6rem', color: C.gold, letterSpacing: '0.2em', textTransform: 'uppercase', marginTop: '0.15rem' }}>
              ◈ CYBERHAWK THREAT INTEL · DEVELOPED IN-HOUSE
            </div>
          </div>
        </div>
        <div style={{ borderLeft: `2px solid ${accentColor}33`, paddingLeft: '0.75rem' }}>
          <p style={{ fontFamily: "'Share Tech Mono', monospace", fontSize: '0.7rem', color: '#336633', lineHeight: 1.6 }}>
            <span style={{ color: C.greenDim }}>&gt;&gt; </span>{description}
          </p>
        </div>
      </div>
    </div>
  );
}

// ─── Execute Button ───────────────────────────────────────────────────────────
export function ExecButton({ onClick, loading, disabled, label, loadingLabel = 'PROCESSING...', icon: Icon, color = '#ff0040' }) {
  return (
    <button onClick={onClick} disabled={loading || disabled} className="exec-btn"
      style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.6rem 1.5rem', borderRadius: '0.375rem', background: loading ? `${color}22` : `linear-gradient(135deg, ${color}cc, ${color}88)`, color: loading ? color : '#fff', border: `1px solid ${color}`, opacity: disabled ? 0.4 : 1, cursor: disabled ? 'not-allowed' : 'pointer' }}>
      {loading
        ? <><div className="spin-fast" style={{ width: '14px', height: '14px', border: `2px solid ${color}44`, borderTop: `2px solid ${color}`, borderRadius: '50%' }} />{loadingLabel}</>
        : <>{Icon && <Icon size={14} />}{label}</>
      }
    </button>
  );
}
