"""Fetch and download THROUGH the user's own Chrome (so a browser-only VPN such as Urban VPN
applies). Python never talks to the hospital; Chrome does, driven over the DevTools protocol.

Start Chrome once with remote debugging (tools\\chrome_hpt.ps1 does this):
  chrome.exe --remote-debugging-port=9222 --user-data-dir=D:\\Meshkor_Backend\\chrome-hpt
In that profile install the VPN extension and switch it to a US server. Leave the window open.

Two functions with the same signatures as the requests versions, so run.py can swap them in:
  fetch(url, timeout)                 -> (status, text)      replaces discover.fetch
  stream_download(url, dest, timeout) -> (sha256, bytes, status)   replaces download.stream_download

Downloads: Chrome would show a .json or .csv in the tab instead of saving it, so the response
headers are rewritten on the fly (Fetch.continueResponse adds Content-Disposition: attachment)
and Chrome streams the body straight to the destination folder (Browser.setDownloadBehavior).
Nothing passes through Python memory and nothing lands on C:.
"""
from __future__ import annotations

import hashlib
import os
import re
import time
from pathlib import Path

CDP_URL = os.environ.get("MESHKOR_CHROME_CDP", "http://127.0.0.1:9222")
_state: dict = {}


def _connect():
    if "page" in _state:
        return _state
    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(CDP_URL, timeout=10_000)
    except Exception as e:  # noqa: BLE001
        pw.stop()
        raise RuntimeError(f"Chrome is not reachable at {CDP_URL}. Start it with tools\\chrome_hpt.ps1 first.") from e
    ctx = browser.contexts[0] if browser.contexts else browser.new_context()
    page = ctx.new_page()
    cdp = ctx.new_cdp_session(page)
    _state.update(pw=pw, browser=browser, ctx=ctx, page=page, cdp=cdp)
    return _state


def close() -> None:
    s = _state
    if not s:
        return
    try:
        s["page"].close()
    except Exception:  # noqa: BLE001
        pass
    try:
        s["pw"].stop()
    except Exception:  # noqa: BLE001
        pass
    _state.clear()


def fetch(url: str, timeout: int = 20) -> tuple[int, str]:
    """Open the URL in Chrome and return (status, visible text). Used for cms-hpt.txt."""
    s = _connect()
    page = s["page"]
    try:
        resp = page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")
    except Exception as e:  # noqa: BLE001
        return 0, str(e)[:120]
    status = resp.status if resp else 0
    if status != 200:
        return status, ""
    try:
        text = page.evaluate("document.body ? document.body.innerText : ''")
    except Exception:  # noqa: BLE001
        text = page.content()
    return status, text


def stream_download(url: str, dest: Path, timeout: int = 3600) -> tuple[str, int, int]:
    """Make Chrome download `url` to `dest` (any drive). Returns (sha256, bytes, status)."""
    s = _connect()
    page, cdp = s["page"], s["cdp"]
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    # a download interrupted last time leaves a GUID-named partial file: remove it, start clean
    for junk in dest.parent.iterdir():
        if junk.is_file() and re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(\.crdownload)?", junk.name):
            junk.unlink()
    done: dict = {}

    def on_will_begin(ev):
        done.setdefault("guid", ev.get("guid"))

    def on_progress(ev):
        if ev.get("state") in ("completed", "canceled"):
            done["state"] = ev["state"]; done["guid"] = ev.get("guid")
            done["bytes"] = int(ev.get("receivedBytes") or 0)
            done["total"] = int(ev.get("totalBytes") or 0)

    def on_paused(ev):
        rid = ev["requestId"]
        if "responseStatusCode" not in ev:                      # request stage: let it go
            cdp.send("Fetch.continueRequest", {"requestId": rid}); return
        code = int(ev.get("responseStatusCode") or 0)
        if ev.get("resourceType") != "Document" or 300 <= code < 400:   # redirects and sub-requests: untouched
            cdp.send("Fetch.continueResponse", {"requestId": rid}); return
        done["status"] = code
        if code != 200:
            cdp.send("Fetch.continueResponse", {"requestId": rid}); return
        headers = [h for h in (ev.get("responseHeaders") or []) if h["name"].lower() not in ("content-disposition", "content-type")]
        headers += [{"name": "Content-Type", "value": "application/octet-stream"},
                    {"name": "Content-Disposition", "value": f'attachment; filename="{dest.name}"'}]
        cdp.send("Fetch.continueResponse", {"requestId": rid, "responseCode": 200, "responseHeaders": headers})

    cdp.on("Browser.downloadWillBegin", on_will_begin)
    cdp.on("Browser.downloadProgress", on_progress)
    cdp.on("Fetch.requestPaused", on_paused)
    cdp.send("Browser.setDownloadBehavior", {"behavior": "allowAndName", "downloadPath": str(dest.parent), "eventsEnabled": True})
    cdp.send("Fetch.enable", {"patterns": [{"urlPattern": "*", "resourceType": "Document", "requestStage": "Response"}]})
    try:
        try:
            page.goto(url, timeout=60_000, wait_until="commit")
        except Exception:  # noqa: BLE001  (a download aborts the navigation: expected)
            pass
        t0 = time.time()
        while "state" not in done:
            if done.get("status", 200) != 200 and "guid" not in done:
                return "", 0, done["status"]
            if time.time() - t0 > timeout:
                return "", 0, 408
            page.wait_for_timeout(500)
    finally:
        try:
            cdp.send("Fetch.disable")
        except Exception:  # noqa: BLE001
            pass
        cdp.remove_listener("Browser.downloadWillBegin", on_will_begin)
        cdp.remove_listener("Browser.downloadProgress", on_progress)
        cdp.remove_listener("Fetch.requestPaused", on_paused)
    if done.get("state") != "completed":
        return "", 0, 499
    if done.get("total") and done.get("bytes") and done["bytes"] != done["total"]:
        (dest.parent / done["guid"]).unlink(missing_ok=True)
        return "", 0, 0            # cut off: treated as a connection failure (retry)
    got = dest.parent / done["guid"]
    if not got.exists():
        return "", 0, 499
    if dest.exists():
        dest.unlink()
    got.rename(dest)
    h = hashlib.sha256()
    with open(dest, "rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest(), dest.stat().st_size, 200
