"""
Automated Resume PDF Uploader.
Handles automatic detection and uploading of Nikhil Mundhra CV.pdf across
applicant tracking systems (Workday, Greenhouse, Lever, Ashby, etc.)
via direct Playwright DOM injection, filechooser event interception,
and browser-use custom controller actions.
"""

from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path
from typing import Any, Optional

DEFAULT_RESUME_FILENAME = "Nikhil Mundhra CV.pdf"

# Standard ATS selectors for resume upload inputs
RESUME_INPUT_SELECTORS = [
    # Workday
    'input[type="file"][data-automation-id*="resume"]',
    'input[type="file"][data-automation-id*="Resume"]',
    'input[type="file"][data-automation-id*="file-upload"]',
    # Greenhouse
    'input[type="file"]#resume_file',
    'input[type="file"][name="resume"]',
    'input[type="file"][data-qa="resume-upload"]',
    # Lever
    'input[type="file"]#resume-upload-input',
    'input[type="file"][name="resume"]',
    # Ashby
    'input[type="file"][id*="resume"]',
    'input[type="file"][name*="resume"]',
    # Generic keywords
    'input[type="file"][id*="cv"]',
    'input[type="file"][name*="cv"]',
    'input[type="file"][aria-label*="resume" i]',
    'input[type="file"][aria-label*="cv" i]',
    'input[type="file"][accept*="pdf"]',
    'input[type="file"]',
]


def get_validated_resume_path(profile: Optional[dict[str, Any]] = None) -> Path:
    """
    Locates and validates the target PDF resume.
    Defaults to Portfolio/Nikhil Mundhra CV.pdf.
    """
    candidate_paths: list[Path] = []

    if profile and profile.get("resume_path"):
        candidate_paths.append(Path(profile["resume_path"]))

    repo_root = Path(__file__).parent
    candidate_paths.extend([
        repo_root / "Portfolio" / DEFAULT_RESUME_FILENAME,
        repo_root / DEFAULT_RESUME_FILENAME,
    ])

    for p in candidate_paths:
        if p.exists() and p.is_file() and p.suffix.lower() == ".pdf":
            return p.resolve()

    # Search Portfolio directory for any matching pdf
    portfolio_dir = repo_root / "Portfolio"
    if portfolio_dir.exists():
        for f in portfolio_dir.glob("*.pdf"):
            return f.resolve()

    raise FileNotFoundError(
        f"Resume PDF not found! Checked: {[str(p) for p in candidate_paths]}. "
        f"Please ensure '{DEFAULT_RESUME_FILENAME}' exists in the Portfolio directory."
    )


def match_resume_selector_in_html(html_text: str) -> list[str]:
    """
    Helper function to inspect HTML and find which selectors match resume file inputs.
    Useful for testing and DOM analysis without a live browser.
    """
    matched: list[str] = []
    for sel in RESUME_INPUT_SELECTORS:
        # Check specific tag and attributes
        if 'data-automation-id*="resume"' in sel and 'data-automation-id="jobApplicationAttachment-resume' in html_text:
            matched.append(sel)
        elif '#resume_file' in sel and 'id="resume_file"' in html_text:
            matched.append(sel)
        elif 'name="resume"' in sel and 'name="resume"' in html_text:
            matched.append(sel)
        elif '#resume-upload-input' in sel and 'id="resume-upload-input"' in html_text:
            matched.append(sel)
        elif 'accept*="pdf"' in sel and 'accept=".pdf' in html_text:
            matched.append(sel)
        elif sel == 'input[type="file"]' and 'type="file"' in html_text:
            matched.append(sel)
    return matched


async def attach_file_chooser_interceptor(page: Any, resume_path: Path) -> None:
    """
    Interception layer: catches any file picker dialog (e.g. when the agent clicks
    'Upload Resume', 'Browse files', or custom styled dropzones) and automatically
    supplies the resume PDF without prompting the OS dialog.
    """
    if not hasattr(page, "on"):
        return

    async def handle_file_chooser(file_chooser: Any) -> None:
        try:
            print(f"📎 Intercepted file chooser dialog! Auto-attaching: {resume_path.name}")
            await file_chooser.set_files(str(resume_path))
            print(f"✅ Successfully attached {resume_path.name} via file chooser interceptor.")
        except Exception as e:
            print(f"⚠️ Error setting files on file chooser: {e}")

    # Register listener on Playwright page
    page.on("filechooser", lambda fc: asyncio.create_task(handle_file_chooser(fc)))


async def upload_resume_to_page(page: Any, resume_path: Optional[Path] = None) -> dict[str, Any]:
    """
    Direct DOM injection: searches for visible or hidden file input elements,
    unhides them if needed, and calls set_input_files directly.
    """
    target_path = resume_path or get_validated_resume_path()
    path_str = str(target_path)

    if not hasattr(page, "locator"):
        return {"success": False, "message": "Invalid page object"}

    for selector in RESUME_INPUT_SELECTORS:
        try:
            locator = page.locator(selector).first
            count = await locator.count()
            if count > 0:
                # Force-unhide in case of custom styled dropzone
                await locator.evaluate(
                    """(el) => {
                        el.style.display = 'block';
                        el.style.visibility = 'visible';
                        el.style.opacity = '1';
                    }"""
                )
                await locator.set_input_files(path_str)
                # Dispatch change event for reactive forms (React, Angular, Vue)
                await locator.dispatch_event("change")
                return {
                    "success": True,
                    "selector": selector,
                    "file": target_path.name,
                    "message": f"Successfully uploaded {target_path.name} via {selector}",
                }
        except Exception:
            continue

    return {
        "success": False,
        "message": "No matching resume file input found on current page view.",
    }


def create_resume_controller(resume_path: Optional[Path] = None) -> Any:
    """
    Creates a browser-use Controller equipped with an explicit 'upload_resume' tool.
    The agent can call this action whenever it sees a CV or resume upload requirement.
    """
    try:
        from browser_use import Controller
        from browser_use.browser.session import BrowserSession
    except ImportError:
        return None

    controller = Controller()
    valid_path = resume_path or get_validated_resume_path()

    @controller.action(
        "Upload the candidate's PDF resume (Nikhil Mundhra CV.pdf) to the job application form"
    )
    async def upload_resume(browser_session) -> str:
        """
        Locates the resume file input or dropzone on the current page and automatically
        attaches Nikhil Mundhra CV.pdf, triggering necessary form change events.
        """
        try:
            page = await browser_session.get_current_page()
            if page:
                result = await upload_resume_to_page(page, valid_path)
                if result.get("success"):
                    return f"✅ Resume uploaded successfully: {result['message']}"
                else:
                    return (
                        f"⚠️ Could not find file input directly. Try clicking the "
                        f"'Upload' or 'Browse' button; the filechooser interceptor will attach the resume."
                    )
            return "⚠️ Could not access active page to upload resume."
        except Exception as e:
            return f"Error uploading resume: {e}"

    return controller
