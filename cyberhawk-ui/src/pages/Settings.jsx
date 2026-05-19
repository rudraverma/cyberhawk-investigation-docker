import { useEffect, useRef, useState } from 'react';
import { useBranding } from '../App';
import { HudFrame, C } from '../components/CyberHawkUI';
import { Save, Upload, Trash2, CheckCircle, AlertTriangle, RotateCcw } from 'lucide-react';

const DEFAULTS = {
  platformName:  'CYBERHAWK',
  heroTitle:     'THREAT INTEL PLATFORM',
  heroSubtitle:  'THREAT INTEL PLATFORM',
  tagline:       'HUNT. ANALYSE. REPORT.',
  welcomeMessage:'',
  analystName:   '',
  organisation:  '',
  tlpDefault:    'TLP:AMBER',
  footerText:    'CyberHawk Threat Intel',
  statusLabel:   'LIVE',
};

export default function Settings() {
  const { branding, setBranding } = useBranding();
  const [form,   setForm]   = useState({ ...DEFAULTS, ...branding });
  const [saving, setSaving] = useState(false);
  const [msg,    setMsg]    = useState(null);
  const [logoPreview, setLogoPreview] = useState(branding.logoOverride ? '/api/config/logo' : null);
  const fileRef = useRef(null);

  useEffect(() => { setForm({ ...DEFAULTS, ...branding }); }, [branding]);

  const flash = (text, ok = true) => { setMsg({ text, ok }); setTimeout(() => setMsg(null), 4000); };

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const save = async () => {
    setSaving(true);
    const r = await fetch('/api/config/branding', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(form),
    });
    setSaving(false);
    if (r.ok) {
      const updated = await r.json();
      setBranding(updated);
      flash('Settings saved');
    } else {
      flash('Save failed', false);
    }
  };

  const reset = () => { setForm({ ...DEFAULTS }); flash('Reset to defaults — click SAVE to apply'); };

  const uploadLogo = async (file) => {
    const fd = new FormData();
    fd.append('file', file);
    const r = await fetch('/api/config/logo', { method: 'POST', body: fd });
    if (r.ok) {
      setLogoPreview(`/api/config/logo?t=${Date.now()}`);
      setBranding(b => ({ ...b, logoOverride: true }));
      flash('Logo uploaded');
    } else {
      flash('Logo upload failed', false);
    }
  };

  const deleteLogo = async () => {
    await fetch('/api/config/logo', { method: 'DELETE' });
    setLogoPreview(null);
    setBranding(b => ({ ...b, logoOverride: false }));
    flash('Logo removed — using default');
  };

  return (
    <div className="cyber-fade-in" style={{ maxWidth: '800px', margin: '0 auto' }}>

      {msg && (
        <div className="cyber-fade-in" style={{ marginBottom: '1rem', padding: '0.65rem 1rem', borderRadius: '0.5rem', background: msg.ok ? C.greenBg : C.redBg, border: `1px solid ${msg.ok ? C.greenBdr : C.redBdr}`, color: msg.ok ? C.green : C.red, fontFamily: "'Share Tech Mono', monospace", fontSize: '0.7rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          {msg.ok ? <CheckCircle size={14} /> : <AlertTriangle size={14} />}{msg.text}
        </div>
      )}

      {/* Logo */}
      <HudFrame title="LOGO" accentColor={C.gold} style={{ marginBottom: '1.5rem' }}>
        <div style={{ padding: '1rem', display: 'flex', alignItems: 'center', gap: '1.5rem', flexWrap: 'wrap' }}>
          <div style={{ width: '72px', height: '72px', borderRadius: '50%', border: `2px solid ${C.gold}44`, display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden', background: '#050505' }}>
            {logoPreview
              ? <img src={logoPreview} alt="logo" style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
              : <span style={{ fontFamily: "'Orbitron', monospace", fontSize: '1.2rem', color: C.gold }}>CH</span>}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            <input ref={fileRef} type="file" accept="image/*" style={{ display: 'none' }} onChange={e => e.target.files[0] && uploadLogo(e.target.files[0])} />
            <button onClick={() => fileRef.current.click()} style={btn(C.gold)}><Upload size={13} /> UPLOAD LOGO</button>
            {logoPreview && <button onClick={deleteLogo} style={btn(C.red)}><Trash2 size={13} /> REMOVE</button>}
            <span style={{ fontFamily: "'Share Tech Mono', monospace", fontSize: '0.55rem', color: '#445544' }}>PNG/SVG recommended · square · max 2 MB</span>
          </div>
        </div>
      </HudFrame>

      {/* Platform identity */}
      <HudFrame title="PLATFORM IDENTITY" accentColor={C.green} style={{ marginBottom: '1.5rem' }}>
        <div style={{ padding: '1rem', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
          <Field label="PLATFORM NAME"  value={form.platformName}  onChange={v => set('platformName',  v)} />
          <Field label="STATUS LABEL"   value={form.statusLabel}   onChange={v => set('statusLabel',   v)} placeholder="LIVE" />
          <Field label="HERO TITLE"     value={form.heroTitle}     onChange={v => set('heroTitle',     v)} span />
          <Field label="HERO SUBTITLE"  value={form.heroSubtitle}  onChange={v => set('heroSubtitle',  v)} span />
          <Field label="TAGLINE"        value={form.tagline}       onChange={v => set('tagline',       v)} span />
          <Field label="WELCOME MESSAGE (OPTIONAL)" value={form.welcomeMessage} onChange={v => set('welcomeMessage', v)} textarea span />
        </div>
      </HudFrame>

      {/* Analyst / org */}
      <HudFrame title="ANALYST PROFILE" accentColor={C.cyan} style={{ marginBottom: '1.5rem' }}>
        <div style={{ padding: '1rem', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
          <Field label="ANALYST NAME"  value={form.analystName}   onChange={v => set('analystName',   v)} />
          <Field label="ORGANISATION"  value={form.organisation}  onChange={v => set('organisation',  v)} />
        </div>
      </HudFrame>

      {/* Footer / TLP */}
      <HudFrame title="FOOTER & CLASSIFICATION" accentColor={C.orange} style={{ marginBottom: '1.5rem' }}>
        <div style={{ padding: '1rem', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
          <Field label="FOOTER TEXT" value={form.footerText}  onChange={v => set('footerText',  v)} />
          <Field label="DEFAULT TLP" value={form.tlpDefault}  onChange={v => set('tlpDefault',  v)} placeholder="TLP:AMBER" />
        </div>
      </HudFrame>

      {/* Actions */}
      <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}>
        <button onClick={reset}  style={btn(C.orange)}><RotateCcw size={13} /> RESET DEFAULTS</button>
        <button onClick={save}   style={btn(C.green)} disabled={saving}>
          <Save size={13} /> {saving ? 'SAVING...' : 'SAVE SETTINGS'}
        </button>
      </div>
    </div>
  );
}

function Field({ label, value, onChange, placeholder = '', textarea = false, span = false }) {
  const style = {
    fontFamily: "'Share Tech Mono', monospace", fontSize: '0.65rem',
    background: '#001100', border: `1px solid ${C.greenBdr}`,
    color: C.green, padding: '0.4rem 0.6rem', borderRadius: '0.25rem',
    width: '100%', outline: 'none', resize: textarea ? 'vertical' : undefined,
  };
  return (
    <div style={{ gridColumn: span ? '1 / -1' : undefined }}>
      <label style={{ display: 'block', fontFamily: "'Share Tech Mono', monospace", fontSize: '0.55rem', color: '#336633', letterSpacing: '0.1em', marginBottom: '0.3rem' }}>{label}</label>
      {textarea
        ? <textarea value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder} rows={3} style={style} />
        : <input    value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder} style={style} />}
    </div>
  );
}

const btn = (color) => ({
  display: 'flex', alignItems: 'center', gap: '0.4rem',
  padding: '0.5rem 1rem', background: `${color}0d`,
  border: `1px solid ${color}33`, borderRadius: '0.375rem',
  color, fontFamily: "'Share Tech Mono', monospace", fontSize: '0.65rem',
  cursor: 'pointer', letterSpacing: '0.05em',
});
