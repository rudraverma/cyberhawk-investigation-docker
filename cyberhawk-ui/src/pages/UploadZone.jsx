import { useCallback, useEffect, useState } from 'react';
import { useDropzone } from 'react-dropzone';
import { useNavigate } from 'react-router-dom';
import { HudFrame, C } from '../components/CyberHawkUI';
import { Upload, FileText, Hash, Trash2, FolderPlus, CheckCircle, AlertTriangle } from 'lucide-react';

export default function UploadZone() {
  const navigate = useNavigate();
  const [uploads, setUploads]   = useState([]);
  const [cases, setCases]       = useState([]);
  const [uploading, setUploading] = useState(false);
  const [msg, setMsg]           = useState(null);
  const [selected, setSelected] = useState({});
  const [targetCase, setTargetCase] = useState('');

  const load = () => {
    fetch('/api/files/upload').then(r => r.json()).then(setUploads).catch(() => {});
    fetch('/api/files/cases').then(r => r.json()).then(setCases).catch(() => {});
  };
  useEffect(load, []);

  const flash = (text, ok = true) => {
    setMsg({ text, ok });
    setTimeout(() => setMsg(null), 4000);
  };

  const onDrop = useCallback(async (accepted) => {
    if (!accepted.length) return;
    setUploading(true);
    for (const file of accepted) {
      const fd = new FormData();
      fd.append('file', file);
      await fetch('/api/files/upload', { method: 'POST', body: fd }).catch(() => {});
    }
    setUploading(false);
    load();
    flash(`${accepted.length} file(s) uploaded`);
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({ onDrop });

  const deleteFile = async (name) => {
    await fetch('/api/files/delete', { method: 'DELETE', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path: `upload/${name}` }) });
    load();
  };

  const assignToCase = async () => {
    const names = Object.keys(selected).filter(k => selected[k]);
    if (!names.length || !targetCase) { flash('Select files and a case first', false); return; }
    for (const name of names) {
      const fd = new FormData();
      await fetch(`/api/files/move`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ src: `upload/${name}`, dst: `investigations/${targetCase}/${name}` }),
      }).catch(() => {});
    }
    setSelected({});
    load();
    flash(`Moved ${names.length} file(s) to ${targetCase}`);
  };

  const toggleAll = (val) => {
    const next = {};
    uploads.forEach(u => { next[u.name] = val; });
    setSelected(next);
  };

  return (
    <div className="cyber-fade-in" style={{ maxWidth: '900px', margin: '0 auto' }}>

      {msg && (
        <div className="cyber-fade-in" style={{ marginBottom: '1rem', padding: '0.65rem 1rem', borderRadius: '0.5rem', background: msg.ok ? C.greenBg : C.redBg, border: `1px solid ${msg.ok ? C.greenBdr : C.redBdr}`, color: msg.ok ? C.green : C.red, fontFamily: "'Share Tech Mono', monospace", fontSize: '0.7rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          {msg.ok ? <CheckCircle size={14} /> : <AlertTriangle size={14} />}
          {msg.text}
        </div>
      )}

      {/* Drop zone */}
      <HudFrame title="EVIDENCE DROP ZONE" accentColor={C.orange} style={{ marginBottom: '1.5rem' }}>
        <div {...getRootProps()} style={{ margin: '1rem', padding: '2.5rem', border: `2px dashed ${isDragActive ? C.orange : C.orangeBdr}`, borderRadius: '0.75rem', textAlign: 'center', cursor: 'pointer', background: isDragActive ? C.orangeBg : 'transparent', transition: 'all 0.2s' }}>
          <input {...getInputProps()} />
          <Upload size={36} color={C.orange} style={{ marginBottom: '0.75rem', opacity: 0.7 }} />
          <div style={{ fontFamily: "'Orbitron', monospace", fontSize: '0.75rem', color: C.orange, letterSpacing: '0.1em', marginBottom: '0.4rem' }}>
            {uploading ? 'UPLOADING...' : isDragActive ? 'DROP NOW' : 'DROP EVIDENCE HERE'}
          </div>
          <div style={{ fontFamily: "'Share Tech Mono', monospace", fontSize: '0.6rem', color: '#664422' }}>
            Emails · Office docs · Executables · PCAPs · Memory dumps
          </div>
        </div>
      </HudFrame>

      {/* File list */}
      <HudFrame title={`UPLOAD QUEUE  [${uploads.length}]`} accentColor={C.orange}>
        <div style={{ padding: '1rem' }}>
          {uploads.length === 0 ? (
            <p style={{ fontFamily: "'Share Tech Mono', monospace", fontSize: '0.65rem', color: '#664422', textAlign: 'center', padding: '2rem 0' }}>
              QUEUE EMPTY — DROP FILES ABOVE
            </p>
          ) : (
            <>
              {/* Toolbar */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.75rem', flexWrap: 'wrap' }}>
                <button onClick={() => toggleAll(true)} style={smallBtn(C.cyan)}>SELECT ALL</button>
                <button onClick={() => toggleAll(false)} style={smallBtn(C.cyan)}>NONE</button>
                <select value={targetCase} onChange={e => setTargetCase(e.target.value)}
                  style={{ fontFamily: "'Share Tech Mono', monospace", fontSize: '0.6rem', background: '#001100', border: `1px solid ${C.greenBdr}`, color: C.green, padding: '0.3rem 0.5rem', borderRadius: '0.25rem', flex: 1, minWidth: '160px' }}>
                  <option value="">— SELECT CASE —</option>
                  {cases.map(c => <option key={c.path} value={c.path}>{c.name}</option>)}
                </select>
                <button onClick={assignToCase} style={smallBtn(C.green)}>
                  <FolderPlus size={12} /> ASSIGN
                </button>
              </div>

              {/* Files */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                {uploads.map(u => (
                  <div key={u.name} style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', padding: '0.5rem 0.75rem', background: selected[u.name] ? C.orangeBg : '#0a0800', border: `1px solid ${selected[u.name] ? C.orangeBdr : '#331100'}`, borderRadius: '0.375rem' }}>
                    <input type="checkbox" checked={!!selected[u.name]} onChange={e => setSelected(s => ({ ...s, [u.name]: e.target.checked }))}
                      style={{ accentColor: C.orange, cursor: 'pointer' }} />
                    <FileText size={14} color={C.orange} style={{ flexShrink: 0 }} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontFamily: "'Share Tech Mono', monospace", fontSize: '0.7rem', color: C.orange, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{u.name}</div>
                      <div style={{ fontFamily: "'Share Tech Mono', monospace", fontSize: '0.55rem', color: '#664422' }}>{u.size} · {u.modified}</div>
                    </div>
                    <button onClick={() => navigate(`/files/upload/${u.name}`)} style={iconBtn(C.cyan)} title="View"><Hash size={12} /></button>
                    <button onClick={() => deleteFile(u.name)} style={iconBtn(C.red)} title="Delete"><Trash2 size={12} /></button>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </HudFrame>
    </div>
  );
}

const smallBtn = (color) => ({
  display: 'flex', alignItems: 'center', gap: '0.3rem',
  padding: '0.3rem 0.6rem', background: `${color}0d`,
  border: `1px solid ${color}33`, borderRadius: '0.25rem',
  color, fontFamily: "'Share Tech Mono', monospace",
  fontSize: '0.6rem', cursor: 'pointer', whiteSpace: 'nowrap',
});

const iconBtn = (color) => ({
  padding: '0.25rem', background: 'transparent',
  border: `1px solid ${color}33`, borderRadius: '0.25rem',
  color, cursor: 'pointer', display: 'flex', alignItems: 'center',
});
