import { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import { HudFrame, C } from '../components/CyberHawkUI';
import { Download, ArrowLeft, FileText, Hash } from 'lucide-react';

export default function ReportViewer() {
  const { search } = useLocation();
  const navigate   = useNavigate();
  const path       = new URLSearchParams(search).get('path') || '';

  const [content, setContent] = useState(null);
  const [mode,    setMode]    = useState('rendered'); // rendered | raw | hex
  const [error,   setError]   = useState(null);

  useEffect(() => {
    if (!path) return;
    fetch(`/api/files/read?path=${encodeURIComponent(path)}`)
      .then(r => { if (!r.ok) throw new Error('Not found'); return r.text(); })
      .then(setContent)
      .catch(() => setError('Could not load file'));
  }, [path]);

  const isMd   = path.endsWith('.md');
  const isText = /\.(txt|csv|json|yaml|yml|log|sh|py|js|ts|html|xml|yar|sigma|conf|ini)$/i.test(path);

  const filename = path.split('/').pop();

  return (
    <div className="cyber-fade-in" style={{ maxWidth: '960px', margin: '0 auto' }}>

      {/* Toolbar */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1rem', flexWrap: 'wrap' }}>
        <button onClick={() => navigate(-1)} style={tb(C.cyan)}><ArrowLeft size={13} /> BACK</button>
        <span style={{ fontFamily: "'Share Tech Mono', monospace", fontSize: '0.65rem', color: '#336633', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{path}</span>
        {isMd && (
          <>
            <button onClick={() => setMode('rendered')} style={tb(mode === 'rendered' ? C.green : '#336633')}>RENDERED</button>
            <button onClick={() => setMode('raw')}      style={tb(mode === 'raw'      ? C.green : '#336633')}>RAW</button>
          </>
        )}
        {!isMd && isText && (
          <>
            <button onClick={() => setMode('rendered')} style={tb(mode === 'rendered' ? C.green : '#336633')}><FileText size={12} /> TEXT</button>
            <button onClick={() => setMode('hex')}      style={tb(mode === 'hex'      ? C.orange : '#336633')}><Hash size={12} /> HEX</button>
          </>
        )}
        <a href={`/api/files/download?path=${encodeURIComponent(path)}`} download={filename}
          style={{ ...tb(C.orange), textDecoration: 'none' }}>
          <Download size={12} /> DOWNLOAD
        </a>
      </div>

      <HudFrame title={filename} accentColor={C.green}>
        <div style={{ padding: '1rem' }}>
          {error && (
            <p style={{ fontFamily: "'Share Tech Mono', monospace", fontSize: '0.7rem', color: C.red, textAlign: 'center', padding: '2rem' }}>{error}</p>
          )}
          {!error && content === null && (
            <p style={{ fontFamily: "'Share Tech Mono', monospace", fontSize: '0.7rem', color: '#224422', textAlign: 'center', padding: '2rem' }}>LOADING...</p>
          )}
          {content !== null && !error && (
            <>
              {isMd && mode === 'rendered' && (
                <div className="md-body">
                  <ReactMarkdown>{content}</ReactMarkdown>
                </div>
              )}
              {(mode === 'raw' || (!isMd && isText && mode === 'rendered')) && (
                <pre style={{ fontFamily: "'Share Tech Mono', monospace", fontSize: '0.65rem', color: C.green, overflowX: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-all', lineHeight: 1.6, margin: 0 }}>
                  {content}
                </pre>
              )}
              {mode === 'hex' && (
                <HexDump data={content} />
              )}
              {!isMd && !isText && (
                <div style={{ fontFamily: "'Share Tech Mono', monospace", fontSize: '0.7rem', color: C.orange, textAlign: 'center', padding: '2rem' }}>
                  BINARY FILE — DOWNLOAD TO ANALYSE
                </div>
              )}
            </>
          )}
        </div>
      </HudFrame>

      <style>{`
        .md-body { font-family: 'Share Tech Mono', monospace; font-size: 0.72rem; color: ${C.green}; line-height: 1.8; }
        .md-body h1,.md-body h2,.md-body h3 { font-family: 'Orbitron', monospace; color: ${C.gold}; margin: 1rem 0 0.5rem; letter-spacing: 0.05em; }
        .md-body h1 { font-size: 1rem; } .md-body h2 { font-size: 0.85rem; } .md-body h3 { font-size: 0.75rem; }
        .md-body p  { margin-bottom: 0.6rem; }
        .md-body a  { color: ${C.cyan}; }
        .md-body code { background: #001a00; padding: 0.1em 0.3em; border-radius: 0.2em; font-size: 0.9em; color: ${C.cyan}; }
        .md-body pre  { background: #000d00; border: 1px solid ${C.greenBdr}; border-radius: 0.375rem; padding: 0.75rem; overflow-x: auto; margin: 0.75rem 0; }
        .md-body pre code { background: transparent; padding: 0; }
        .md-body table { border-collapse: collapse; width: 100%; margin: 0.75rem 0; }
        .md-body th { background: ${C.greenBg}; border: 1px solid ${C.greenBdr}; padding: 0.3rem 0.6rem; color: ${C.gold}; }
        .md-body td { border: 1px solid #112211; padding: 0.3rem 0.6rem; }
        .md-body blockquote { border-left: 3px solid ${C.gold}; padding-left: 0.75rem; color: #669966; margin: 0.5rem 0; }
        .md-body ul,.md-body ol { padding-left: 1.5rem; margin-bottom: 0.6rem; }
        .md-body hr { border: none; border-top: 1px solid ${C.greenBdr}; margin: 1rem 0; }
      `}</style>
    </div>
  );
}

function HexDump({ data }) {
  const bytes  = new TextEncoder().encode(data.slice(0, 4096));
  const lines  = [];
  for (let i = 0; i < bytes.length; i += 16) {
    const chunk = bytes.slice(i, i + 16);
    const hex   = Array.from(chunk).map(b => b.toString(16).padStart(2, '0')).join(' ');
    const ascii = Array.from(chunk).map(b => (b >= 0x20 && b < 0x7f) ? String.fromCharCode(b) : '.').join('');
    lines.push(`${i.toString(16).padStart(8, '0')}  ${hex.padEnd(47)}  |${ascii}|`);
  }
  return (
    <pre style={{ fontFamily: "'Share Tech Mono', monospace", fontSize: '0.6rem', color: C.cyan, overflowX: 'auto', margin: 0, lineHeight: 1.7 }}>
      {lines.join('\n')}
      {data.length > 4096 && `\n... (truncated at 4 KB)`}
    </pre>
  );
}

const tb = (color) => ({
  display: 'flex', alignItems: 'center', gap: '0.3rem',
  padding: '0.3rem 0.65rem', background: `${color}0d`,
  border: `1px solid ${color}33`, borderRadius: '0.25rem',
  color, fontFamily: "'Share Tech Mono', monospace", fontSize: '0.6rem', cursor: 'pointer',
});
