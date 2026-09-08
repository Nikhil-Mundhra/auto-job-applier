"""
Tests for automatic resume PDF upload validation, ATS selector matching,
and task prompt verification.
"""

from pathlib import Path
from resume_uploader import (
    get_validated_resume_path,
    match_resume_selector_in_html,
    create_resume_controller,
)
from main import load_profile, build_task


def test_resume_path_validation():
    profile = load_profile()
    resume_path = get_validated_resume_path(profile)

    assert resume_path.exists()
    assert resume_path.is_file()
    assert resume_path.suffix.lower() == ".pdf"
    assert "Nikhil Mundhra CV.pdf" in resume_path.name


def test_resume_path_fallback_when_profile_empty():
    resume_path = get_validated_resume_path({})
    assert resume_path.exists()
    assert "Nikhil Mundhra CV.pdf" in resume_path.name


def test_ats_resume_selector_matching():
    # 1. Workday snippet
    workday_html = '<div class="drop-zone"><input type="file" data-automation-id="jobApplicationAttachment-resume" /></div>'
    matched_wd = match_resume_selector_in_html(workday_html)
    assert any("resume" in s for s in matched_wd)

    # 2. Greenhouse snippet
    greenhouse_html = '<div class="field"><input type="file" id="resume_file" name="resume" accept=".pdf,.doc" /></div>'
    matched_gh = match_resume_selector_in_html(greenhouse_html)
    assert 'input[type="file"]#resume_file' in matched_gh

    # 3. Lever snippet
    lever_html = '<div class="application-field"><input type="file" id="resume-upload-input" name="resume" /></div>'
    matched_lever = match_resume_selector_in_html(lever_html)
    assert 'input[type="file"]#resume-upload-input' in matched_lever

    # 4. Generic PDF snippet
    generic_html = '<input type="file" accept=".pdf" class="file-picker-hidden" />'
    matched_generic = match_resume_selector_in_html(generic_html)
    assert 'input[type="file"][accept*="pdf"]' in matched_generic


def test_task_prompt_includes_resume_instructions():
    profile = load_profile()
    resume_path = get_validated_resume_path(profile)
    task = build_task(profile, job_url="https://jobs.example.com/apply/1")

    assert "RESUME / CV AUTO-UPLOAD:" in task
    assert "upload_resume" in task
    assert str(resume_path) in task
    assert "Nikhil Mundhra CV.pdf" in task
    assert "filechooser interceptor" in task


import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from resume_uploader import (
    get_validated_resume_path,
    match_resume_selector_in_html,
    attach_file_chooser_interceptor,
    upload_resume_to_page,
    create_resume_controller,
)


def test_resume_not_found_raises():
    with patch("resume_uploader.Path.exists", return_value=False), \
         patch("resume_uploader.Path.glob", return_value=[]):
        with pytest.raises(FileNotFoundError):
            get_validated_resume_path({"resume_path": "/nonexistent/path.pdf"})


def test_resume_search_portfolio_glob():
    mock_pdf = Path("/fake/dir/Portfolio/found.pdf")
    with patch("resume_uploader.Path.exists") as mock_exists, \
         patch("resume_uploader.Path.glob", return_value=[mock_pdf]):
        # make first candidate checks False, portfolio dir True
        mock_exists.side_effect = lambda: True
        with patch.object(Path, "is_file", return_value=False):
            with patch("resume_uploader.Path.resolve", return_value=mock_pdf):
                path = get_validated_resume_path({})
                assert path == mock_pdf


def test_attach_file_chooser_interceptor():
    async def _test():
        resume_path = Path("/fake/resume.pdf")

        # 1. Page without 'on' attribute
        await attach_file_chooser_interceptor(object(), resume_path)

        # 2. Page with 'on' attribute
        page = MagicMock()
        listeners = {}
        page.on = MagicMock(side_effect=lambda ev, fn: listeners.update({ev: fn}))

        await attach_file_chooser_interceptor(page, resume_path)
        assert "filechooser" in listeners

        # Test filechooser callback success
        mock_fc = MagicMock()
        mock_fc.set_files = AsyncMock()
        task = listeners["filechooser"](mock_fc)
        await task

        # Test filechooser callback exception
        mock_fc_err = MagicMock()
        mock_fc_err.set_files = AsyncMock(side_effect=RuntimeError("Chooser failed"))
        task_err = listeners["filechooser"](mock_fc_err)
        await task_err

    asyncio.run(_test())


def test_upload_resume_to_page_invalid_page():
    res = asyncio.run(upload_resume_to_page(object()))
    assert res["success"] is False
    assert "Invalid page object" in res["message"]


def test_upload_resume_to_page_success():
    page = MagicMock()
    locator = MagicMock()
    locator.count = AsyncMock(return_value=1)
    locator.evaluate = AsyncMock()
    locator.set_input_files = AsyncMock()
    locator.dispatch_event = AsyncMock()

    page.locator = MagicMock(return_value=MagicMock(first=locator))

    res = asyncio.run(upload_resume_to_page(page))
    assert res["success"] is True
    assert "Successfully uploaded" in res["message"]


def test_upload_resume_to_page_not_found():
    page = MagicMock()
    locator = MagicMock()
    locator.count = AsyncMock(return_value=0)
    page.locator = MagicMock(return_value=MagicMock(first=locator))

    res = asyncio.run(upload_resume_to_page(page))
    assert res["success"] is False
    assert "No matching resume file input found" in res["message"]


def test_upload_resume_to_page_exception():
    page = MagicMock()
    locator = MagicMock()
    locator.count = AsyncMock(return_value=1)
    locator.evaluate = AsyncMock(side_effect=RuntimeError("DOM error"))
    page.locator = MagicMock(return_value=MagicMock(first=locator))

    res = asyncio.run(upload_resume_to_page(page))
    assert res["success"] is False


def test_create_resume_controller():
    controller = create_resume_controller()
    assert controller is not None

    # Retrieve registered upload_resume action
    reg = getattr(controller, "registry", None)
    inner_reg = getattr(reg, "registry", reg)
    actions = getattr(inner_reg, "actions", {})
    action_obj = actions.get("upload_resume")
    if action_obj:
        action_fn = action_obj.function
        # 1. Page exists and upload succeeds
        session = MagicMock()
        mock_page = MagicMock()
        mock_locator = MagicMock()
        mock_locator.count = AsyncMock(return_value=1)
        mock_locator.evaluate = AsyncMock()
        mock_locator.set_input_files = AsyncMock()
        mock_locator.dispatch_event = AsyncMock()
        mock_page.locator = MagicMock(return_value=MagicMock(first=mock_locator))
        session.get_current_page = AsyncMock(return_value=mock_page)

        msg = asyncio.run(action_fn(browser_session=session))
        assert "Resume uploaded successfully" in msg

        # 2. Page exists and upload fails
        mock_locator.count = AsyncMock(return_value=0)
        msg_fail = asyncio.run(action_fn(browser_session=session))
        assert "Could not find file input directly" in msg_fail

        # 3. No active page
        session.get_current_page = AsyncMock(return_value=None)
        msg_no_page = asyncio.run(action_fn(browser_session=session))
        assert "Could not access active page" in msg_no_page

        # 4. Exception
        session.get_current_page = AsyncMock(side_effect=RuntimeError("Boom"))
        msg_err = asyncio.run(action_fn(browser_session=session))
        assert "Error uploading resume" in msg_err


def test_create_resume_controller_import_error():
    with patch.dict("sys.modules", {"browser_use": None}):
        c = create_resume_controller()
        assert c is None


if __name__ == "__main__":
    test_resume_path_validation()
    test_resume_path_fallback_when_profile_empty()
    test_ats_resume_selector_matching()
    test_task_prompt_includes_resume_instructions()
    test_resume_not_found_raises()
    test_attach_file_chooser_interceptor()
    test_upload_resume_to_page_invalid_page()
    test_upload_resume_to_page_success()
    test_upload_resume_to_page_not_found()
    test_create_resume_controller()
    test_create_resume_controller_import_error()
    print("All resume uploader tests passed successfully!")
