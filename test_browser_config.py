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


def test_find_chromium_executable_env_invalid(tmp_path):
    fake_browser = tmp_path / "non_existent"
    with patch.dict(os.environ, {"BROWSER_EXECUTABLE_PATH": str(fake_browser)}):
        # When env path doesn't exist, it should continue searching
        res = find_chromium_executable()
        assert res != str(fake_browser)


def test_find_chromium_executable_playwright_cache_testing_chrome(tmp_path):
    cache_dir = tmp_path / "Library/Caches/ms-playwright"
    chrome_bin = cache_dir / "chromium-1234/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"
    chrome_bin.parent.mkdir(parents=True, exist_ok=True)
    chrome_bin.write_text("#!/bin/sh\necho testing\n")
    chrome_bin.chmod(0o755)

    with patch.dict(os.environ, {}, clear=True), \
         patch("browser_config.Path.home", return_value=tmp_path), \
         patch("os.path.exists", side_effect=lambda p: str(chrome_bin) == p or p == str(chrome_bin.parent)), \
         patch("os.access", return_value=True):
        res = find_chromium_executable()
        assert res == str(chrome_bin)


def test_find_chromium_executable_playwright_cache_headless_shell(tmp_path):
    cache_dir = tmp_path / "Library/Caches/ms-playwright"
    shell_bin = cache_dir / "chromium-1234/chrome-headless-shell"
    shell_bin.parent.mkdir(parents=True, exist_ok=True)
    shell_bin.write_text("#!/bin/sh\necho shell\n")
    shell_bin.chmod(0o755)

    with patch.dict(os.environ, {}, clear=True), \
         patch("browser_config.Path.home", return_value=tmp_path), \
         patch("os.path.exists", side_effect=lambda p: str(shell_bin) == p or p == str(shell_bin.parent)), \
         patch("os.access", return_value=True):
        res = find_chromium_executable()
        assert res == str(shell_bin)


def test_find_chromium_executable_none_found(tmp_path):
    empty_home = tmp_path / "empty_home"
    empty_home.mkdir(parents=True, exist_ok=True)

    with patch.dict(os.environ, {}, clear=True), \
         patch("browser_config.Path.home", return_value=empty_home), \
         patch("os.path.exists", return_value=False), \
         patch("os.access", return_value=False):
        res = find_chromium_executable()
        assert res is None



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
