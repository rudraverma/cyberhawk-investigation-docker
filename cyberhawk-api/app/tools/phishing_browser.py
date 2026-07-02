"""
phishing_browser.py — CyberHawk Headless Browser Investigation Tool
====================================================================
Bypasses bot-detection fingerprint gates using real headless Chromium.
Captures redirect chain, DOM, JS, HAR, screenshots. Can fill forms
(fake email, password, device codes) and follow full attack flow.

Usage:
    python3 /app/app/tools/phishing_browser.py --url "https://target.com" [options]

Options:
    --url URL               Target URL (required)
    --case PATH             Output dir  (default: /workspace/browser_out/)
    --fill-email EMAIL      Fake email for login forms
    --fill-password PASS    Fake password (default: Fake@Pass123!)
    --fill-code CODE        Fake device code (e.g. ABCD-1234)
    --interact              Auto-fill + submit detected forms
    --timeout SECS          Per-page timeout  (default: 30)
    --screenshot            Save PNG at each step
    --har                   Save full HAR network log
    --user-agent UA         Override User-Agent
    --timezone TZ           Browser timezone (default: America/New_York)
    --locale LOCALE         Browser locale   (default: en-US)
    --no-stealth            Disable stealth patches
    --proxy PROXY           HTTP proxy / SOCKS5  (e.g. socks5://127.0.0.1:9050)
"""

import asyncio, argparse, json, os, re, sys
from datetime import datetime
from pathlib import Path

# ── Availability checks ──────────────────────────────────────────────────────
try:
    from playwright.async_api import async_playwright, TimeoutError as PWTimeout
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

try:
    from playwright_stealth import Stealth          # playwright-stealth >= 2.x API
    HAS_STEALTH = True
except ImportError:
    HAS_STEALTH = False

# ── Defaults ──────────────────────────────────────────────────────────────────
DEFAULT_EMAIL    = "john.smith@outlook.com"
DEFAULT_PASSWORD = "Fake@Pass123!"
DEFAULT_CODE     = "ABCD-1234"

STEALTH_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/133.0.0.0 Safari/537.36 Edg/133.0.0.0"
)

CHROMIUM_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-blink-features=AutomationControlled",
    "--disable-infobars",
    "--window-size=1920,1080",
    "--enable-webgl",
    "--use-angle=swiftshader",          # software WebGL — spoofed below
    "--enable-features=NetworkService",
    "--allow-running-insecure-content",
    "--disable-extensions",
    "--lang=en-US",
]

# Injected before any page JS runs — spoof GPU fingerprint + remove webdriver
WEBGL_SPOOF_JS = """
(function() {
  // Spoof WebGL GPU strings — SwiftShader renderer is an instant bot signal
  const _wp = WebGLRenderingContext.prototype.getParameter;
  WebGLRenderingContext.prototype.getParameter = function(p) {
    if (p === 37445) return 'Google Inc. (NVIDIA Corporation)';
    if (p === 37446) return 'ANGLE (NVIDIA, NVIDIA GeForce RTX 3070 Direct3D11 vs_5_0 ps_5_0, D3D11)';
    return _wp.call(this, p);
  };
  const _wp2 = WebGL2RenderingContext.prototype.getParameter;
  WebGL2RenderingContext.prototype.getParameter = function(p) {
    if (p === 37445) return 'Google Inc. (NVIDIA Corporation)';
    if (p === 37446) return 'ANGLE (NVIDIA, NVIDIA GeForce RTX 3070 Direct3D11 vs_5_0 ps_5_0, D3D11)';
    return _wp2.call(this, p);
  };
  // Remove automation flag
  Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
  // Realistic browser plugins (headless has none by default)
  Object.defineProperty(navigator, 'plugins', {
    get: () => ({
      length: 3,
      0: { name: 'PDF Viewer' },
      1: { name: 'Chrome PDF Viewer' },
      2: { name: 'Chromium PDF Viewer' }
    })
  });
})();
"""

# Prefer the full Chromium binary — headless-shell is trivially fingerprinted
# Discover path dynamically so it survives Playwright version bumps
import glob as _glob
_candidates = (
    sorted(_glob.glob("/ms-playwright/chromium-*/chrome-linux64/chrome")) +
    sorted(_glob.glob("/root/.cache/ms-playwright/chromium-*/chrome-linux64/chrome"))
)
_FULL_CHROME = _candidates[-1] if _candidates else ""


class PhishingBrowser:
    def __init__(self, args):
        self.args      = args
        self.out       = Path(args.case)
        self.out.mkdir(parents=True, exist_ok=True)
        self.ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.step      = 0
        self.findings  = {
            "url": args.url, "timestamp": self.ts,
            "redirects": [], "pages": [], "network": [],
            "iocs": [], "forms": [], "js_blocks": [],
            "device_code": None, "oauth_urls": [],
            "api_endpoints": [], "screenshots": [],
        }

    # ── Network hooks ────────────────────────────────────────────────────────
    def _on_request(self, req):
        e = {
            "type": "request", "url": req.url,
            "method": req.method, "post": req.post_data,
            "time": datetime.now().isoformat()
        }
        self.findings["network"].append(e)
        u = req.url.lower()
        if any(x in u for x in ["deviceauth", "device_code", "oauth2", "/token", "/authorize"]):
            self.findings["oauth_urls"].append(req.url)
        if any(x in u for x in ["/api/", "/health", "/generate", "/status", "/poll"]):
            self.findings["api_endpoints"].append(req.url)

    def _on_response(self, resp):
        self.findings["network"].append({
            "type": "response", "url": resp.url, "status": resp.status,
            "headers": dict(resp.headers), "time": datetime.now().isoformat()
        })
        if resp.status in (301, 302, 303, 307, 308):
            self.findings["redirects"].append({
                "from": resp.url,
                "to": resp.headers.get("location", ""),
                "status": resp.status
            })

    # ── Screenshot ───────────────────────────────────────────────────────────
    async def _shot(self, page, label):
        if not self.args.screenshot:
            return
        p = self.out / f"screen_{self.ts}_{self.step:02d}_{label}.png"
        try:
            await page.screenshot(path=str(p), full_page=True)
            self.findings["screenshots"].append(str(p))
            print(f"  [screenshot] {p.name}")
        except Exception as ex:
            print(f"  [screenshot] failed: {ex}")

    # ── Extract intel from page ───────────────────────────────────────────────
    async def _extract(self, page, url):
        html = await page.content()
        hp   = self.out / f"page_{self.ts}_{self.step:02d}.html"
        hp.write_text(html, encoding="utf-8")

        # JS blocks
        for i, m in enumerate(re.finditer(r'<script[^>]*>([\s\S]*?)</script>', html, re.I)):
            b = m.group(1).strip()
            if len(b) > 20:
                self.findings["js_blocks"].append({"page": url, "i": i, "js": b[:3000]})

        # Device code / SID patterns
        for pat in [
            r'(?:user_code|userCode)["\s:=]+([A-Z0-9]{4}-[A-Z0-9]{4})',
            r'id=["\']userCode["\'][^>]*>([A-Z0-9-]+)<',
            r'(?:const|var|let)\s+SID\s*=\s*["\']?(\d{10,})',
        ]:
            m = re.search(pat, html)
            if m:
                self.findings["device_code"] = m.group(1)
                print(f"\n  [!!!] DEVICE CODE / SID FOUND: {m.group(1)}")

        # OAuth / Microsoft URLs
        for u in re.findall(r'https?://[^\s"\'<>]+', html):
            if any(x in u.lower() for x in ["deviceauth", "oauth", "login.microsoft", "/api/"]):
                self.findings["oauth_urls"].append(u)
                self.findings["iocs"].append({"type": "url", "value": u, "src": "html"})

        # API endpoints (fetch / const API patterns)
        for pat in [
            r'(?:API|api)\s*[=+]\s*["\']([^"\']+)["\']',
            r'fetch\(["\']([^"\']+)["\']',
        ]:
            for m in re.findall(pat, html):
                self.findings["api_endpoints"].append(m)
                print(f"  [API] {m}")

        # Forms
        for form in await page.query_selector_all("form"):
            fi = {
                "action": await form.get_attribute("action") or url,
                "fields": []
            }
            for inp in await form.query_selector_all("input"):
                fi["fields"].append({
                    "type": await inp.get_attribute("type") or "text",
                    "name": await inp.get_attribute("name") or "",
                    "id":   await inp.get_attribute("id") or "",
                })
            if fi["fields"]:
                self.findings["forms"].append(fi)

        self.findings["pages"].append({
            "url": url, "title": await page.title(), "html": str(hp)
        })

    # ── Form interaction ──────────────────────────────────────────────────────
    async def _interact(self, page):
        email = self.args.fill_email or DEFAULT_EMAIL
        pwd   = self.args.fill_password or DEFAULT_PASSWORD
        code  = self.args.fill_code or DEFAULT_CODE

        for sel, val, label in [
            ('input[type="email"],input[name*="email"],input[id*="loginfmt"],input[name*="user"]',
             email, "email"),
            ('input[type="password"],input[name*="pass"]',
             pwd, "password"),
            ('input[id*="code"],input[name*="code"],input[placeholder*="ode"]',
             code, "device-code"),
        ]:
            for s in sel.split(","):
                try:
                    el = await page.query_selector(s.strip())
                    if el and await el.is_visible():
                        await el.fill(val)
                        print(f"  [form] filled {label} → {s.strip()}")
                        break
                except Exception:
                    pass

        # Submit — try common button patterns
        for s in [
            'button[type="submit"]', 'input[type="submit"]',
            'button:has-text("Next")', 'button:has-text("Sign in")',
            'button:has-text("Continue")', 'button:has-text("Verify")',
        ]:
            try:
                el = await page.query_selector(s)
                if el and await el.is_visible():
                    print(f"  [form] clicking: {s}")
                    await el.click()
                    await asyncio.sleep(3)
                    break
            except Exception:
                pass

    # ── Main ─────────────────────────────────────────────────────────────────
    async def run(self):
        if not HAS_PLAYWRIGHT:
            print("[ERROR] playwright not installed. Run: pip install 'playwright>=1.60' && playwright install chromium")
            sys.exit(1)

        print(f"\n{'='*60}")
        print(f"  CyberHawk Phishing Browser")
        print(f"  Target  : {self.args.url}")
        print(f"  Output  : {self.out}")
        print(f"  Stealth : {HAS_STEALTH and not self.args.no_stealth}")
        print(f"  Interact: {self.args.interact}")
        print(f"  Proxy   : {self.args.proxy or 'none'}")
        print(f"{'='*60}\n")

        har_path = str(self.out / f"network_{self.ts}.har") if self.args.har else None
        tms      = self.args.timeout * 1000

        async with async_playwright() as pw:
            # Prefer full Chromium over headless-shell — latter is trivially fingerprinted
            exe_kwarg = {}
            if os.path.exists(_FULL_CHROME):
                exe_kwarg["executable_path"] = _FULL_CHROME

            browser = await pw.chromium.launch(
                headless=True,
                args=CHROMIUM_ARGS,
                proxy={"server": self.args.proxy} if self.args.proxy else None,
                **exe_kwarg,
            )
            ctx = await browser.new_context(
                user_agent          = self.args.user_agent or STEALTH_UA,
                viewport            = {"width": 1920, "height": 1080},
                locale              = self.args.locale,
                timezone_id         = self.args.timezone,
                color_scheme        = "light",
                record_har_path     = har_path,
                ignore_https_errors = True,
                extra_http_headers  = {"Accept-Language": "en-US,en;q=0.9"},
            )
            page = await ctx.new_page()

            # Inject GPU / webdriver spoof before any page JS runs
            await page.add_init_script(WEBGL_SPOOF_JS)

            # Apply playwright-stealth patches (removes remaining automation tells)
            if HAS_STEALTH and not self.args.no_stealth:
                await Stealth().apply_stealth_async(page)

            page.on("request",  self._on_request)
            page.on("response", self._on_response)

            try:
                # Step 1 — Navigate to target
                print(f"[1] Loading target...")
                resp = await page.goto(self.args.url, wait_until="networkidle", timeout=tms)
                self.step += 1
                url1 = page.url
                print(f"    Status : {resp.status if resp else '?'}")
                print(f"    URL    : {url1}")
                await self._shot(page, "initial")
                await self._extract(page, url1)

                # Step 2 — Wait for fingerprint gate POST + redirect
                print(f"\n[2] Waiting for fingerprint gate to fire...")
                await asyncio.sleep(4)
                try:
                    await page.wait_for_load_state("networkidle", timeout=tms)
                except Exception:
                    pass
                self.step += 1
                url2 = page.url
                print(f"    URL after gate: {url2}")
                await self._shot(page, "post_gate")
                if url2 != url1:
                    await self._extract(page, url2)

                # Report key findings immediately
                if self.findings["device_code"]:
                    print(f"\n  [!!!] DEVICE CODE PHISHING — code: {self.findings['device_code']}")
                if self.findings["oauth_urls"]:
                    print(f"  [!]  OAuth URLs: {set(self.findings['oauth_urls'])}")
                if self.findings["api_endpoints"]:
                    print(f"  [!]  API endpoints: {set(self.findings['api_endpoints'])}")

                # Step 3 — Form interaction
                if self.args.interact:
                    print(f"\n[3] Interacting with forms...")
                    await self._interact(page)
                    await asyncio.sleep(4)
                    try:
                        await page.wait_for_load_state("networkidle", timeout=tms)
                    except Exception:
                        pass
                    self.step += 1
                    url3 = page.url
                    print(f"    Post-interact URL: {url3}")
                    await self._shot(page, "post_interact")
                    await self._extract(page, url3)

                await self._shot(page, "final")

            except PWTimeout:
                print(f"[TIMEOUT] {self.args.timeout}s exceeded — saving what was captured")
            except Exception as ex:
                print(f"[ERROR] {type(ex).__name__}: {ex}")
            finally:
                await ctx.close()
                await browser.close()

        # Save JSON report
        rp = self.out / f"report_{self.ts}.json"
        rp.write_text(json.dumps(self.findings, indent=2, default=str))

        # Print summary
        f = self.findings
        print(f"\n{'='*60}  SUMMARY")
        print(f"  Pages      : {len(f['pages'])}")
        print(f"  Redirects  : {len(f['redirects'])}")
        print(f"  Requests   : {len([x for x in f['network'] if x['type'] == 'request'])}")
        print(f"  Forms      : {len(f['forms'])}")
        print(f"  JS blocks  : {len(f['js_blocks'])}")
        print(f"  Device code: {f['device_code'] or 'not found'}")
        print(f"  OAuth URLs : {len(set(f['oauth_urls']))}")
        print(f"  API endpoints: {len(set(f['api_endpoints']))}")
        if f["api_endpoints"]:
            for ep in set(f["api_endpoints"]):
                print(f"    → {ep}")
        print(f"\n  Redirect chain:")
        for r in f["redirects"]:
            print(f"    [{r['status']}] {r['from'][:70]}")
            print(f"           → {r['to'][:70]}")
        print(f"\n  Report : {rp}")
        if har_path:
            print(f"  HAR    : {har_path}")
        print(f"{'='*60}\n")


def main():
    p = argparse.ArgumentParser(
        description="CyberHawk Phishing Browser — headless Chromium investigation tool"
    )
    p.add_argument("--url",           required=True,  help="Target URL")
    p.add_argument("--case",          default="/workspace/browser_out", help="Output directory")
    p.add_argument("--fill-email",    default=DEFAULT_EMAIL)
    p.add_argument("--fill-password", default=DEFAULT_PASSWORD)
    p.add_argument("--fill-code",     default=DEFAULT_CODE)
    p.add_argument("--interact",      action="store_true", help="Auto-fill and submit forms")
    p.add_argument("--timeout",       type=int, default=30)
    p.add_argument("--screenshot",    action="store_true")
    p.add_argument("--har",           action="store_true")
    p.add_argument("--user-agent",    default=None)
    p.add_argument("--timezone",      default="America/New_York")
    p.add_argument("--locale",        default="en-US")
    p.add_argument("--no-stealth",    action="store_true")
    p.add_argument("--proxy",         default=None, help="e.g. socks5://127.0.0.1:9050")
    asyncio.run(PhishingBrowser(p.parse_args()).run())


if __name__ == "__main__":
    main()
