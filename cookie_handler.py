"""
Deterministic Cookie Consent Auto-Acceptance.
Automatically detects and clicks cookie prompts, banners, and modals across
major CMPs (OneTrust, Cookiebot, Osano, Didomi, TrustArc, Usercentrics, Workday, etc.)
without consuming any AI agent turns or tokens.
"""

from __future__ import annotations

import json
from typing import Any, Optional

# Complete deterministic JavaScript snippet to detect, click, and dismiss cookie prompts
COOKIE_AUTO_ACCEPT_JS = """() => {
    try {
        // Helper: deep query selector across document and shadow roots
        function queryAllDeep(selector, root = document) {
            let elements = Array.from(root.querySelectorAll(selector));
            const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
            let node;
            while ((node = walker.nextNode())) {
                if (node.shadowRoot) {
                    elements = elements.concat(queryAllDeep(selector, node.shadowRoot));
                }
            }
            return elements;
        }

        // Helper: check if element is visible and clickable
        function isVisible(el) {
            if (!el) return false;
            const style = window.getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
                return false;
            }
            const rect = el.getBoundingClientRect();
            return rect.width > 0 && rect.height > 0;
        }

        // Helper: safely click an element triggering mouse & pointer events
        function triggerClick(el) {
            try {
                el.scrollIntoView({ block: 'center', inline: 'center' });
            } catch (e) {}
            try {
                el.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
                el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                el.dispatchEvent(new PointerEvent('pointerup', { bubbles: true }));
                el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
            } catch (e) {}
            el.click();
        }

        // 1. Known CMP primary accept button selectors
        const KNOWN_CMP_SELECTORS = [
            // OneTrust
            '#onetrust-accept-btn-handler',
            'button#onetrust-accept-btn-handler',
            '.onetrust-close-btn-handler',
            // Cookiebot
            '#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll',
            '#CybotCookiebotDialogBodyButtonAccept',
            '#CybotCookiebotDialogBodyLevelButtonAccept',
            // Osano
            '.osano-cm-accept-all',
            'button.osano-cm-button--type_accept',
            // TrustArc / Evidon
            '#truste-consent-button',
            '.trustarc-agree-btn',
            '.trustarc-client-btn-primary',
            // Didomi
            '#didomi-notice-agree-button',
            // Usercentrics
            'button[data-testid="uc-accept-all-button"]',
            'button[data-testid="uc-accept-all"]',
            // Klaro
            'button.cm-btn-accept-all',
            'button.cm-btn-success',
            // Axeptio
            'button#axeptio_btn_acceptAll',
            // Complianz
            'button.cmplz-accept',
            // Civic UK
            'button#ccc-recommended-settings',
            'button#ccc-notify-accept',
            // Workday & ATS Specific
            'button[data-automation-id="cookie-consent-accept-all"]',
            'button[data-automation-id*="cookie-accept"]',
            'button[data-automation-id*="consent-accept"]',
            // Generic data attributes
            '[data-cookie-accept]',
            '[data-accept-cookies]',
            '[data-action="accept-cookies"]',
            '[aria-label="Accept all cookies" i]',
            '[aria-label="Accept cookies" i]',
            '#cookie-accept',
            '#accept-cookies',
            '.accept-cookies-button',
        ];

        for (const selector of KNOWN_CMP_SELECTORS) {
            const matches = queryAllDeep(selector);
            for (const el of matches) {
                if (isVisible(el)) {
                    const text = (el.innerText || el.textContent || selector).trim();
                    triggerClick(el);
                    return { accepted: true, method: 'cmp_selector', selector: selector, text: text };
                }
            }
        }

        // 2. Generic heuristic: find buttons inside cookie/privacy containers
        const CONTAINER_SELECTOR = [
            '[id*="cookie" i]',
            '[id*="consent" i]',
            '[id*="privacy" i]',
            '[id*="gdpr" i]',
            '[class*="cookie" i]',
            '[class*="consent" i]',
            '[class*="privacy" i]',
            '[class*="banner" i]',
            '[role="dialog"][aria-label*="cookie" i]',
            '[role="dialog"][aria-label*="consent" i]',
            '[role="region"][aria-label*="cookie" i]',
            '[role="region"][aria-label*="consent" i]',
        ].join(', ');

        const containers = queryAllDeep(CONTAINER_SELECTOR);
        const ACCEPT_REGEX = /^(accept all cookies|accept all|allow all cookies|allow all|accept cookies|i accept|i agree|agree & continue|accept & continue|agree and continue|accept and continue|got it|agree|accept)$/i;

        for (const container of containers) {
            if (!isVisible(container)) continue;

            const clickable = queryAllDeep('button, a[role="button"], input[type="button"], input[type="submit"]', container);
            for (const btn of clickable) {
                if (!isVisible(btn)) continue;
                const text = (btn.innerText || btn.textContent || btn.value || '').trim();
                if (ACCEPT_REGEX.test(text)) {
                    triggerClick(btn);
                    return { accepted: true, method: 'text_match', text: text };
                }
            }
        }

        // 3. Clean up any leftover modal backdrops / overlays if CMP was dismissed
        const backdrops = queryAllDeep('.onetrust-pc-dark-filter, .osano-cm-dialog__overlay, #CybotCookiebotDialogBodyUnderlay');
        for (const bd of backdrops) {
            try {
                bd.style.display = 'none';
            } catch (e) {}
        }

        return { accepted: false };
    } catch (err) {
        return { accepted: false, error: String(err) };
    }
}"""


def get_cookie_init_script() -> str:
    """Return the client-side JavaScript snippet to inject at document start."""
    return f"""
    (() => {{
        const runCookieHandler = {COOKIE_AUTO_ACCEPT_JS};
        // Run immediately
        if (document.readyState !== 'loading') {{
            runCookieHandler();
        }}
        // Run on DOM ready
        document.addEventListener('DOMContentLoaded', () => {{
            runCookieHandler();
            // Also retry after 500ms and 1500ms for delayed CMP banners
            setTimeout(runCookieHandler, 500);
            setTimeout(runCookieHandler, 1500);
        }});
    }})();
    """


async def auto_accept_cookies(browser_session: Any) -> dict[str, Any]:
    """
    Executes the deterministic cookie auto-acceptor on the currently active page.
    Returns a dict with execution results (e.g. {'accepted': True, 'text': 'Accept All'}).
    """
    if not browser_session:
        return {"accepted": False, "error": "No browser session available"}

    try:
        page = await browser_session.get_current_page()
        if not page:
            return {"accepted": False, "error": "No active page found"}

        # Page actor evaluate expects an arrow function string (...args) => format
        raw_result = await page.evaluate(COOKIE_AUTO_ACCEPT_JS)
        if isinstance(raw_result, str) and raw_result.strip():
            try:
                res = json.loads(raw_result)
            except Exception:
                res = {"accepted": "accepted" in raw_result.lower(), "raw": raw_result}
        elif isinstance(raw_result, dict):
            res = raw_result
        else:
            res = {"accepted": False}

        if res.get("accepted"):
            msg = res.get("text") or res.get("selector") or "accepted"
            print(f"🍪 Auto-accepted cookies prompt: '{msg}'")

        return res
    except Exception as e:
        # Non-blocking: never crash application flow if cookie check errors
        return {"accepted": False, "error": str(e)}
