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


if __name__ == "__main__":
    test_cookie_init_script_structure()
    test_cmp_selectors_present()
    test_accept_regex_patterns()
    print("All cookie handler tests passed successfully!")
