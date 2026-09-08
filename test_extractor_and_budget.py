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


if __name__ == "__main__":
    test_company_name_extraction()
    test_company_about_wikipedia_lookup()
    test_happy_path_budget_exactly_one_call()
    test_fallback_path_budget_exactly_two_calls()
    test_budget_guardrails()
    test_build_task_with_company_intelligence()
    print("All extractor and budget manager tests passed successfully!")
