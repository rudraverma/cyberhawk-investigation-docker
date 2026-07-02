import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { HudFrame, C } from '../components/CyberHawkUI';
import {
  Globe, Search, CheckCircle, AlertTriangle,
  FolderOpen, Loader, XCircle,
} from 'lucide-react';

const TYPES = ['Phishing', 'Malware', 'OSINT', 'Incident Response', 'Threat Hunt', 'Other'];
const TLP   = ['TLP:WHITE', 'TLP:GREEN', 'TLP:AMBER', 'TLP:RED'];

const LEVEL_COLOR = {
  phase:    C.cyan,
  dns:      C.green,
  whois:    C.green,
  redirect: C.orange,
  warn:     C.orange,
  error:    C.red,
  ioc:      '#ff4466',
  port:     C.cyan,
  good:     C.green,
  skill:    C.purple,
  done:     C.gold,
  info:     C.green,
  sep:      'rgba(0,255,65,0.15)',
};

export default function SubmitUrl() {
  const navigate = useNavigate();
  const logRef   = useRef(null);

  const [form, setForm] = useState({
    url:       '',
    case_name: '',
    case_type: 'Phishing',
    tlp:       'TLP:AMBER',
    analyst:   '',
  });
  const [state,    setState]    = useState('idle');
  const [logs,     setLogs]     = useState([]);
  const [casePath, setCasePath] = useState('');
  const [error,    setError]    = useState(null);

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const onUrlChange = (v) => {
    set('url', v);
    if (!form.case_name) {
      try {
        const u = new URL(v.includes('://') ? v : 'https://' + v);
        if (u.hostname) set('case_name', u.hostname.replace(/\./g, '-'));
      } catch {}
    }
  };

  const reset = () => { setState('idle'); setLogs([]); setCasePath(''); setError(null); };

  const submit = async () => {
    if (!form.url.trim()) { setError('URL is required'); return; }
    setError(null); setLogs([]); setCasePath(''); setState('running');
    let taskId = null, path = null;
    try {
      const r = await fetch('/api/investigate/url', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(form),
      });
      const data = await r.json();
      if (!data.ok) { setState('error'); setError(data.error || 'Server error'); return; }
      taskId = data.task_id; path = data.case_path; setCasePath(path);
    } catch (e) { setState('error'); setError(`Request failed: ${e.message}`); return; }

    const es = new EventSource(`/api/investigate/url/${taskId}/stream`);
    es.onmessage = (e) => {
      let entry; try { entry = JSON.parse(e.data); } catch { return; }
      if (entry.type === 'done') {
        setState(entry.status === 'complete' ? 'complete' : 'error');
        if (entry.case_path) setCasePath(entry.case_path);
        es.close();
      } else { setLogs(prev => [...prev, entry]); }
    };
    es.onerror = () => { setState(prev => prev === 'running' ? 'error' : prev); es.close(); };
  };

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [logs]);

  const isRunning  = state === 'running';
  const isComplete = state === 'complete';
  const isError    = state === 'error';
  const showStream = state !== 'idle';
  const streamAccent = isComplete ? C.green : isError ? C.red : C.cyan;
  const streamLabel  = isComplete ? '  [ COMPLETE ]' : isError ? '  [ ERROR ]' : '  [ LIVE ]';

  return (
    <div className="cyber-fade-in" style={{ maxWidth: '940px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <HudFrame title="SUBMIT URL FOR INVESTIGATION" accentColor={C.cyan}>
        <div style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          {error && (
            <div style={{ padding: '0.6rem 0.9rem', borderRadius: '0.375rem', background: C.redBg, border: `1px solid ${C.redBdr}`, color: C.red, fontFamily: "'Share Tech Mono', monospace", fontSize: '0.65rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <AlertTriangle size={13} />{error}
            </div>
          )}
          <div>
            <label style={labelStyle}>TARGET URL *</label>
            <div style={{ position: 'relative' }}>
              <Globe size={14} color={C.cyan} style={{ position: 'absolute', left: '0.65rem', top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none' }} />
              <input value={form.url} onChange={e => onUrlChange(e.target.value)}
                placeholder="https://suspicious-domain.com/login" disabled={isRunning}
                style={{ ...inputStyle, paddingLeft: '2.1rem', borderColor: C.cyanBdr, color: C.cyan, fontSize: '0.72rem' }}
                onKeyDown={e => e.key === 'Enter' && !isRunning && submit()} />
            </div>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '1rem' }}>
            <Field label="CASE NAME (AUTO)" value={form.case_name} onChange={v => set('case_name', v)} placeholder="auto-from-domain" disabled={isRunning} />
            <Select label="CASE TYPE" value={form.case_type} onChange={v => set('case_type', v)} options={TYPES} disabled={isRunning} />
            <Select label="TLP" value={form.tlp} onChange={v => set('tlp', v)} options={TLP} disabled={isRunning} />
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: '1rem', alignItems: 'flex-end' }}>
            <Field label="ANALYST (OPT)" value={form.analyst} onChange={v => set('analyst', v)} placeholder="Handle or name" disabled={isRunning} />
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              {showStream && !isRunning && (
                <button onClick={reset} style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0.65rem 1rem', background: 'transparent', border: `1px solid ${C.greenBdr}`, borderRadius: '0.5rem', color: '#336633', fontFamily: "'Share Tech Mono', monospace", fontSize: '0.6rem', cursor: 'pointer', whiteSpace: 'nowrap' }}>NEW</button>
              )}
              <button onClick={submit} disabled={isRunning}
                style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.65rem 1.5rem', background: isRunning ? 'transparent' : `${C.cyan}0d`, border: `1px solid ${isRunning ? C.cyanBdr : C.cyan}55`, borderRadius: '0.5rem', color: C.cyan, fontFamily: "'Orbitron', monospace", fontSize: '0.62rem', letterSpacing: '0.1em', cursor: isRunning ? 'not-allowed' : 'pointer', opacity: isRunning ? 0.5 : 1, whiteSpace: 'nowrap' }}>
                {isRunning ? <><Loader size={13} className="spin-fast" style={{ flexShrink: 0 }} /> INVESTIGATING...</> : <><Search size={13} /> INVESTIGATE URL</>}
              </button>
            </div>
          </div>
        </div>
      </HudFrame>

      {showStream && (
        <HudFrame title={`INVESTIGATION STREAM${streamLabel}`} accentColor={streamAccent}>
          <div ref={logRef} style={{ padding: '0.85rem 1.1rem', height: '440px', overflowY: 'auto', fontFamily: "'Share Tech Mono', monospace", fontSize: '0.64rem', lineHeight: '1.8', background: '#00050a' }}>
            {logs.map((entry, i) => {
              if (entry.level === 'sep') return <div key={i} style={{ color: LEVEL_COLOR.sep, userSelect: 'none', letterSpacing: '0.05em' }}>{'─'.repeat(72)}</div>;
              const color = LEVEL_COLOR[entry.level] || C.green;
              return <div key={i} style={{ color, whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>{entry.msg}</div>;
            })}
            {isRunning && <div style={{ color: C.cyan, marginTop: '0.2rem', opacity: 0.7 }}><span className="cyber-blink">▍</span></div>}
            {isError && !isRunning && <div style={{ color: C.red, marginTop: '0.5rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}><XCircle size={12} /> Investigation ended with errors.</div>}
          </div>
          {(isComplete || isError || casePath) && (
            <div style={{ padding: '0.7rem 1.1rem', borderTop: `1px solid ${C.border}`, display: 'flex', alignItems: 'center', gap: '1rem', background: 'rgba(0,0,0,0.4)' }}>
              {isComplete && <CheckCircle size={14} color={C.green} />}
              {isError    && <XCircle    size={14} color={C.red} />}
              <span style={{ fontFamily: "'Share Tech Mono', monospace", fontSize: '0.62rem', color: isComplete ? C.green : isError ? C.red : '#336633', flex: 1 }}>
                {isComplete ? 'All artifacts saved to case directory.' : isError ? 'Investigation incomplete.' : 'Case created.'}
                {casePath && <span style={{ color: '#336633', marginLeft: '0.75rem' }}>{casePath}</span>}
              </span>
              {casePath && (
                <button onClick={() => navigate(`/files/${casePath}`)}
                  style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0.4rem 1rem', background: `${C.green}0d`, border: `1px solid ${C.green}44`, borderRadius: '0.375rem', color: C.green, fontFamily: "'Share Tech Mono', monospace", fontSize: '0.6rem', cursor: 'pointer', whiteSpace: 'nowrap' }}>
                  <FolderOpen size={12} /> OPEN CASE
                </button>
              )}
            </div>
          )}
        </HudFrame>
      )}
    </div>
  );
}

function Field({ label, value, onChange, placeholder = '', disabled = false }) {
  return (
    <div>
      <label style={labelStyle}>{label}</label>
      <input value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder} disabled={disabled} style={{ ...inputStyle, opacity: disabled ? 0.5 : 1 }} />
    </div>
  );
}

function Select({ label, value, onChange, options, disabled = false }) {
  return (
    <div>
      <label style={labelStyle}>{label}</label>
      <select value={value} onChange={e => onChange(e.target.value)} disabled={disabled} style={{ ...inputStyle, opacity: disabled ? 0.5 : 1 }}>
        {options.map(o => <option key={o} value={o}>{o}</option>)}
      </select>
    </div>
  );
}

const labelStyle = { display: 'block', fontFamily: "'Share Tech Mono', monospace", fontSize: '0.55rem', color: '#336633', letterSpacing: '0.1em', marginBottom: '0.3rem' };
const inputStyle = { fontFamily: "'Share Tech Mono', monospace", fontSize: '0.65rem', background: '#001100', border: `1px solid ${C.greenBdr}`, color: C.green, padding: '0.4rem 0.6rem', borderRadius: '0.25rem', width: '100%', outline: 'none', boxSizing: 'border-box' };
