"""
Browser configuration and stealth launcher helpers.
Prioritizes retail installed browsers (Opera GX, Google Chrome, Brave)
over automation testing builds, and configures anti-detection flags.
"""

import os
from pathlib import Path
from typing import Optional


def find_chromium_executable() -> Optional[str]:
    """Auto-detect Chromium / Opera GX / Google Chrome binary on macOS."""
    env_path = os.getenv("BROWSER_EXECUTABLE_PATH")
    if env_path and os.path.exists(env_path) and os.access(env_path, os.X_OK):
        return env_path

    # Check retail / installed consumer browsers first (Opera GX prioritized)
    for p in [
        "/Applications/Opera GX.app/Contents/MacOS/Opera",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Vivaldi.app/Contents/MacOS/Vivaldi",
    ]:
        if os.path.exists(p) and os.access(p, os.X_OK):
            return p

    # Fallback to Playwright cache only if no consumer browser is present
    playwright_cache = Path.home() / "Library/Caches/ms-playwright"
    if playwright_cache.exists():
        for chrome_bin in playwright_cache.glob("**/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"):
            if chrome_bin.exists() and os.access(chrome_bin, os.X_OK):
                return str(chrome_bin)
        for chrome_bin in playwright_cache.glob("**/chrome-headless-shell"):
            if chrome_bin.exists() and os.access(chrome_bin, os.X_OK):
                return str(chrome_bin)
    return None


def get_browser_launch_args() -> list[str]:
    """Return command line arguments for low suspicion / anti-detection execution."""
    return [
        "--use-mock-keychain",
        "--password-store=basic",
        "--disable-features=Translate",
        "--disable-blink-features=AutomationControlled",
        "--no-default-browser-check",
        "--no-first-run",
    ]


STEALTH_INIT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined,
});
if (!window.chrome) {
    window.chrome = { runtime: {} };
}
"""
