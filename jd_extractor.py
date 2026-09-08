"""
Automated Job Description & Company Intelligence Extractor.
Extracts job descriptions and company background from URLs and web sources.
Guarantees strict LLM call budget: minimum 1 call, at most 2 calls.
"""

from __future__ import annotations

import html
import json
import os
import re
import urllib.parse
import urllib.request
from typing import Any, Callable, Optional


class LLMBudgetExceededError(RuntimeError):
    """Raised when LLM calls exceed the permitted maximum budget."""
    pass


class LLMBudgetUnderflowError(RuntimeError):
    """Raised when LLM calls are below the permitted minimum budget."""
    pass


class LLMBudgetManager:
    """
    Strictly manages and enforces the LLM API call budget.
    Ensures: min_calls <= call_count <= max_calls.
    """
    def __init__(self, min_calls: int = 1, max_calls: int = 2, llm_fn: Optional[Callable[[str, str], str]] = None):
        self.min_calls = min_calls
        self.max_calls = max_calls
        self.call_count = 0
        self._llm_fn = llm_fn or default_llm_call

    def call(self, system_prompt: str, user_prompt: str) -> str:
        if self.call_count >= self.max_calls:
            raise LLMBudgetExceededError(
                f"LLM call budget exceeded: attempted call #{self.call_count + 1} "
                f"but maximum permitted is {self.max_calls}."
            )
        self.call_count += 1
        return self._llm_fn(system_prompt, user_prompt)

    def verify(self) -> None:
        if self.call_count < self.min_calls:
            raise LLMBudgetUnderflowError(
                f"LLM call budget underflow: made {self.call_count} calls, "
                f"minimum required is {self.min_calls}."
            )
        if self.call_count > self.max_calls:
            raise LLMBudgetExceededError(
                f"LLM call budget exceeded: made {self.call_count} calls, "
                f"maximum permitted is {self.max_calls}."
            )


def default_llm_call(system_prompt: str, user_prompt: str) -> str:
    """
    Direct HTTPS LLM caller via OpenRouter or Anthropic.
    Falls back gracefully if keys are absent or network unavailable.
    """
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")

    if openrouter_key:
        try:
            model_name = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
            payload = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.2,
                "max_tokens": 1500,
            }
            req = urllib.request.Request(
                "https://openrouter.ai/api/v1/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {openrouter_key}",
                    "Content-Type": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"⚠️ OpenRouter API error ({e}). Checking alternative...")

    if anthropic_key:
        try:
            payload = {
                "model": "claude-3-7-sonnet-20250219",
                "max_tokens": 1500,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}],
                "temperature": 0.2,
            }
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "x-api-key": anthropic_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["content"][0]["text"]
        except Exception as e:
            print(f"⚠️ Anthropic API error ({e}).")

    # Graceful offline synthesis if keys are unpaid or rate-limited
    return json.dumps({
        "company_summary": "Technology and engineering organization.",
        "why_company_answer": "I am eager to leverage my engineering and AI experience to contribute to high-impact challenges.",
        "culture_mission_match": "Dedication to high code quality and user-focused engineering."
    })


def strip_html_tags(text: str) -> str:
    """Remove HTML tags and decode HTML entities."""
    clean = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
    clean = re.sub(r"<script[\s\S]*?</script>", " ", clean, flags=re.IGNORECASE)
    clean = re.sub(r"<nav[\s\S]*?</nav>", " ", clean, flags=re.IGNORECASE)
    clean = re.sub(r"<footer[\s\S]*?</footer>", " ", clean, flags=re.IGNORECASE)
    clean = re.sub(r"<header[\s\S]*?</header>", " ", clean, flags=re.IGNORECASE)
    clean = re.sub(r"<[^>]+>", " ", clean)
    clean = html.unescape(clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def fetch_url(url: str, timeout: int = 10) -> str:
    """Fetch raw HTML content using standard browser headers."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def extract_json_ld(html_text: str) -> Optional[dict[str, Any]]:
    """Extract Schema.org JobPosting JSON-LD object if present."""
    matches = re.findall(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>([\s\S]*?)</script>',
        html_text,
        flags=re.IGNORECASE,
    )
    for match in matches:
        try:
            data = json.loads(match.strip())
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get("@type") == "JobPosting":
                        return item
            elif isinstance(data, dict):
                if data.get("@type") == "JobPosting":
                    return data
                if "@graph" in data and isinstance(data["@graph"], list):
                    for item in data["@graph"]:
                        if isinstance(item, dict) and item.get("@type") == "JobPosting":
                            return item
        except Exception:
            continue
    return None


def extract_company_name(url: str, html_text: str, json_ld: Optional[dict[str, Any]] = None) -> str:
    """
    Deduce company name from JSON-LD, URL slug patterns, or page title.
    """
    # 1. From JSON-LD
    if json_ld:
        hiring_org = json_ld.get("hiringOrganization")
        if isinstance(hiring_org, dict) and hiring_org.get("name"):
            return hiring_org["name"].strip()
        if isinstance(hiring_org, str) and hiring_org.strip():
            return hiring_org.strip()

    # 2. From common URL structures
    parsed = urllib.parse.urlparse(url)
    domain = parsed.netloc.lower()
    path_parts = [p for p in parsed.path.split("/") if p]

    # Greenhouse: boards.greenhouse.io/<company>/jobs/...
    if "greenhouse.io" in domain and path_parts:
        return path_parts[0].replace("-", " ").title()

    # Lever: jobs.lever.co/<company>/...
    if "lever.co" in domain and path_parts:
        return path_parts[0].replace("-", " ").title()

    # Workday: <company>.wd1.myworkdayjobs.com/...
    if "myworkdayjobs.com" in domain:
        subdomain = domain.split(".")[0]
        return subdomain.replace("-", " ").title()

    # Ashby: jobs.ashbyhq.com/<company>/...
    if "ashbyhq.com" in domain and path_parts:
        return path_parts[0].replace("-", " ").title()

    # SmartRecruiters: careers.smartrecruiters.com/<company>/...
    if "smartrecruiters.com" in domain and path_parts:
        return path_parts[0].replace("-", " ").title()

    # 3. From HTML Title regex (e.g., "Software Engineer at Datadog" or "Stripe Careers - Job")
    title_match = re.search(r"<title[^>]*>([\s\S]*?)</title>", html_text, flags=re.IGNORECASE)
    if title_match:
        title_text = title_match.group(1).strip()
        at_match = re.search(r"\bat\s+([A-Za-z0-9\s\.\,\-]+)(?:\||\-|$)", title_text, flags=re.IGNORECASE)
        if at_match:
            return at_match.group(1).strip()
        dash_match = re.search(r"(?:\||\-)\s*([A-Za-z0-9\s\.\,\-]+)$", title_text)
        if dash_match:
            candidate = dash_match.group(1).strip()
            if candidate.lower() not in ["careers", "jobs", "apply", "job board"]:
                return candidate

    # Fallback to domain host name
    clean_host = domain.replace("www.", "").split(".")[0]
    return clean_host.replace("-", " ").title()


def extract_company_about_web(company_name: str) -> str:
    """
    Fetch company summary from Wikipedia REST API or DuckDuckGo.
    """
    if not company_name or len(company_name) < 2:
        return ""

    # Clean company name of legal suffixes for better encyclopedia lookup
    clean_name = re.sub(r"\b(inc|corp|corporation|llc|ltd|pvt|limited)\b\.?", "", company_name, flags=re.IGNORECASE).strip()

    # 1. Wikipedia REST API
    try:
        wiki_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(clean_name)}"
        req = urllib.request.Request(wiki_url, headers={"User-Agent": "JobApplicationAgent/1.0"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            extract = data.get("extract", "")
            if extract and len(extract) > 50:
                return f"[Wikipedia Summary]: {extract}"
    except Exception:
        pass

    # 2. DuckDuckGo Instant Answer API
    try:
        ddg_url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(clean_name)}&format=json&no_html=1&skip_disambig=1"
        req = urllib.request.Request(ddg_url, headers={"User-Agent": "JobApplicationAgent/1.0"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            abstract = data.get("AbstractText", "")
            if abstract:
                return f"[Company Overview]: {abstract}"
    except Exception:
        pass

    return f"{company_name} is a technology organization."


def extract_script_jd(html_text: str, json_ld: Optional[dict[str, Any]]) -> Optional[str]:
    """
    Deterministic extraction of Job Description using JSON-LD or known portal selectors.
    Returns None if script extraction fails or text is insufficient.
    """
    # 1. JSON-LD Schema.org JobPosting
    if json_ld:
        title = json_ld.get("title", "")
        desc = json_ld.get("description", "")
        skills = json_ld.get("skills", "")
        qualifications = json_ld.get("qualifications", "")
        responsibilities = json_ld.get("responsibilities", "")

        parts = [f"Job Title: {title}"] if title else []
        if desc:
            parts.append(strip_html_tags(desc))
        if responsibilities:
            parts.append(f"Responsibilities: {strip_html_tags(str(responsibilities))}")
        if qualifications:
            parts.append(f"Qualifications: {strip_html_tags(str(qualifications))}")
        if skills:
            parts.append(f"Skills: {strip_html_tags(str(skills))}")

        combined = "\n\n".join(parts).strip()
        if len(combined) >= 200:
            return combined

    # 2. Known Portal Selectors regex
    known_patterns = [
        r'data-automation-id=["\']jobPostingDescription["\'][^>]*>([\s\S]*?)</div>',
        r'data-automation-id=["\']richPostingDescription["\'][^>]*>([\s\S]*?)</div>',
        r'id=["\']content["\'][^>]*>([\s\S]*?)</div>',
        r'class=["\'][^"\']*job-description[^"\']*["\'][^>]*>([\s\S]*?)</div>',
        r'class=["\'][^"\']*section-page[^"\']*["\'][^>]*>([\s\S]*?)</div>',
        r'<main[^>]*>([\s\S]*?)</main>',
        r'<article[^>]*>([\s\S]*?)</article>',
    ]
    for pat in known_patterns:
        match = re.search(pat, html_text, flags=re.IGNORECASE)
        if match:
            clean = strip_html_tags(match.group(1))
            # Validate that it has substantial length and common JD keywords
            if len(clean) >= 250 and re.search(r"\b(responsibilities|requirements|qualifications|experience|skills|role)\b", clean, flags=re.IGNORECASE):
                return clean

    # 3. Clean body text with high confidence check
    body_match = re.search(r"<body[^>]*>([\s\S]*?)</body>", html_text, flags=re.IGNORECASE)
    if body_match:
        clean_body = strip_html_tags(body_match.group(1))
        # If body is substantial and contains multiple key markers
        markers = ["responsibilities", "requirements", "qualifications", "what you'll do", "about you"]
        hit_count = sum(1 for m in markers if m in clean_body.lower())
        if hit_count >= 2 and len(clean_body) >= 300:
            return clean_body[:5000]

    return None


def prepare_job_context(
    job_url: str,
    candidate_profile: dict[str, Any],
    html_content: Optional[str] = None,
    budget_manager: Optional[LLMBudgetManager] = None,
) -> dict[str, Any]:
    """
    Automated pipeline that extracts the job description, company details,
    and synthesized alignment pitch.

    Enforces the LLM budget constraint:
        - 1 call: Happy path (script extracts JD, LLM synthesizes company & candidate alignment).
        - 2 calls: Fallback path (LLM extracts JD, then LLM synthesizes company & candidate alignment).
    """
    manager = budget_manager or LLMBudgetManager(min_calls=1, max_calls=2)

    # 1. Fetch HTML if not provided directly
    if html_content is None:
        try:
            html_content = fetch_url(job_url)
        except Exception as e:
            html_content = f"<html><body>Could not fetch URL directly: {e}</body></html>"

    # 2. Extract JSON-LD and Company Name (script-based, 0 LLM calls)
    json_ld = extract_json_ld(html_content)
    company_name = extract_company_name(job_url, html_content, json_ld)
    company_about_web = extract_company_about_web(company_name)

    # 3. Deterministic Script Extraction of Job Description
    job_description = extract_script_jd(html_content, json_ld)

    if not job_description:
        # Script failed -> LLM Call 1 (Fallback JD Extractor)
        clean_page_text = strip_html_tags(html_content)[:6000]
        jd_sys_prompt = (
            "You are an expert technical recruiter. Extract the job title, key responsibilities, "
            "required technical skills, and candidate qualifications from the following webpage text. "
            "Return a concise, structured job description."
        )
        jd_user_prompt = f"URL: {job_url}\nCompany: {company_name}\n\nPAGE CONTENT:\n{clean_page_text}"
        job_description = manager.call(jd_sys_prompt, jd_user_prompt)

    # 4. Mandatory LLM Call (Call 1 in happy path, Call 2 in fallback path)
    # Synthesizes Company Profile & Candidate Fit for screening questions
    candidate_highlights = {
        "name": candidate_profile.get("full_name"),
        "education": candidate_profile.get("education"),
        "top_skills": candidate_profile.get("skills", {}).get("programming_languages", [])[:6],
        "recent_roles": [e.get("title") + " at " + e.get("company") for e in candidate_profile.get("work_history", [])[:3]],
        "projects": [p.get("name") for p in candidate_profile.get("projects", [])[:2]],
    }

    company_sys_prompt = (
        "You are an executive career strategist helping a candidate apply to a company. "
        "Given the company information, job description, and candidate profile, produce a JSON object with:\n"
        "1. 'company_summary': 2-3 sentences summarizing what the company does, its core products, and mission.\n"
        "2. 'why_company_answer': A professional, genuine 3-4 sentence answer for the screening question "
        "'Why do you want to work at this company?' connecting the candidate's background to the company's work.\n"
        "3. 'culture_mission_match': 2 sentences highlighting alignment between candidate strengths and company mission.\n"
        "Respond ONLY with valid JSON."
    )
    company_user_prompt = (
        f"Company Name: {company_name}\n"
        f"Web/About Research: {company_about_web}\n\n"
        f"Job Description Excerpt:\n{job_description[:2000]}\n\n"
        f"Candidate Background:\n{json.dumps(candidate_highlights, indent=2)}"
    )

    synthesis_raw = manager.call(company_sys_prompt, company_user_prompt)

    # Parse JSON synthesis or fallback safely
    try:
        # Extract JSON substring if wrapped in markdown code fence
        json_match = re.search(r"\{[\s\S]*\}", synthesis_raw)
        if json_match:
            synthesis_data = json.loads(json_match.group(0))
        else:
            synthesis_data = json.loads(synthesis_raw)
    except Exception:
        synthesis_data = {
            "company_summary": company_about_web,
            "why_company_answer": f"I am excited to apply my engineering and AI experience to {company_name}'s mission.",
            "culture_mission_match": f"Strong alignment with {company_name}'s focus on high-impact technology.",
        }

    # Verify that the LLM budget was strictly respected: 1 <= call_count <= 2
    manager.verify()

    return {
        "company_name": company_name,
        "company_about_raw": company_about_web,
        "company_summary": synthesis_data.get("company_summary", company_about_web),
        "why_company_answer": synthesis_data.get("why_company_answer", ""),
        "culture_mission_match": synthesis_data.get("culture_mission_match", ""),
        "job_description": job_description,
        "llm_call_count": manager.call_count,
    }
