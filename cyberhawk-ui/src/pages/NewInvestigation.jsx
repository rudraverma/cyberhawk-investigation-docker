import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { HudFrame, C } from '../components/CyberHawkUI';
import { FolderPlus, CheckCircle, AlertTriangle } from 'lucide-react';

const TYPES = ['Phishing', 'Malware', 'OSINT', 'Incident Response', 'Memory Forensics', 'Network Forensics', 'Threat Hunt', 'Other'];
const TLP   = ['TLP:WHITE', 'TLP:GREEN', 'TLP:AMBER', 'TLP:RED'];

export default function NewInvestigation() {
  const navigate = useNavigate();
  const today    = new Date().toISOString().slice(0, 10);

  const [form, setForm] = useState({
    caseName:    '',
    caseType:    'Phishing',
    analyst:     '',
    tlp:         'TLP:AMBER',
    description: '',
    hypothesis:  '',
  });
  const [creating, setCreating] = useState(false);
  const [error,    setError]    = useState(null);

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const slugify = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');

  const create = async () => {
    if (!form.caseName.trim()) { setError('Case name is required'); return; }
    setCreating(true);
    setError(null);

    const slug    = slugify(form.caseName);
    const casePath = `${today}/${slug}`;

    // create the case folder
    const r = await fetch('/api/files/case', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: casePath }),
    });

    if (!r.ok) { setError('Failed to create case folder'); setCreating(false); return; }

    // write initial notes.md
    const notes = buildNotes(form, today, casePath);
    await fetch('/api/files/write', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: `investigations/${casePath}/notes.md`, content: notes }),
    });

    setCreating(false);
    navigate(`/files/investigations/${casePath}`);
  };

  return (
    <div className="cyber-fade-in" style={{ maxWidth: '700px', margin: '0 auto' }}>
      <HudFrame title="NEW INVESTIGATION" accentColor={C.red}>
        <div style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>

          {error && (
            <div style={{ padding: '0.6rem 0.9rem', borderRadius: '0.375rem', background: C.redBg, border: `1px solid ${C.redBdr}`, color: C.red, fontFamily: "'Share Tech Mono', monospace", fontSize: '0.65rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <AlertTriangle size={13} />{error}
            </div>
          )}

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <Field label="CASE NAME *"    value={form.caseName}  onChange={v => set('caseName',  v)} placeholder="e.g. phishing-invoice-may" span />
            <Select label="CASE TYPE"     value={form.caseType}  onChange={v => set('caseType',  v)} options={TYPES} />
            <Select label="TLP"           value={form.tlp}       onChange={v => set('tlp',       v)} options={TLP} />
            <Field label="ANALYST (OPT)"  value={form.analyst}   onChange={v => set('analyst',   v)} placeholder="Your name or handle" span />
            <TextArea label="DESCRIPTION (OPT)"  value={form.description} onChange={v => set('description', v)} placeholder="Brief summary of the case" />
            <TextArea label="INITIAL HYPOTHESIS" value={form.hypothesis}  onChange={v => set('hypothesis',  v)} placeholder="What do you suspect so far?" />
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '0.5rem' }}>
            <button onClick={create} disabled={creating}
              style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.65rem 1.5rem', background: `${C.red}0d`, border: `1px solid ${C.red}44`, borderRadius: '0.5rem', color: C.red, fontFamily: "'Orbitron', monospace", fontSize: '0.65rem', letterSpacing: '0.1em', cursor: creating ? 'not-allowed' : 'pointer', opacity: creating ? 0.6 : 1 }}>
              <FolderPlus size={15} />
              {creating ? 'CREATING...' : 'CREATE INVESTIGATION'}
            </button>
          </div>
        </div>
      </HudFrame>
    </div>
  );
}

function Field({ label, value, onChange, placeholder = '', span = false }) {
  return (
    <div style={{ gridColumn: span ? '1 / -1' : undefined }}>
      <label style={labelStyle}>{label}</label>
      <input value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder} style={inputStyle} />
    </div>
  );
}

function TextArea({ label, value, onChange, placeholder = '' }) {
  return (
    <div>
      <label style={labelStyle}>{label}</label>
      <textarea value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder} rows={3} style={{ ...inputStyle, resize: 'vertical' }} />
    </div>
  );
}

function Select({ label, value, onChange, options }) {
  return (
    <div>
      <label style={labelStyle}>{label}</label>
      <select value={value} onChange={e => onChange(e.target.value)} style={inputStyle}>
        {options.map(o => <option key={o} value={o}>{o}</option>)}
      </select>
    </div>
  );
}

const labelStyle = { display: 'block', fontFamily: "'Share Tech Mono', monospace", fontSize: '0.55rem', color: '#336633', letterSpacing: '0.1em', marginBottom: '0.3rem' };
const inputStyle = { fontFamily: "'Share Tech Mono', monospace", fontSize: '0.65rem', background: '#001100', border: `1px solid ${C.greenBdr}`, color: C.green, padding: '0.4rem 0.6rem', borderRadius: '0.25rem', width: '100%', outline: 'none' };

function buildNotes(form, date, casePath) {
  return `# Investigation Notes — ${form.caseName}

CLASSIFICATION: ${form.tlp} — Do not share outside authorised personnel

## Metadata
| Field | Value |
|---|---|
| Case ID | ${casePath} |
| Date Opened | ${date} |
| Type | ${form.caseType} |
| Analyst | ${form.analyst || 'TBD'} |
| TLP | ${form.tlp} |

## Description
${form.description || '_No description provided_'}

## Initial Hypothesis
${form.hypothesis || '_No hypothesis provided_'}

## Evidence Received
_Record SHA-256 hashes of all uploaded evidence here._

| File | MD5 | SHA-256 |
|---|---|---|
| | | |

## Skills Applied
_List skills invoked during this investigation._

## Key Findings
_Populate as investigation progresses._
`;
}
