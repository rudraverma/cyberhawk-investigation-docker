import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { HudFrame, C } from '../components/CyberHawkUI';
import { Folder, FileText, Download, ChevronRight, Home, Eye } from 'lucide-react';

export default function FileBrowser() {
  const params  = useParams();
  const navigate = useNavigate();
  const subPath  = params['*'] || '';

  const [entries, setEntries] = useState([]);
  const [error,   setError]   = useState(null);

  useEffect(() => {
    fetch(`/api/files/tree?path=${encodeURIComponent(subPath || 'investigations')}`)
      .then(r => r.json())
      .then(data => { setEntries(data); setError(null); })
      .catch(() => setError('Failed to load directory'));
  }, [subPath]);

  const navigate_ = (entry) => {
    if (entry.type === 'directory') navigate(`/files/${entry.path}`);
    else navigate(`/view?path=${encodeURIComponent(entry.path)}`);
  };

  const crumbs = buildCrumbs(subPath || 'investigations');

  return (
    <div className="cyber-fade-in" style={{ maxWidth: '900px', margin: '0 auto' }}>

      {/* Breadcrumb */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', marginBottom: '1rem', flexWrap: 'wrap' }}>
        <button onClick={() => navigate('/files')} style={crumbBtn}><Home size={12} /></button>
        {crumbs.map((c, i) => (
          <span key={c.path} style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
            <ChevronRight size={10} color="#224422" />
            <button onClick={() => navigate(`/files/${c.path}`)} style={{ ...crumbBtn, color: i === crumbs.length - 1 ? C.green : '#336633' }}>
              {c.label}
            </button>
          </span>
        ))}
      </div>

      <HudFrame title={`FILES  /${subPath || 'investigations'}`} accentColor={C.green}>
        <div style={{ padding: '1rem' }}>
          {error && (
            <p style={{ fontFamily: "'Share Tech Mono', monospace", fontSize: '0.65rem', color: C.red, textAlign: 'center', padding: '1rem 0' }}>{error}</p>
          )}
          {!error && entries.length === 0 && (
            <p style={{ fontFamily: "'Share Tech Mono', monospace", fontSize: '0.65rem', color: '#224422', textAlign: 'center', padding: '2rem 0' }}>
              DIRECTORY EMPTY
            </p>
          )}
          {entries.map(entry => (
            <div key={entry.path}
              style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', padding: '0.45rem 0.6rem', borderRadius: '0.375rem', cursor: 'pointer', marginBottom: '0.2rem', border: '1px solid transparent', transition: 'all 0.1s' }}
              onClick={() => navigate_(entry)}
              onMouseOver={e => { e.currentTarget.style.background = C.greenBg; e.currentTarget.style.borderColor = C.greenBdr; }}
              onMouseOut={e =>  { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.borderColor = 'transparent'; }}>
              {entry.type === 'directory'
                ? <Folder size={16} color={C.gold} style={{ flexShrink: 0 }} />
                : <FileText size={16} color={C.green} style={{ flexShrink: 0 }} />}
              <span style={{ fontFamily: "'Share Tech Mono', monospace", fontSize: '0.7rem', color: entry.type === 'directory' ? C.gold : C.green, flex: 1 }}>
                {entry.name}
              </span>
              {entry.size && (
                <span style={{ fontFamily: "'Share Tech Mono', monospace", fontSize: '0.55rem', color: '#224422' }}>{entry.size}</span>
              )}
              {entry.modified && (
                <span style={{ fontFamily: "'Share Tech Mono', monospace", fontSize: '0.55rem', color: '#224422', marginLeft: '0.5rem' }}>{entry.modified}</span>
              )}
              {entry.type === 'file' && (
                <span style={{ display: 'flex', gap: '0.3rem' }}>
                  <button onClick={e => { e.stopPropagation(); navigate(`/view?path=${encodeURIComponent(entry.path)}`); }}
                    style={{ padding: '0.2rem 0.4rem', background: `${C.cyan}0d`, border: `1px solid ${C.cyan}33`, borderRadius: '0.2rem', color: C.cyan, cursor: 'pointer', display: 'flex', alignItems: 'center' }}>
                    <Eye size={11} />
                  </button>
                  <a href={`/api/files/download?path=${encodeURIComponent(entry.path)}`} download onClick={e => e.stopPropagation()}
                    style={{ padding: '0.2rem 0.4rem', background: `${C.orange}0d`, border: `1px solid ${C.orange}33`, borderRadius: '0.2rem', color: C.orange, display: 'flex', alignItems: 'center', textDecoration: 'none' }}>
                    <Download size={11} />
                  </a>
                </span>
              )}
            </div>
          ))}
        </div>
      </HudFrame>
    </div>
  );
}

function buildCrumbs(path) {
  const parts = path.split('/').filter(Boolean);
  return parts.map((p, i) => ({ label: p, path: parts.slice(0, i + 1).join('/') }));
}

const crumbBtn = {
  background: 'transparent', border: 'none', cursor: 'pointer',
  fontFamily: "'Share Tech Mono', monospace", fontSize: '0.65rem',
  color: '#336633', display: 'flex', alignItems: 'center', padding: '0.1rem 0.2rem',
};
