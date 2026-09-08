import os
from pathlib import Path
from unittest.mock import patch

import pytest

from browser_config import (
    find_chromium_executable,
    get_browser_launch_args,
    STEALTH_INIT_SCRIPT,
)


def test_find_chromium_executable_returns_opera_gx_or_valid_binary():
    exe = find_chromium_executable()
    assert exe is not None
    assert os.path.exists(exe)
    assert os.access(exe, os.X_OK)
    if os.path.exists("/Applications/Opera GX.app/Contents/MacOS/Opera"):
        assert "Opera GX" in exe


def test_find_chromium_executable_respects_env_override(tmp_path):
    fake_browser = tmp_path / "custom_browser"
    fake_browser.write_text("#!/bin/sh\necho custom\n")
    fake_browser.chmod(0o755)

    with patch.dict(os.environ, {"BROWSER_EXECUTABLE_PATH": str(fake_browser)}):
        assert find_chromium_executable() == str(fake_browser)


def test_get_browser_launch_args_contains_anti_detection_flags():
    args = get_browser_launch_args()
    assert "--disable-blink-features=AutomationControlled" in args
    assert "--use-mock-keychain" in args
    assert "--password-store=basic" in args
    assert "--no-default-browser-check" in args
    assert "--no-first-run" in args


def test_stealth_init_script_content():
    assert "navigator" in STEALTH_INIT_SCRIPT
    assert "webdriver" in STEALTH_INIT_SCRIPT
    assert "window.chrome" in STEALTH_INIT_SCRIPT


@pytest.mark.anyio
async def test_opera_gx_playwright_stealth_flags():
    from playwright.async_api import async_playwright

    exe = find_chromium_executable()
    if not exe or not os.path.exists(exe):
        pytest.skip("No compatible browser binary found")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            executable_path=exe,
            args=get_browser_launch_args(),
            ignore_default_args=["--enable-automation"],
        )
        context = await browser.new_context()
        await context.add_init_script(STEALTH_INIT_SCRIPT)
        page = await context.new_page()
        await page.goto("about:blank")

        webdriver_flag = await page.evaluate("navigator.webdriver")
        has_chrome = await page.evaluate("Boolean(window.chrome)")

        assert webdriver_flag is False or webdriver_flag is None
        assert has_chrome is True

        await browser.close()
