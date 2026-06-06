"""Reusable UI-verification harness for TRIBIQ (the BIDA_prod Streamlit app).

WHY THIS EXISTS
---------------
Streamlit `AppTest` and isolated previews do NOT reproduce this app's real
CSS/layout behaviour (form-submit buttons hidden off-screen, BaseWeb wrapper
colours, fixed-height textareas, panel switching, etc.). The only reliable way
to verify a UI change is to drive the *real* authenticated app in a browser.
This script logs in as a `users.xlsx` superuser via the Chrome DevTools Protocol
(no Playwright/Selenium needed — only the `websockets` + `requests` libs, which
are installed), clicks through a sequence of steps, and captures screenshots
and/or probes the live DOM.

PREREQS
-------
- The app must already be running, e.g.:
    streamlit run app.py --server.fileWatcherType=none --server.headless true --server.port 8501
- Google Chrome installed (default path below; override with --chrome).
- Run from the BIDA_prod directory (needs users.xlsx).

USAGE
-----
  # default: login + screenshot the landing page to docs/_verify.png
  python tools/verify_ui.py

  # a sequence of steps (semicolon-separated). Actions:
  #   click:<text>   click first button/summary whose text contains <text>
  #   exact:<text>   click first <summary> whose text == <text>
  #   wait:<seconds>
  #   shot:<file>    screenshot to docs/<file>
  #   probe:<jsexpr> Runtime.evaluate(jsexpr) and print the result
  python tools/verify_ui.py --user superuser01 \
    --steps "click:quiz; wait:2; click:start quiz; wait:12; shot:quiz.png; \
             probe:[...document.querySelectorAll('input[type=radio]')].length"

NOTE: the cold-started server runs the script on first connect, so the FIRST
run after a restart often catches the 'RUNNING…' skeleton — just run it twice
(the server stays warm) or raise --login-wait.
"""
from __future__ import annotations
import argparse, asyncio, base64, json, subprocess, sys, time
from pathlib import Path
import pandas as pd
import requests
from websockets.asyncio.client import connect

ROOT = Path(__file__).resolve().parent.parent          # BIDA_prod/
DOCS = ROOT.parent / "docs"                             # ...Tribal_knowledge/docs
DEFAULT_CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

_SET = ("(()=>{const set=(e,v)=>{const p=e.tagName==='TEXTAREA'"
        "?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;"
        "Object.getOwnPropertyDescriptor(p,'value').set.call(e,v);"
        "e.dispatchEvent(new Event('input',{bubbles:true}));"
        "e.dispatchEvent(new Event('change',{bubbles:true}));};")
FILL = _SET + ("const i=[...document.querySelectorAll('input')];"
               "const u=i.find(x=>x.type==='text');const p=i.find(x=>x.type==='password');"
               "if(u)set(u,%U%);if(p)set(p,%P%);return i.length;})()")
CLICK = ("(()=>{const w=%T%.toLowerCase();"
         "let b=[...document.querySelectorAll('button')].find(x=>(x.innerText||'').toLowerCase().includes(w));"
         "if(b){b.click();return 'button:'+b.innerText.trim();}"
         "let s=[...document.querySelectorAll('summary')].find(x=>(x.innerText||'').toLowerCase().includes(w));"
         "if(s){s.click();return 'summary:'+s.innerText.trim();}return 'NOT FOUND:'+w;})()")
EXACT = ("(()=>{const w=%T%;const s=[...document.querySelectorAll('summary')]"
         ".find(x=>(x.innerText||'').trim()===w);if(s){s.click();return 'summary:'+w;}return 'NOT FOUND:'+w;})()")


def _password_for(user_id: str) -> str:
    df = pd.read_excel(ROOT / "users.xlsx")
    return str(df[df["User ID"].astype(str) == user_id].iloc[0]["Password"])


def _launch_chrome(chrome: str, port: int):
    return subprocess.Popen(
        [chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--remote-allow-origins=*",
         f"--remote-debugging-port={port}", "--window-size=1500,2000", "--hide-scrollbars", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _devtools_ws(port: int):
    for _ in range(40):
        try:
            for t in requests.get(f"http://localhost:{port}/json").json():
                if t.get("type") == "page":
                    return t["webSocketDebuggerUrl"]
        except Exception:
            pass
        time.sleep(0.5)
    return None


async def _run(args):
    pwd = _password_for(args.user)
    proc = _launch_chrome(args.chrome, args.debug_port)
    ws_url = _devtools_ws(args.debug_port)
    if not ws_url:
        print("ERROR: could not reach Chrome DevTools"); proc.terminate(); return 1
    try:
        async with connect(ws_url, max_size=80_000_000) as ws:
            n = 0
            async def cmd(method, params=None):
                nonlocal n; n += 1; mid = n
                await ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
                while True:
                    m = json.loads(await ws.recv())
                    if m.get("id") == mid:
                        return m
            async def js(expr):
                r = await cmd("Runtime.evaluate", {"expression": expr, "returnByValue": True})
                return r.get("result", {}).get("result", {}).get("value")
            async def shot(name):
                DOCS.mkdir(exist_ok=True)
                r = await cmd("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})
                (DOCS / name).write_bytes(base64.b64decode(r["result"]["data"]))
                print("  shot ->", DOCS / name)

            await cmd("Page.enable"); await cmd("Runtime.enable")
            await cmd("Page.navigate", {"url": args.url})
            await asyncio.sleep(args.nav_wait)
            await js(FILL.replace("%U%", json.dumps(args.user)).replace("%P%", json.dumps(pwd)))
            await asyncio.sleep(1)
            await js(CLICK.replace("%T%", json.dumps("login")))
            print(f"logged in as {args.user}; waiting {args.login_wait}s for app init…")
            await asyncio.sleep(args.login_wait)

            steps = [s.strip() for s in (args.steps or "").split(";") if s.strip()]
            if not steps:
                await shot(args.out)
            for step in steps:
                action, _, val = step.partition(":")
                action = action.strip().lower()
                if action == "wait":
                    await asyncio.sleep(float(val))
                elif action == "click":
                    print("click", repr(val), "->", await js(CLICK.replace("%T%", json.dumps(val))))
                elif action == "exact":
                    print("exact", repr(val), "->", await js(EXACT.replace("%T%", json.dumps(val))))
                elif action == "shot":
                    await shot(val or args.out)
                elif action == "probe":
                    print("probe ->", await js(val))
                else:
                    print("unknown step:", step)
            print("DONE")
            return 0
    finally:
        proc.terminate()


def main():
    ap = argparse.ArgumentParser(description="Drive & screenshot the live TRIBIQ app via Chrome DevTools.")
    ap.add_argument("--user", default="superuser01", help="User ID from users.xlsx to log in as")
    ap.add_argument("--url", default="http://localhost:8501")
    ap.add_argument("--steps", default="", help="semicolon-separated: click:/exact:/wait:/shot:/probe:")
    ap.add_argument("--out", default="_verify.png", help="default screenshot filename (in docs/)")
    ap.add_argument("--chrome", default=DEFAULT_CHROME)
    ap.add_argument("--debug-port", type=int, default=9333)
    ap.add_argument("--nav-wait", type=float, default=22, help="seconds to wait for the login form")
    ap.add_argument("--login-wait", type=float, default=45, help="seconds to wait for app init after login")
    args = ap.parse_args()
    sys.exit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
