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


if __name__ == "__main__":
    test_resume_path_validation()
    test_resume_path_fallback_when_profile_empty()
    test_ats_resume_selector_matching()
    test_task_prompt_includes_resume_instructions()
    print("All resume uploader tests passed successfully!")
