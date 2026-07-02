import { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { HudFrame, C } from '../components/CyberHawkUI';
import { FileText, AlertTriangle, CheckCircle, FolderOpen, Zap } from 'lucide-react';

const LEVEL_COLOR = {
  phase: C.cyan, skill: C.purple, dns: C.green, whois: C.green,
  redirect: C.orange, warn: C.orange, error: C.red, ioc: '#ff4466',
  port: C.cyan, good: C.green, done: C.gold, info: C.green, sep: 'rgba(0,255,65,0.15)',
};

export default function TriageFile() {
  const [params] = useSearchParams();
  const navigate  = useNavigate();
  const logRef    = useRef(null);

  const [filename, setFilename]   = useState(params.get('file') || '');
  const [caseType, setCaseType]   = useState('General');
  const [tlp, setTlp]             = useState('TLP:AMBER');
  const [analyst, setAnalyst]     = useState('');
  const [state, setState]         = useState('idle');
  const [logs, setLogs]           = useState([]);
  const [taskId, setTaskId]       = useState(null);
  const [casePath, setCasePath]   = useState(null);
  const esRef = useRef(null);

  useEffect(() => {
    if (params.get('file') && params.get('auto') === '1') startTriage(params.get('file'));
  }, []);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [logs]);

  useEffect(() => { return () => { if (esRef.current) esRef.current.close(); }; }, []);

  const startTriage = async (fname) => {
    const f = fname || filename;
    if (!f) return;
    if (esRef.current) esRef.current.close();
    setLogs([]); setState('running'); setTaskId(null); setCasePath(null);

    const res = await fetch('/api/investigate/evidence', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename: f, case_type: caseType, tlp, analyst }),
    });
    if (!res.ok) {
      setLogs([{ msg: `Error: ${await res.text()}`, level: 'error', ts: new Date().toISOString() }]);
      setState('error'); return;
    }
    const data = await res.json();
    setTaskId(data.task_id);

    const es = new EventSource(`/api/investigate/evidence/${data.task_id}/stream`);
    esRef.current = es;
    es.onmessage = (e) => {
      const entry = JSON.parse(e.data);
      if (entry.type === 'done') {
        setState(entry.status === 'complete' ? 'complete' : 'error');
        if (entry.case_path) setCasePath(entry.case_path);
        es.close(); return;
      }
      setLogs(l => [...l, entry]);
    };
    es.onerror = () => { setState('error'); es.close(); };
  };

  const reset = () => { if (esRef.current) esRef.current.close(); setLogs([]); setState('idle'); setTaskId(null); setCasePath(null); setFilename(''); };

  const statusColor = { idle: C.cyan, running: C.orange, complete: C.green, error: C.red }[state];
  const statusLabel = { idle: 'READY', running: 'TRIAGING...', complete: 'COMPLETE', error: 'ERROR' }[state];

  return (
    <div className="cyber-fade-in" style={{ maxWidth: '1000px', margin: '0 auto' }}>
      <HudFrame title="EVIDENCE TRIAGE" accentColor={C.purple} style={{ marginBottom: '1.5rem' }}>
        <div style={{ padding: '1.25rem', display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
          <Zap size={22} color={C.purple} style={{ flexShrink: 0 }} />
          <div style={{ flex: 1 }}>
            <div style={{ fontFamily: "'Orbitron', monospace", fontSize: '0.7rem', color: C.purple, letterSpacing: '0.1em' }}>PHASE 0 MANDATORY — Skills checked before any investigation</div>
            <div style={{ fontFamily: "'Share Tech Mono', monospace", fontSize: '0.6rem', color: '#553355', marginTop: '0.2rem' }}>Uploads any evidence type → auto-detects file type → matches skills → begins triage</div>
          </div>
          <div style={{ padding: '0.3rem 0.75rem', background: `${statusColor}0d`, border: `1px solid ${statusColor}44`, borderRadius: '0.25rem', fontFamily: "'VT323', monospace", fontSize: '1rem', color: statusColor }}>{statusLabel}</div>
        </div>
      </HudFrame>

      {state === 'idle' && (
        <HudFrame title="EVIDENCE INPUT" accentColor={C.purple} style={{ marginBottom: '1.5rem' }}>
          <div style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: '0.75rem' }}>
              <div>
                <label style={labelStyle}>FILENAME (from upload queue)</label>
                <input value={filename} onChange={e => setFilename(e.target.value)}
                  placeholder="malware.exe / phish.eml / capture.pcap ..."
                  style={inputStyle(C.purple)} />
              </div>
              <div>
                <label style={labelStyle}>CASE TYPE</label>
                <select value={caseType} onChange={e => setCaseType(e.target.value)} style={inputStyle(C.purple)}>
                  {['General','Phishing','Malware','Ransomware','Network','Forensics','Memory Dump','APT','Web Attack','Script'].map(t =>
                    <option key={t} value={t}>{t}</option>
                  )}
                </select>
              </div>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
              <div>
                <label style={labelStyle}>TLP</label>
                <select value={tlp} onChange={e => setTlp(e.target.value)} style={inputStyle(C.purple)}>
                  {['TLP:AMBER','TLP:RED','TLP:GREEN','TLP:WHITE'].map(t => <option key={t}>{t}</option>)}
                </select>
              </div>
              <div>
                <label style={labelStyle}>ANALYST</label>
                <input value={analyst} onChange={e => setAnalyst(e.target.value)} placeholder="Rudra Verma" style={inputStyle(C.purple)} />
              </div>
            </div>
            <button onClick={() => startTriage()} disabled={!filename}
              style={{ padding: '0.75rem 2rem', background: filename ? `${C.purple}1a` : '#111', border: `1px solid ${filename ? C.purple : '#333'}`, borderRadius: '0.5rem', color: filename ? C.purple : '#555', fontFamily: "'Orbitron', monospace", fontSize: '0.7rem', letterSpacing: '0.1em', cursor: filename ? 'pointer' : 'not-allowed' }}>
              <Zap size={14} style={{ marginRight: '0.5rem', verticalAlign: 'middle' }} />START TRIAGE
            </button>
          </div>
        </HudFrame>
      )}

      {(state === 'running' || logs.length > 0) && (
        <HudFrame title={`TRIAGE LOG  [${logs.length} entries]`} accentColor={state === 'complete' ? C.green : state === 'error' ? C.red : C.purple}>
          <div ref={logRef} style={{ padding: '1rem', fontFamily: "'Share Tech Mono', monospace", fontSize: '0.65rem', maxHeight: '520px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '2px' }}>
            {logs.map((entry, i) => {
              if (entry.level === 'sep') return <div key={i} style={{ color: LEVEL_COLOR.sep, borderTop: `1px solid ${LEVEL_COLOR.sep}`, margin: '0.3rem 0', userSelect: 'none' }} />;
              const color = LEVEL_COLOR[entry.level] || C.green;
              return <div key={i} style={{ color, lineHeight: 1.5, whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>{entry.msg}</div>;
            })}
            {state === 'running' && <div style={{ color: C.orange, marginTop: '0.5rem' }}>▌</div>}
          </div>
          {state !== 'running' && (
            <div style={{ padding: '0.75rem 1rem', borderTop: `1px solid #1a1a1a`, display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
              {casePath && <button onClick={() => navigate(`/files/${casePath}`)} style={actionBtn(C.green)}><FolderOpen size={14} /> OPEN CASE</button>}
              <button onClick={reset} style={actionBtn(C.cyan)}>NEW TRIAGE</button>
              {state === 'error' && <button onClick={() => startTriage()} style={actionBtn(C.orange)}><AlertTriangle size={14} /> RETRY</button>}
              {state === 'complete' && (
                <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '0.4rem', color: C.green, fontFamily: "'Share Tech Mono', monospace", fontSize: '0.65rem' }}>
                  <CheckCircle size={14} /> TRIAGE COMPLETE
                </div>
              )}
            </div>
          )}
        </HudFrame>
      )}
    </div>
  );
}

const labelStyle = { display: 'block', fontFamily: "'Share Tech Mono', monospace", fontSize: '0.55rem', color: '#553355', letterSpacing: '0.1em', marginBottom: '0.3rem' };
const inputStyle = (color) => ({ width: '100%', padding: '0.5rem 0.75rem', background: '#050005', border: `1px solid ${color}44`, borderRadius: '0.375rem', color, fontFamily: "'Share Tech Mono', monospace", fontSize: '0.7rem', outline: 'none', boxSizing: 'border-box' });
const actionBtn  = (color) => ({ display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0.4rem 0.9rem', background: `${color}0d`, border: `1px solid ${color}44`, borderRadius: '0.375rem', color, fontFamily: "'Share Tech Mono', monospace", fontSize: '0.6rem', cursor: 'pointer' });
