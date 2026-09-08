"""
Test suite for automated JD extraction, Company About extraction,
and strict LLM call budget enforcement (min 1, max 2 calls).
"""

import json
from pathlib import Path

from jd_extractor import (
    LLMBudgetManager,
    LLMBudgetExceededError,
    LLMBudgetUnderflowError,
    extract_company_name,
    extract_company_about_web,
    extract_json_ld,
    extract_script_jd,
    prepare_job_context,
)
from main import load_profile, build_task


def test_company_name_extraction():
    # 1. From Greenhouse URL
    gh_url = "https://boards.greenhouse.io/datadog/jobs/123456"
    assert extract_company_name(gh_url, "") == "Datadog"

    # 2. From Lever URL
    lever_url = "https://jobs.lever.co/stripe/abc-def-123"
    assert extract_company_name(lever_url, "") == "Stripe"

    # 3. From Workday URL
    wd_url = "https://netflix.wd1.myworkdayjobs.com/en-US/careers/job/SWE-1"
    assert extract_company_name(wd_url, "") == "Netflix"

    # 4. From JSON-LD hiringOrganization
    json_ld = {
        "@type": "JobPosting",
        "hiringOrganization": {"name": "Anthropic PBC"}
    }
    assert extract_company_name("https://example.com/job/1", "", json_ld=json_ld) == "Anthropic PBC"


def test_company_about_wikipedia_lookup():
    # Live or mock lookup for well-known tech firm
    about_text = extract_company_about_web("Datadog")
    assert "Datadog" in about_text or "technology" in about_text.lower()


def test_happy_path_budget_exactly_one_call():
    """
    When the HTML contains clean Schema.org JobPosting, the deterministic script
    extracts the JD with 0 LLM calls.
    Then exactly 1 LLM call is made to synthesize company profile and alignment.
    Total calls must equal 1.
    """
    mock_html = """
    <html>
      <head>
        <script type="application/ld+json">
        {
          "@context": "https://schema.org/",
          "@type": "JobPosting",
          "title": "Senior AI Systems Engineer",
          "hiringOrganization": {
            "@type": "Organization",
            "name": "Stripe"
          },
          "description": "We are looking for an AI Systems Engineer with Python, PyTorch, and distributed systems experience to scale our machine learning infrastructure and fraud detection systems.",
          "responsibilities": "Design and maintain high-throughput ML inference pipelines and fraud detection models.",
          "qualifications": "Strong proficiency in Python, PyTorch, system design, and distributed data pipelines."
        }
        </script>
      </head>
      <body><div>Career Page</div></body>
    </html>
    """
    profile = load_profile()

    call_log = []

    def mock_llm(sys_p: str, user_p: str) -> str:
        call_log.append((sys_p, user_p))
        return json.dumps({
            "company_summary": "Stripe is a financial infrastructure platform for the internet.",
            "why_company_answer": "I am passionate about building scalable financial AI systems.",
            "culture_mission_match": "High ownership and rigor in distributed production systems."
        })

    budget = LLMBudgetManager(min_calls=1, max_calls=2, llm_fn=mock_llm)
    job_ctx = prepare_job_context(
        job_url="https://jobs.lever.co/stripe/123",
        candidate_profile=profile,
        html_content=mock_html,
        budget_manager=budget,
    )

    # Assert budget condition: exactly 1 call
    assert budget.call_count == 1
    assert job_ctx["llm_call_count"] == 1
    assert "Stripe" in job_ctx["company_name"]
    assert "Senior AI Systems Engineer" in job_ctx["job_description"]
    assert "financial infrastructure" in job_ctx["company_summary"]


def test_fallback_path_budget_exactly_two_calls():
    """
    When the HTML is messy/obfuscated and lacks JSON-LD or standard selectors:
    Call 1: Fallback JD extraction from raw page text.
    Call 2: Synthesis of company profile and alignment.
    Total calls must equal 2.
    """
    mock_messy_html = """
    <html>
      <head><title>Careers Portal</title></head>
      <body>
        <div class="obscure-wrapper-77">
           Some minimal unparsed text without standard markers.
        </div>
      </body>
    </html>
    """
    profile = load_profile()

    calls = []

    def mock_two_step_llm(sys_p: str, user_p: str) -> str:
        calls.append((sys_p, user_p))
        if len(calls) == 1:
            # Call 1: JD Extraction response
            return "Job Title: Full Stack Developer\nResponsibilities: Build React and Node.js applications."
        else:
            # Call 2: Company Profile Synthesis response
            return json.dumps({
                "company_summary": "Innovative SaaS provider.",
                "why_company_answer": "Eager to contribute full-stack skills to build great products.",
                "culture_mission_match": "User-centric iteration."
            })

    budget = LLMBudgetManager(min_calls=1, max_calls=2, llm_fn=mock_two_step_llm)
    job_ctx = prepare_job_context(
        job_url="https://boards.greenhouse.io/acme/jobs/99",
        candidate_profile=profile,
        html_content=mock_messy_html,
        budget_manager=budget,
    )

    # Assert budget condition: exactly 2 calls
    assert budget.call_count == 2
    assert job_ctx["llm_call_count"] == 2
    assert "Full Stack Developer" in job_ctx["job_description"]
    assert "Innovative SaaS" in job_ctx["company_summary"]


def test_budget_guardrails():
    """Verify that manager raises errors when min_calls or max_calls are violated."""
    # Underflow check: 0 calls made
    budget = LLMBudgetManager(min_calls=1, max_calls=2, llm_fn=lambda s, u: "ok")
    try:
        budget.verify()
        assert False, "Expected LLMBudgetUnderflowError"
    except LLMBudgetUnderflowError:
        pass

    # Overflow check: attempted 3 calls
    budget2 = LLMBudgetManager(min_calls=1, max_calls=2, llm_fn=lambda s, u: "ok")
    budget2.call("sys", "user1")
    budget2.call("sys", "user2")
    try:
        budget2.call("sys", "user3")
        assert False, "Expected LLMBudgetExceededError"
    except LLMBudgetExceededError:
        pass


def test_build_task_with_company_intelligence():
    profile = load_profile()
    company_context = {
        "company_name": "Datadog",
        "company_summary": "Cloud observability and monitoring platform.",
        "why_company_answer": "I want to apply my backend and distributed systems experience to observability at scale.",
        "culture_mission_match": "Passion for reliable engineering infrastructure.",
    }
    task = build_task(
        profile=profile,
        job_url="https://boards.greenhouse.io/datadog/jobs/123",
        job_description="Python, distributed systems, monitoring engineer",
        company_context=company_context,
    )

    assert "COMPANY INTELLIGENCE & SCREENING ALIGNMENT:" in task
    assert "Datadog" in task
    assert "Cloud observability" in task
    assert "Why do you want to work at Datadog?" in task
    assert "Stop as soon as you reach the final review or submit page" in task


def test_budget_verify_exceeded_error():
    import pytest
    budget = LLMBudgetManager(min_calls=1, max_calls=2, llm_fn=lambda s, u: "ok")
    budget.call_count = 5
    with pytest.raises(LLMBudgetExceededError):
        budget.verify()


def test_default_llm_call_openrouter():
    import os
    from unittest.mock import patch, MagicMock
    from jd_extractor import default_llm_call

    with patch.dict(os.environ, {"OPENROUTER_API_KEY": "fake_openrouter"}, clear=True):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"choices": [{"message": {"content": "openrouter response"}}]}).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        with patch("urllib.request.urlopen", return_value=mock_resp):
            res = default_llm_call("sys", "user")
            assert res == "openrouter response"


def test_default_llm_call_openrouter_error_fallback():
    import os
    from unittest.mock import patch
    from jd_extractor import default_llm_call

    with patch.dict(os.environ, {"OPENROUTER_API_KEY": "fake_openrouter"}, clear=True):
        with patch("urllib.request.urlopen", side_effect=Exception("Network error")):
            res = default_llm_call("sys", "user")
            assert "company_summary" in res


def test_default_llm_call_anthropic():
    import os
    from unittest.mock import patch, MagicMock
    from jd_extractor import default_llm_call

    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "fake_anthropic"}, clear=True):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"content": [{"text": "anthropic response"}]}).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        with patch("urllib.request.urlopen", return_value=mock_resp):
            res = default_llm_call("sys", "user")
            assert res == "anthropic response"


def test_default_llm_call_anthropic_error_fallback():
    import os
    from unittest.mock import patch
    from jd_extractor import default_llm_call

    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "fake_anthropic"}, clear=True):
        with patch("urllib.request.urlopen", side_effect=Exception("Network error")):
            res = default_llm_call("sys", "user")
            assert "company_summary" in res


def test_default_llm_call_offline():
    import os
    from unittest.mock import patch
    from jd_extractor import default_llm_call

    with patch.dict(os.environ, {}, clear=True):
        res = default_llm_call("sys", "user")
        data = json.loads(res)
        assert "why_company_answer" in data


def test_fetch_url():
    from unittest.mock import patch, MagicMock
    from jd_extractor import fetch_url

    mock_resp = MagicMock()
    mock_resp.read.return_value = b"<html>content</html>"
    mock_resp.__enter__.return_value = mock_resp
    with patch("urllib.request.urlopen", return_value=mock_resp):
        html = fetch_url("https://example.com/test")
        assert "content" in html


def test_extract_json_ld_variants():
    # List format
    html_list = '<script type="application/ld+json">[{"@type": "JobPosting", "title": "Dev"}]</script>'
    assert extract_json_ld(html_list)["title"] == "Dev"

    # Graph format
    html_graph = '<script type="application/ld+json">{"@graph": [{"@type": "JobPosting", "title": "Architect"}]}</script>'
    assert extract_json_ld(html_graph)["title"] == "Architect"

    # Invalid JSON
    html_invalid = '<script type="application/ld+json">invalid json</script>'
    assert extract_json_ld(html_invalid) is None

    # No JSON-LD
    assert extract_json_ld("<html>no json ld</html>") is None


def test_extract_company_name_variants():
    # String hiringOrganization
    assert extract_company_name("https://example.com", "", {"hiringOrganization": "String Corp"}) == "String Corp"

    # Ashby
    assert extract_company_name("https://jobs.ashbyhq.com/scale-ai/123", "") == "Scale Ai"

    # SmartRecruiters
    assert extract_company_name("https://careers.smartrecruiters.com/bosch/123", "") == "Bosch"

    # Title with 'at'
    html_at = "<title>Software Engineer at Acme Corp | Jobs</title>"
    assert extract_company_name("https://jobs.example.com/1", html_at) == "Acme Corp"

    # Title with dash
    html_dash = "<title>Software Engineer - Global Tech</title>"
    assert extract_company_name("https://jobs.example.com/1", html_dash) == "Global Tech"

    # Fallback host
    assert extract_company_name("https://www.uber.com/careers/123", "<title>Careers</title>") == "Uber"


def test_extract_company_about_web_variants():
    from unittest.mock import patch, MagicMock

    assert extract_company_about_web("") == ""

    # Wikipedia exception, DuckDuckGo success
    mock_ddg = MagicMock()
    mock_ddg.read.return_value = json.dumps({"AbstractText": "DDG summary of tech company."}).encode("utf-8")
    mock_ddg.__enter__.return_value = mock_ddg

    def side_effect_req(req, *args, **kwargs):
        if "wikipedia" in req.full_url:
            raise Exception("Wiki down")
        return mock_ddg

    with patch("urllib.request.urlopen", side_effect=side_effect_req):
        about = extract_company_about_web("SomeOrg Inc.")
        assert "DDG summary" in about

    # Both fail -> default string
    with patch("urllib.request.urlopen", side_effect=Exception("All down")):
        about_fallback = extract_company_about_web("FallbackCorp")
        assert "FallbackCorp is a technology organization" in about_fallback


def test_extract_script_jd_variants():
    # JSON-LD with skills
    json_ld = {
        "title": "Engineer",
        "description": "A" * 150,
        "skills": "Python, Docker",
        "responsibilities": "Building things",
        "qualifications": "BS degree",
    }
    jd = extract_script_jd("<html></html>", json_ld)
    assert jd is not None
    assert "Skills: Python, Docker" in jd

    # Known portal selector: job-description class
    portal_html = f'<div class="job-description">Responsibilities and requirements: {"details " * 40}</div>'
    res = extract_script_jd(portal_html, None)
    assert res is not None
    assert "Responsibilities" in res

    # Body match
    body_html = f'<body>responsibilities requirements qualifications what you\'ll do {"text " * 60}</body>'
    res_body = extract_script_jd(body_html, None)
    assert res_body is not None
    assert "responsibilities" in res_body


def test_prepare_job_context_fetch_and_synthesis_fallbacks():
    from unittest.mock import patch
    profile = load_profile()

    # 1. html_content is None -> triggers fetch_url
    with patch("jd_extractor.fetch_url", return_value="<html><body>Short</body></html>"):
        budget = LLMBudgetManager(min_calls=1, max_calls=2, llm_fn=lambda s, u: "not json")
        ctx = prepare_job_context("https://example.com/job", profile, html_content=None, budget_manager=budget)
        assert ctx["company_name"] == "Example"
        assert "why_company_answer" in ctx

    # 2. fetch_url raises Exception
    with patch("jd_extractor.fetch_url", side_effect=Exception("Failed to fetch")):
        budget = LLMBudgetManager(min_calls=1, max_calls=2, llm_fn=lambda s, u: '{"why_company_answer": "custom"}')
        ctx = prepare_job_context("https://example.com/job", profile, html_content=None, budget_manager=budget)
        assert "why_company_answer" in ctx


if __name__ == "__main__":
    test_company_name_extraction()
    test_company_about_wikipedia_lookup()
    test_happy_path_budget_exactly_one_call()
    test_fallback_path_budget_exactly_two_calls()
    test_budget_guardrails()
    test_build_task_with_company_intelligence()
    test_budget_verify_exceeded_error()
    test_default_llm_call_openrouter()
    test_default_llm_call_openrouter_error_fallback()
    test_default_llm_call_anthropic()
    test_default_llm_call_anthropic_error_fallback()
    test_default_llm_call_offline()
    test_fetch_url()
    test_extract_json_ld_variants()
    test_extract_company_name_variants()
    test_extract_company_about_web_variants()
    test_extract_script_jd_variants()
    test_prepare_job_context_fetch_and_synthesis_fallbacks()
    print("All extractor and budget manager tests passed successfully!")

