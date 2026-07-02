import { C } from '../components/CyberHawkUI';

export default function MitmPage() {
  return (
    <div style={{ height: 'calc(100vh - 120px)', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
      <div style={{ color: C.green, fontFamily: 'Share Tech Mono', fontSize: '0.7rem', letterSpacing: '0.05em' }}>
        ◈ MITMPROXY LIVE — all investigation traffic is intercepted and displayed below
      </div>
      <iframe
        src={import.meta.env.VITE_MITM_URL || ""}
        style={{
          flex: 1,
          border: '1px solid #1a3a1a',
          borderRadius: '4px',
          background: '#000',
          width: '100%',
        }}
        title="mitmweb"
        allow="same-origin"
      />
    </div>
  );
}
