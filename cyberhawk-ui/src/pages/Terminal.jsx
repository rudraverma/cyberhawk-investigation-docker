import { useEffect, useRef, useState } from 'react';
import { Terminal as XTerm } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import { WebLinksAddon } from '@xterm/addon-web-links';
import { HudFrame, C } from '../components/CyberHawkUI';
import { Terminal as TermIcon, Power, Maximize2 } from 'lucide-react';
import '@xterm/xterm/css/xterm.css';

export default function TerminalPage() {
  const containerRef = useRef(null);
  const termRef      = useRef(null);
  const wsRef        = useRef(null);
  const fitRef       = useRef(null);
  const [connected, setConnected] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);

  useEffect(() => {
    const term = new XTerm({
      theme: {
        background: '#000000',
        foreground: C.green,
        cursor:     C.green,
        selectionBackground: `${C.green}44`,
        black:      '#000000',
        green:      C.green,
        brightGreen: C.green,
        cyan:       C.cyan,
        brightCyan: C.cyan,
        red:        C.red,
        yellow:     C.gold,
      },
      fontFamily: "'Share Tech Mono', 'Courier New', monospace",
      fontSize:    14,
      lineHeight:  1.2,
      cursorBlink: true,
      scrollback:  5000,
    });

    const fit   = new FitAddon();
    const links = new WebLinksAddon();
    term.loadAddon(fit);
    term.loadAddon(links);
    term.open(containerRef.current);
    fit.fit();
    termRef.current = term;
    fitRef.current  = fit;

    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const ws    = new WebSocket(`${proto}://${window.location.host}/api/terminal/ws`);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      ws.send(JSON.stringify({ type: 'resize', cols: term.cols, rows: term.rows }));
    };
    ws.onmessage = (e) => {
      if (typeof e.data === 'string') term.write(e.data);
    };
    ws.onclose = () => {
      setConnected(false);
      term.write('\r\n\x1b[31m[DISCONNECTED]\x1b[0m\r\n');
    };
    ws.onerror = () => {
      term.write('\r\n\x1b[31m[CONNECTION ERROR]\x1b[0m\r\n');
    };

    term.onData((data) => {
      if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'input', data }));
    });

    const ro = new ResizeObserver(() => {
      try { fit.fit(); } catch {}
      if (ws.readyState === WebSocket.OPEN)
        ws.send(JSON.stringify({ type: 'resize', cols: term.cols, rows: term.rows }));
    });
    ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      ws.close();
      term.dispose();
    };
  }, []);

  const reconnect = () => {
    wsRef.current?.close();
    termRef.current?.clear();
  };

  const toggleFullscreen = () => setFullscreen(f => !f);

  return (
    <div className="cyber-fade-in" style={fullscreen ? fullscreenStyle : { maxWidth: '1100px', margin: '0 auto' }}>
      <HudFrame
        title={<span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}><TermIcon size={13} /> TERMINAL</span>}
        accentColor={C.cyan}
      >
        {/* Toolbar */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.5rem 1rem', borderBottom: `1px solid ${C.border}` }}>
          <span className={connected ? 'cyber-blink' : undefined} style={{ width: '8px', height: '8px', borderRadius: '50%', background: connected ? C.green : C.red, display: 'inline-block', boxShadow: connected ? `0 0 6px ${C.green}` : 'none' }} />
          <span style={{ fontFamily: "'Share Tech Mono', monospace", fontSize: '0.6rem', color: connected ? C.green : C.red }}>
            {connected ? 'CONNECTED' : 'DISCONNECTED'}
          </span>
          <span style={{ flex: 1 }} />
          <button onClick={reconnect} style={tbBtn(C.orange)} title="Reconnect"><Power size={12} /> RECONNECT</button>
          <button onClick={toggleFullscreen} style={tbBtn(C.cyan)} title="Fullscreen"><Maximize2 size={12} /></button>
        </div>

        <div ref={containerRef} style={{ height: fullscreen ? 'calc(100vh - 120px)' : '500px', padding: '0.25rem' }} />
      </HudFrame>
    </div>
  );
}

const fullscreenStyle = {
  position: 'fixed', inset: 0, zIndex: 9999,
  background: '#000', display: 'flex', flexDirection: 'column',
};

const tbBtn = (color) => ({
  display: 'flex', alignItems: 'center', gap: '0.3rem',
  padding: '0.2rem 0.5rem', background: `${color}0d`,
  border: `1px solid ${color}33`, borderRadius: '0.2rem',
  color, fontFamily: "'Share Tech Mono', monospace", fontSize: '0.6rem', cursor: 'pointer',
});
