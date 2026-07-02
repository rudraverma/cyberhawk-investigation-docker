"""
etherhiding_detector.py — EtherHiding Blockchain C2 Detection
==============================================================
Visits a URL with a real headless browser, hooks window.eval() and
atob() via CDP, monitors network requests and WebSocket frames for
eth_call / blockchain RPC calls. Writes:
  - captured_evals.json   : all eval() / atob() calls captured
  - service_workers.json  : any service worker registrations
  - etherhiding_signal.json : written ONLY if eth_call detected
  - calls EtherHawk webhook if eth_call found

Usage:
    python3 etherhiding_detector.py --url URL --case /path/to/case [--webhook-url URL] [--webhook-secret SECRET]

Exit codes:
    0 = clean (no eth_call detected)
    1 = EtherHiding DETECTED (eth_call found)
    2 = error / browser failure
"""

import argparse
import asyncio
import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

try:
    from playwright.async_api import async_playwright, TimeoutError as PWTimeout
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

try:
    from playwright_stealth import Stealth
    HAS_STEALTH = True
except ImportError:
    HAS_STEALTH = False


EVAL_HOOK_JS = r"""
(function() {
    if (window.__etherhawk_hooked) return;
    window.__etherhawk_hooked = true;
    window.__captured_evals = [];
    window.__captured_sws = [];

    const _orig_eval = window.eval;
    window.eval = function(code) {
        try {
            const entry = {
                type: 'eval',
                code: String(code).substring(0, 4000),
                ts: Date.now(),
                eth_call: String(code).includes('eth_call'),
                has_atob: String(code).includes('atob'),
                has_web3: String(code).toLowerCase().includes('web3'),
                contract_like: /0x[0-9a-fA-F]{40}/.test(String(code))
            };
            window.__captured_evals.push(entry);
        } catch(e) {}
        return _orig_eval.apply(this, arguments);
    };
    Object.defineProperty(window.eval, 'toString', {
        value: function() { return 'function eval() { [native code] }'; }
    });

    const _orig_atob = window.atob;
    window.atob = function(str) {
        const result = _orig_atob.call(this, str);
        try {
            if (result.length > 20) {
                const rs = result.toLowerCase();
                if (rs.includes('eth_call') || rs.includes('web3') || rs.includes('blockchain')
                    || rs.includes('0x') || rs.includes('binance') || rs.includes('bsc')) {
                    window.__captured_evals.push({
                        type: 'atob_suspicious',
                        input_b64_prefix: str.substring(0, 200),
                        decoded_prefix: result.substring(0, 4000),
                        ts: Date.now(),
                        eth_call: rs.includes('eth_call'),
                        has_web3: rs.includes('web3')
                    });
                }
            }
        } catch(e) {}
        return result;
    };

    const _orig_register = navigator.serviceWorker ? navigator.serviceWorker.register.bind(navigator.serviceWorker) : null;
    if (_orig_register) {
        navigator.serviceWorker.register = function(url, options) {
            window.__captured_sws.push({ url: url, ts: Date.now() });
            return _orig_register(url, options);
        };
    }
})();
"""

BLOCKCHAIN_RPC_METHODS = {"eth_call", "eth_blockNumber", "eth_getStorageAt",
                           "eth_getLogs", "eth_chainId", "net_version"}


def _parse_rpc_body(body: str | None) -> list[dict]:
    """Parse a JSON-RPC request body and return any blockchain RPC method calls."""
    if not body:
        return []
    try:
        data = json.loads(body)
        calls = data if isinstance(data, list) else [data]
        return [c for c in calls if isinstance(c, dict) and c.get("method") in BLOCKCHAIN_RPC_METHODS]
    except Exception:
        return []


async def detect(url: str, case_dir: Path, webhook_url: str, webhook_secret: str,
                 timeout: int = 35) -> int:
    if not HAS_PLAYWRIGHT:
        print("[!] playwright not installed — skipping dynamic detection", file=sys.stderr)
        return 2

    eth_calls: list[dict] = []
    service_workers: list[str] = []
    captured_evals: list[dict] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            proxy={"server": os.getenv("MITM_PROXY", "http://ch-ether-proxy:8095")},
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--window-size=1920,1080",
                "--lang=en-US",
            ],
        )

        ctx_opts = dict(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            timezone_id="America/New_York",
        )
        ctx_opts["ignore_https_errors"] = True
        context = await browser.new_context(**ctx_opts)

        if HAS_STEALTH:
            try:
                stealth = Stealth()
                await stealth.apply_stealth_async(context)
            except Exception:
                pass

        # Inject eval hook on every navigation
        await context.add_init_script(EVAL_HOOK_JS)

        page = await context.new_page()

        # Monitor ALL POST requests for blockchain RPC methods (eth_call etc.)
        # Not filtered by known RPC host — catches any unknown/custom RPC provider
        def on_request(req):
            if req.method == "POST":
                calls = _parse_rpc_body(req.post_data)
                for c in calls:
                    eth_calls.append({
                        "url": req.url, "method": c.get("method"),
                        "params": c.get("params", [])[:2],
                        "transport": "http", "ts": time.time(),
                    })

        page.on("request", on_request)

        # Monitor WebSocket frames for JSON-RPC
        def on_websocket(ws):
            def on_frame(frame):
                try:
                    calls = _parse_rpc_body(frame.payload)
                    for c in calls:
                        eth_calls.append({
                            "url": ws.url, "method": c.get("method"),
                            "params": c.get("params", [])[:2],
                            "transport": "websocket", "ts": time.time(),
                        })
                except Exception:
                    pass
            ws.on("framesent", on_frame)

        page.on("websocket", on_websocket)

        try:
            await page.goto(url, wait_until="networkidle", timeout=timeout * 1000)
        except PWTimeout:
            pass
        except Exception as e:
            print(f"[!] page.goto error: {e}", file=sys.stderr)

        # Give deferred scripts and async fetch() calls time to execute
        try:
            await asyncio.sleep(5)
        except Exception:
            pass

        # Extract captured evals and service workers from page
        try:
            captured_evals = await page.evaluate("window.__captured_evals || []")
        except Exception:
            pass

        try:
            sws = await page.evaluate("window.__captured_sws || []")
            service_workers = [s.get("url", "") for s in sws if s.get("url")]
        except Exception:
            pass

        await browser.close()

    # Write evidence
    case_dir.mkdir(parents=True, exist_ok=True)

    (case_dir / "captured_evals.json").write_text(json.dumps({
        "captured_at": datetime.now().isoformat(),
        "url": url,
        "evals": captured_evals,
        "eth_call_count": len(eth_calls),
    }, indent=2))

    if service_workers:
        (case_dir / "service_workers.json").write_text(json.dumps({
            "urls": service_workers, "count": len(service_workers)
        }, indent=2))

    # eth_call detected?
    detected = bool(eth_calls) or any(
        e.get("eth_call") or e.get("has_web3")
        for e in captured_evals
    )

    if detected:
        signal = {
            "url": url,
            "case_id": case_dir.name,
            "case_path": str(case_dir),
            "eth_calls": eth_calls[:5],
            "suspicious_evals": [e for e in captured_evals if e.get("eth_call") or e.get("has_web3")][:3],
            "service_workers": service_workers,
            "detected_at": datetime.now().isoformat(),
        }

        # Try to find contract from eth_call params
        for call in eth_calls:
            params = call.get("params", [])
            if params and isinstance(params[0], dict):
                contract = params[0].get("to", "")
                if contract:
                    signal["contract"] = contract
                    signal["rpc_url"] = call.get("url", "")
                    break

        (case_dir / "etherhiding_signal.json").write_text(json.dumps(signal, indent=2))
        print(f"[!] ETHERHIDING DETECTED — eth_call captured ({len(eth_calls)} RPC call(s))")

        # POST to EtherHawk webhook
        if webhook_url:
            try:
                payload = json.dumps(signal).encode()
                req = urllib.request.Request(
                    webhook_url,
                    data=payload,
                    headers={
                        "Content-Type": "application/json",
                        "X-EtherHawk-Secret": webhook_secret or "",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    body = resp.read().decode()
                    print(f"[+] EtherHawk webhook: {body}")
            except Exception as e:
                print(f"[!] webhook failed: {e}", file=sys.stderr)

        return 1

    print(f"[+] No EtherHiding indicators detected  (evals: {len(captured_evals)}, rpc: {len(eth_calls)})")
    return 0


def main():
    parser = argparse.ArgumentParser(description="EtherHiding dynamic detector")
    parser.add_argument("--url", required=True)
    parser.add_argument("--case", required=True, help="Case output directory")
    parser.add_argument("--webhook-url", default="http://localhost:8094/webhook/etherhiding-confirmed")
    parser.add_argument("--webhook-secret", default=os.getenv("ETHERHAWK_WEBHOOK_SECRET", ""))
    parser.add_argument("--timeout", type=int, default=35)
    args = parser.parse_args()

    exit_code = asyncio.run(
        detect(
            url=args.url,
            case_dir=Path(args.case),
            webhook_url=args.webhook_url,
            webhook_secret=args.webhook_secret,
            timeout=args.timeout,
        )
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
