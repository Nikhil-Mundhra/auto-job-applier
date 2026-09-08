"""
Tests for cookie_handler.py.
Verifies that cookie prompt selectors, heuristics, and script generation correctly
target known CMP banners (OneTrust, Cookiebot, Osano, Workday, etc.) without false triggers.
"""

import re
from cookie_handler import COOKIE_AUTO_ACCEPT_JS, get_cookie_init_script


def test_cookie_init_script_structure():
    script = get_cookie_init_script()
    assert "DOMContentLoaded" in script
    assert "runCookieHandler" in script
    assert "setTimeout" in script


def test_cmp_selectors_present():
    # OneTrust
    assert "#onetrust-accept-btn-handler" in COOKIE_AUTO_ACCEPT_JS
    # Cookiebot
    assert "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll" in COOKIE_AUTO_ACCEPT_JS
    # Osano
    assert ".osano-cm-accept-all" in COOKIE_AUTO_ACCEPT_JS
    # TrustArc
    assert "#truste-consent-button" in COOKIE_AUTO_ACCEPT_JS
    # Workday
    assert "cookie-consent-accept-all" in COOKIE_AUTO_ACCEPT_JS


def test_accept_regex_patterns():
    # Extract the regex pattern from COOKIE_AUTO_ACCEPT_JS
    pattern_match = re.search(r"const ACCEPT_REGEX = /([^/]+)/i", COOKIE_AUTO_ACCEPT_JS)
    assert pattern_match is not None, "ACCEPT_REGEX not found in COOKIE_AUTO_ACCEPT_JS"
    regex = re.compile(pattern_match.group(1), re.IGNORECASE)

    # Positive cases
    valid_texts = [
        "Accept all cookies",
        "Accept All Cookies",
        "accept all",
        "ALLOW ALL COOKIES",
        "Accept Cookies",
        "I Accept",
        "I Agree",
        "Agree & Continue",
        "Accept & Continue",
        "Got it",
        "Accept",
        "Agree",
    ]
    for text in valid_texts:
        assert regex.match(text) is not None, f"Expected '{text}' to match cookie accept regex"

    # Negative cases (should not match)
    invalid_texts = [
        "Reject all",
        "Decline all cookies",
        "Manage preferences",
        "Cookie settings",
        "Apply Now",
        "Submit Application",
        "Next",
    ]
    for text in invalid_texts:
        assert regex.match(text) is None, f"Expected '{text}' NOT to match cookie accept regex"


import asyncio
import json
from unittest.mock import AsyncMock, MagicMock
from cookie_handler import COOKIE_AUTO_ACCEPT_JS, get_cookie_init_script, auto_accept_cookies


def test_auto_accept_cookies_no_session():
    res = asyncio.run(auto_accept_cookies(None))
    assert res["accepted"] is False
    assert "No browser session available" in res["error"]


def test_auto_accept_cookies_no_page():
    session = MagicMock()
    session.get_current_page = AsyncMock(return_value=None)
    res = asyncio.run(auto_accept_cookies(session))
    assert res["accepted"] is False
    assert "No active page found" in res["error"]


def test_auto_accept_cookies_dict_result():
    page = MagicMock()
    page.evaluate = AsyncMock(return_value={"accepted": True, "text": "Accept All"})
    session = MagicMock()
    session.get_current_page = AsyncMock(return_value=page)
    res = asyncio.run(auto_accept_cookies(session))
    assert res["accepted"] is True
    assert res["text"] == "Accept All"


def test_auto_accept_cookies_json_string_result():
    page = MagicMock()
    page.evaluate = AsyncMock(return_value=json.dumps({"accepted": True, "selector": "#onetrust-btn"}))
    session = MagicMock()
    session.get_current_page = AsyncMock(return_value=page)
    res = asyncio.run(auto_accept_cookies(session))
    assert res["accepted"] is True
    assert res["selector"] == "#onetrust-btn"


def test_auto_accept_cookies_raw_string_result():
    page = MagicMock()
    page.evaluate = AsyncMock(return_value="accepted prompt")
    session = MagicMock()
    session.get_current_page = AsyncMock(return_value=page)
    res = asyncio.run(auto_accept_cookies(session))
    assert res["accepted"] is True


def test_auto_accept_cookies_other_result():
    page = MagicMock()
    page.evaluate = AsyncMock(return_value=12345)
    session = MagicMock()
    session.get_current_page = AsyncMock(return_value=page)
    res = asyncio.run(auto_accept_cookies(session))
    assert res["accepted"] is False


def test_auto_accept_cookies_exception():
    page = MagicMock()
    page.evaluate = AsyncMock(side_effect=RuntimeError("Page crashed"))
    session = MagicMock()
    session.get_current_page = AsyncMock(return_value=page)
    res = asyncio.run(auto_accept_cookies(session))
    assert res["accepted"] is False
    assert "Page crashed" in res["error"]


if __name__ == "__main__":
    test_cookie_init_script_structure()
    test_cmp_selectors_present()
    test_accept_regex_patterns()
    test_auto_accept_cookies_no_session()
    test_auto_accept_cookies_no_page()
    test_auto_accept_cookies_dict_result()
    test_auto_accept_cookies_json_string_result()
    test_auto_accept_cookies_raw_string_result()
    test_auto_accept_cookies_other_result()
    test_auto_accept_cookies_exception()
    print("All cookie handler tests passed successfully!")
