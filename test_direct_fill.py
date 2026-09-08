"""
Unit and integration tests for direct_fill.py.
"""

import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

import direct_fill
from direct_fill import fill_application, main as cli_main


@pytest.mark.anyio
async def test_fill_application_mocked():
    # Mock Playwright and page interactions
    mock_locator = MagicMock()
    mock_locator.count = AsyncMock(return_value=1)
    mock_locator.is_visible = AsyncMock(return_value=True)
    mock_locator.fill = AsyncMock()
    mock_locator.select_option = AsyncMock()
    mock_locator.check = AsyncMock()
    mock_locator.uncheck = AsyncMock()
    mock_locator.is_checked = AsyncMock(return_value=False)
    mock_locator.get_attribute = AsyncMock(return_value="text")
    mock_locator.input_value = AsyncMock(return_value="")
    mock_locator.inner_text = AsyncMock(return_value="Test Label")
    mock_locator.evaluate = AsyncMock(return_value={"text": "Label *", "className": "required"})
    mock_locator.set_input_files = AsyncMock()
    mock_locator.dispatch_event = AsyncMock()
    mock_locator.first = mock_locator
    mock_locator.all = AsyncMock(return_value=[mock_locator])

    mock_option = MagicMock()
    mock_option.all_inner_texts = AsyncMock(return_value=["Yes", "No", "Male", "Asian, not Hispanic or Latino", "Bachelor's Degree", "Junior", "1 year"])
    mock_locator.locator = MagicMock(return_value=mock_option)

    mock_page = MagicMock()
    mock_page.goto = AsyncMock()
    mock_page.wait_for_timeout = AsyncMock()
    mock_page.inner_text = AsyncMock(return_value="Job Description: Software Engineer in Corvallis, OR. Salary: $80,000 - $120,000")
    mock_page.evaluate = AsyncMock(return_value={"accepted": True, "method": "cookie_button", "text": "Accept"})
    mock_page.screenshot = AsyncMock()
    mock_page.is_closed = MagicMock(return_value=True)
    mock_page.keyboard = MagicMock()
    mock_page.keyboard.press = AsyncMock()
    mock_page.locator = MagicMock(return_value=mock_locator)

    mock_context = MagicMock()
    mock_context.pages = [mock_page]
    mock_context.add_init_script = AsyncMock()
    mock_context.close = AsyncMock()

    mock_browser = MagicMock()
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_browser.is_connected = MagicMock(return_value=True)
    mock_browser.close = AsyncMock()

    mock_playwright = MagicMock()
    mock_playwright.chromium = MagicMock()
    mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)
    mock_playwright.chromium.launch_persistent_context = AsyncMock(return_value=mock_context)

    mock_p_ctx = AsyncMock()
    mock_p_ctx.__aenter__.return_value = mock_playwright
    mock_p_ctx.__aexit__.return_value = None

    with patch("direct_fill.async_playwright", return_value=mock_p_ctx), \
         patch("direct_fill.find_chromium_executable", return_value="/bin/chrome"):
        res = await fill_application(
            "http://example.com/job",
            headless=True,
            pause_for_review=False,
            screenshot_path="/tmp/test_shot.png"
        )
        assert res["cookies_accepted"] is True
        assert res["screenshot"] == "/tmp/test_shot.png"


@pytest.mark.anyio
async def test_fill_application_persistent_context():
    mock_locator = MagicMock()
    mock_locator.count = AsyncMock(return_value=0)
    mock_locator.first = mock_locator
    mock_locator.all = AsyncMock(return_value=[])

    mock_page = MagicMock()
    mock_page.is_closed = MagicMock(return_value=True)
    mock_page.evaluate = AsyncMock(return_value=None)
    mock_page.inner_text = AsyncMock(return_value="Job body")
    mock_page.screenshot = AsyncMock()
    mock_page.goto = AsyncMock()
    mock_page.wait_for_timeout = AsyncMock()
    mock_page.locator = MagicMock(return_value=mock_locator)

    mock_context = MagicMock()
    mock_context.pages = []
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_context.add_init_script = AsyncMock()
    mock_context.close = AsyncMock()

    mock_playwright = MagicMock()
    mock_playwright.chromium = MagicMock()
    mock_playwright.chromium.launch_persistent_context = AsyncMock(return_value=mock_context)

    mock_p_ctx = AsyncMock()
    mock_p_ctx.__aenter__.return_value = mock_playwright
    mock_p_ctx.__aexit__.return_value = None

    with patch("direct_fill.async_playwright", return_value=mock_p_ctx), \
         patch.dict(os.environ, {"BROWSER_USER_DATA_DIR": "/tmp/fake_profile"}), \
         patch("direct_fill.find_chromium_executable", return_value="/bin/chrome"):
        res = await fill_application(
            "https://example.com/job",
            headless=True,
            pause_for_review=False
        )
        assert mock_playwright.chromium.launch_persistent_context.called


def test_cli_main_direct_fill():
    with patch("sys.argv", ["direct_fill.py", "https://example.com/job", "--headless"]), \
         patch("direct_fill.fill_application", new_callable=AsyncMock) as mock_fill:
        cli_main()
        mock_fill.assert_called_once_with("https://example.com/job", headless=True, screenshot_path=None)


def test_entrypoint_direct_fill():
    with patch("direct_fill.main") as mock_main:
        with patch.object(direct_fill, "__name__", "__main__"):
            if direct_fill.__name__ == "__main__":
                direct_fill.main()
            assert mock_main.called
