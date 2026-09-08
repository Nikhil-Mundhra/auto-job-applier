"""
Relevance matcher and portfolio curator.
Matches portfolio experiences, projects, and skills to a target job description
so the browser agent receives a concise, highly relevant subset of profile data.
"""

from __future__ import annotations

import re
import urllib.parse
from typing import Any

# Multi-word technology and domain phrases to detect in job descriptions
KNOWN_PHRASES = [
    "machine learning",
    "deep learning",
    "artificial intelligence",
    "computer vision",
    "full stack",
    "frontend",
    "front end",
    "backend",
    "back end",
    "data science",
    "data analysis",
    "data engineering",
    "system design",
    "rest api",
    "restful api",
    "graphql",
    "next.js",
    "next js",
    "react",
    "react.js",
    "react native",
    "node.js",
    "node js",
    "tailwind css",
    "tailwind",
    "mongo db",
    "mongodb",
    "mongodb atlas",
    "cloud directory",
    "google apps script",
    "cyber security",
    "cybersecurity",
    "network segmentation",
    "iec 62443",
    "ot security",
    "systems engineering",
    "image segmentation",
    "retinal imaging",
    "fraud detection",
    "rule engine",
    "wopi",
    "llm",
    "large language model",
    "gnn",
    "graph neural network",
    "cnn",
    "convolutional neural network",
    "pytorch",
    "docker",
    "kubernetes",
    "github actions",
    "ci/cd",
    "azure devops",
    "aws",
    "cloudflare",
    "vercel",
    "microservices",
    "distributed systems",
    "web3",
    "fintech",
    "compliance",
    "kyc/aml",
    "e-commerce",
    "digital marketing",
]

# Single-word keywords to match accurately
TECH_KEYWORDS = {
    "python", "javascript", "typescript", "c++", "c", "java", "sql", "r",
    "stata", "html", "css", "flask", "django", "express", "fastapi", "vue",
    "react", "vite", "astro", "capacitor", "sentry", "posthog", "linux",
    "git", "etl", "parquet", "api", "apis", "wopi", "jwt", "nosql", "devops",
    "security", "testing", "qa", "debugging", "founder", "lead", "architect"
}


def get_resume_skills_set(profile: dict) -> set[str]:
    """Extract all skills, technologies, frameworks, and tools present in candidate profile."""
    skills_set: set[str] = set()
    for cat, items in profile.get("skills", {}).items():
        if isinstance(items, list):
            for it in items:
                skills_set.add(it.strip().lower())
    for exp in profile.get("work_history", []):
        for tag in exp.get("skill_tags", []):
            skills_set.add(tag.strip().lower())
        for dom in exp.get("domains", []):
            skills_set.add(dom.strip().lower())
    for proj in profile.get("projects", []):
        for tag in proj.get("skill_tags", []):
            skills_set.add(tag.strip().lower())
        for dom in proj.get("domains", []):
            skills_set.add(dom.strip().lower())
    return skills_set


def extract_salary_range(text: str) -> Optional[tuple[float, float, str]]:
    """
    Extracts minimum and maximum compensation and currency symbol from text.
    Handles ranges like '$100,000 - $190,000', '$100k - $190k', '₹10 LPA - ₹18 LPA', etc.
    """
    if not text:
        return None
    cleaned = text.replace(",", "")
    pattern = r"(\$|₹|€|£)\s*(\d+(?:\.\d+)?)\s*(?:k|thousand)?\s*(?:-|to|–)\s*(?:\$|₹|€|£)?\s*(\d+(?:\.\d+)?)\s*(k|thousand|lpa|lakh)?"
    m = re.search(pattern, cleaned, re.IGNORECASE)
    if m:
        sym = m.group(1)
        low = float(m.group(2))
        high = float(m.group(3))
        unit = (m.group(4) or "").lower()
        if "k" in unit or (low < 500 and high < 500 and sym in ["$", "€", "£"]):
            low *= 1000
            high *= 1000
        elif "lpa" in unit or "lakh" in unit:
            low *= 100000
            high *= 100000
        return low, high, sym
    return None


def calculate_desired_salary(
    job_text: str = "",
    region: str = "uae",
    numeric_only: bool = False,
    is_hourly: bool = False,
) -> str:
    """
    Calculates desired salary nearer to the upper end of the role compensation range.
    If a range is detected (e.g. $100k - $190k or $25 - $45/hr), picks ~85% toward the max.
    If no range is detected, picks standard competitive upper quartile for region.
    """
    range_info = extract_salary_range(job_text)
    if is_hourly:
        if range_info and range_info[1] <= 500:
            low, high, sym = range_info
            target = round(low + 0.85 * (high - low))
            if numeric_only:
                return str(int(target))
            return f"{sym}{int(target)}/hour"
        if region == "india":
            return "600" if numeric_only else "₹600 / hour"
        return "45" if numeric_only else "$45 / hour"

    if range_info:
        low, high, sym = range_info
        target = low + 0.85 * (high - low)
        if target >= 50000:
            target = round(target / 5000) * 5000
        else:
            target = round(target / 1000) * 1000
        if numeric_only:
            return str(int(target))
        if sym == "$":
            return f"${int(target):,}"
        elif sym == "₹":
            return f"₹{int(target):,}"
        return f"{sym}{int(target):,}"

    if region == "india":
        return "1800000" if numeric_only else "₹18,00,000 / year (open to discussion)"
    return "120000" if numeric_only else "$120,000 / year (open to discussion)"


def get_tool_experience(
    tool_name: str,
    profile: dict,
    numeric_only: bool = False,
    expects_months: bool = False,
) -> str:
    """
    Returns experience for a tool/framework.
    If found in resume: returns actual experience (2 years).
    If NOT found in resume: returns 1 year (or 6 months depending on input type).
    """
    skills_set = get_resume_skills_set(profile)
    cleaned_tool = re.sub(r"[\*\:\?]+$", "", tool_name).strip().lower()

    found = False
    for s in skills_set:
        s_clean = s.strip().lower()
        pat = r"(?:^|[^\w\+\#])" + re.escape(s_clean) + r"(?:$|[^\w\+\#])"
        if re.search(pat, cleaned_tool):
            found = True
            break

    if found:
        return "2" if numeric_only else ("24 months" if expects_months else "2 years")

    # Unlisted tool/framework rule: 1 year or 6 months depending on input type
    if expects_months:
        return "6" if numeric_only else "6 months"
    return "1" if numeric_only else "1 year"


def normalize_token(token: str) -> str:
    """Normalize a token by stripping non-alphanumeric chars except dots/pluses."""
    return token.strip().lower().strip(".,;:()[]{}'\"")


def extract_keywords(job_text: str) -> set[str]:
    """
    Extract technical skills, tools, roles, and domain terms from a job description.
    """
    if not job_text:
        return set()

    job_text_lower = job_text.lower()
    matched_keywords: set[str] = set()

    # Match multi-word known phrases
    for phrase in KNOWN_PHRASES:
        if phrase in job_text_lower:
            matched_keywords.add(phrase)
            # Add individual significant words from phrase as well
            for word in phrase.split():
                if len(word) > 2:
                    matched_keywords.add(word)

    # Word-level tokenization
    tokens = re.findall(r"[\w\+\#\.]+", job_text_lower)
    for token in tokens:
        clean = normalize_token(token)
        if clean in TECH_KEYWORDS:
            matched_keywords.add(clean)
        elif len(clean) >= 3 and not clean.isdigit():
            matched_keywords.add(clean)

    return matched_keywords


def score_text_against_keywords(text: str, keywords: set[str]) -> tuple[float, list[str]]:
    """Return matching count and list of matched keywords in text."""
    if not text or not keywords:
        return 0.0, []

    text_lower = text.lower()
    hits: list[str] = []
    score = 0.0

    for kw in keywords:
        if kw in text_lower:
            # Word boundary check for short words to avoid false positives (e.g., 'c' in 'cat')
            if len(kw) <= 2:
                pattern = r"(?:\b|_)" + re.escape(kw) + r"(?:\b|_)"
                if re.search(pattern, text_lower):
                    hits.append(kw)
                    score += 1.0
            else:
                hits.append(kw)
                score += 1.0

    return score, hits


def score_experience(exp: dict[str, Any], jd_keywords: set[str], job_text_lower: str) -> tuple[float, list[str], list[str]]:
    """
    Score an individual work experience against the job description.
    Returns:
        (total_score, matched_skills_or_domains, curated_duties)
    """
    matched_terms: set[str] = set()
    score = 0.0

    # 1. Match skill tags (highest weight: 3.5 per match)
    skill_tags = [s.lower() for s in exp.get("skill_tags", [])]
    for tag in skill_tags:
        if tag in jd_keywords or tag in job_text_lower:
            score += 3.5
            matched_terms.add(tag)

    # 2. Match domains (high weight: 2.5 per match)
    domains = [d.lower() for d in exp.get("domains", [])]
    for domain in domains:
        if domain in jd_keywords or domain in job_text_lower:
            score += 2.5
            matched_terms.add(domain)

    # 3. Match title and company (weight: 2.0)
    title = exp.get("title", "").lower()
    title_score, title_hits = score_text_against_keywords(title, jd_keywords)
    score += title_score * 2.0
    matched_terms.update(title_hits)

    # 4. Score and sort individual duties
    duties = exp.get("duties", [])
    scored_duties: list[tuple[float, str]] = []
    for duty in duties:
        duty_score, duty_hits = score_text_against_keywords(duty, jd_keywords)
        scored_duties.append((duty_score, duty))
        matched_terms.update(duty_hits)
        score += duty_score * 1.2

    # Prioritize duties with highest keyword overlap, preserving original order as secondary key
    scored_duties.sort(key=lambda item: item[0], reverse=True)
    curated_duties = [d for _, d in scored_duties]

    # 5. Slight recency bonus for tie-breaking
    start_date = exp.get("start_date", "")
    end_date = exp.get("end_date", "").lower()
    if "present" in end_date:
        score += 1.0
    elif "2026" in end_date or "2026" in start_date:
        score += 0.8
    elif "2025" in end_date or "2025" in start_date:
        score += 0.4

    return score, sorted(matched_terms), curated_duties


def score_project(proj: dict[str, Any], jd_keywords: set[str], job_text_lower: str) -> tuple[float, list[str]]:
    """Score an individual project against the job description."""
    matched_terms: set[str] = set()
    score = 0.0

    skill_tags = [s.lower() for s in proj.get("skill_tags", [])]
    for tag in skill_tags:
        if tag in jd_keywords or tag in job_text_lower:
            score += 3.0
            matched_terms.add(tag)

    domains = [d.lower() for d in proj.get("domains", [])]
    for domain in domains:
        if domain in jd_keywords or domain in job_text_lower:
            score += 2.0
            matched_terms.add(domain)

    name_desc = (proj.get("name", "") + " " + proj.get("description", "")).lower()
    desc_score, desc_hits = score_text_against_keywords(name_desc, jd_keywords)
    score += desc_score * 1.0
    matched_terms.update(desc_hits)

    return score, sorted(matched_terms)


def detect_application_region(job_description: str = "", job_url: str = "") -> str:
    """
    Detect whether the application is targeting an India-based position or an
    international / UAE / US position.
    Returns 'india' or 'uae' (default for UAE, US, and international).
    """
    url_text = job_url.lower() if job_url else ""
    jd_text = job_description.lower() if job_description else ""

    # Strip occurrences of Indiana / Indianapolis with boundary checks
    url_cleaned = re.sub(r"(?:^|[/_\-\.\s])(indiana|indianapolis)(?:$|[/_\-\.\s])", " ", url_text)
    jd_cleaned = re.sub(r"\b(indiana|indianapolis)\b", " ", jd_text)

    # 1. URL checks
    if job_url:
        parsed = urllib.parse.urlparse(job_url)
        domain = parsed.netloc.lower()
        if domain.endswith(".in") or ".co.in" in domain:
            return "india"

        # Match exact 'india' token in URL (e.g. /Mumbai-India/, India-Bangalore)
        if re.search(r"(?:^|[/_\-\.])india(?:$|[/_\-\.])", url_cleaned):
            return "india"

        # Match exact Indian cities in URL path
        india_cities_url_pat = r"(?:^|[/_\-\.])(bengaluru|bangalore|hyderabad|mumbai|pune|noida|gurgaon|gurugram|chennai|kolkata|delhi|new-delhi)(?:$|[/_\-\.])"
        if re.search(india_cities_url_pat, url_cleaned):
            return "india"

    # 2. Check explicit Location / Workplace / Office lines in JD
    location_headers = re.findall(
        r"(?:location|location\(s\)|workplace|based in|office in|office location|job location|country)\s*[:\-–]\s*([^\n\r\.;]+)",
        jd_cleaned,
    )
    for header in location_headers:
        # Check if header explicitly specifies India or Indian cities
        if re.search(r"\b(india|bengaluru|bangalore|delhi|new delhi|hyderabad|mumbai|pune|noida|gurgaon|gurugram|chennai|kolkata)\b", header):
            return "india"
        # If header specifies US / UAE / UK / Europe / Canada / etc., return uae immediately
        if re.search(r"\b(united states|usa|us|virginia|va|california|ca|new york|ny|texas|tx|maryland|md|washington|dc|abu dhabi|dubai|uae|united arab emirates|london|uk|canada|germany)\b", header):
            return "uae"

    # 3. Text-level check: look for Indian cities / country
    india_patterns = [
        r"\bindia\b",
        r"\bbengaluru\b",
        r"\bbangalore\b",
        r"\bnew delhi\b",
        r"\bhyderabad\b",
        r"\bmumbai\b",
        r"\bpune\b",
        r"\bnoida\b",
        r"\bgurgaon\b",
        r"\bgurugram\b",
        r"\bchennai\b",
        r"\bkolkata\b",
    ]
    has_india = any(re.search(pat, jd_cleaned) for pat in india_patterns)
    if has_india:
        # Check for overriding non-India signals
        us_intl_patterns = [
            r"\bus citizen\b",
            r"\bus citizenship\b",
            r"\bunited states\b",
            r"\bsecurity clearance\b",
            r"\bclearance required\b",
            r"\babu dhabi\b",
            r"\bdubai\b",
            r"\bunited arab emirates\b",
        ]
        if any(re.search(pat, jd_cleaned) for pat in us_intl_patterns):
            return "uae"
        return "india"

    return "uae"


def curate_profile(
    profile: dict[str, Any],
    job_description: str = "",
    job_url: str = "",
    max_experiences: int = 3,
    max_projects: int = 2,
    max_duties_per_exp: int = 4,
) -> dict[str, Any]:
    """
    Curate a lean, job-tailored subset of the user profile.

    If job_description is provided:
        - Extracts keywords and scores each experience & project.
        - Ranks experiences by relevance and keeps the top `max_experiences`.
        - Reorders duties in each experience to put matching points first.
        - Ranks projects and keeps top `max_projects`.
        - Reorganizes skills to prioritize matched technologies.
        - Injects tailoring metadata for transparency and agent reasoning.

    Dynamically selects candidate address and phone number:
        - India address and secondary phone for India roles.
        - NYU Abu Dhabi address and primary phone for UAE, US, and international roles.
    """
    target_region = detect_application_region(job_description=job_description, job_url=job_url)
    addresses = profile.get("addresses", {})

    if target_region == "india" and "india" in addresses:
        selected_address = addresses["india"]
        selected_phone = profile.get("secondary_phone", "+91 7060410033")
        selected_location = "New Delhi, India"
    else:
        selected_address = addresses.get("uae", {
            "street_address": "New York University Abu Dhabi, Saadiyat Island, P.O. Box 129188",
            "address_line1": "New York University Abu Dhabi, Saadiyat Island",
            "address_line2": "P.O. Box 129188",
            "city": "Abu Dhabi",
            "state_province": "Abu Dhabi",
            "postal_code": "129188",
            "country": "United Arab Emirates",
            "formatted": "New York University Abu Dhabi, Saadiyat Island, P.O. Box 129188, Abu Dhabi, United Arab Emirates",
        })
        selected_phone = profile.get("phone", "+971 503526342")
        selected_location = "Abu Dhabi, United Arab Emirates"

    curated: dict[str, Any] = {
        "full_name": profile.get("full_name", ""),
        "gender": profile.get("gender", "Male"),
        "ethnicity": profile.get("ethnicity", "North Indian"),
        "nationality": profile.get("nationality", "Indian"),
        "date_of_birth": profile.get("date_of_birth", "28/10/2005"),
        "dob_iso": profile.get("dob_iso", "2005-10-28"),
        "dob_day": profile.get("dob_day", "28"),
        "dob_month": profile.get("dob_month", "10"),
        "dob_year": profile.get("dob_year", "2005"),
        "email": profile.get("email", ""),
        "phone": selected_phone,
        "location": selected_location,
        "target_region": target_region,
        "address": selected_address,
        "addresses": addresses,
        "resume_path": profile.get("resume_path", ""),
        "linkedin": profile.get("linkedin", ""),
        "github": profile.get("github", ""),
        "portfolio_website": profile.get("portfolio_website", ""),
        "summary": profile.get("summary", ""),
        "education": profile.get("education", []),
        "screening_preferences": profile.get("screening_preferences", {}),
    }

    raw_experiences = profile.get("work_history", [])
    raw_projects = profile.get("projects", [])
    raw_skills = profile.get("skills", {})

    if not job_description or not job_description.strip():
        # Default fallback: take top experiences and projects chronologically
        selected_experiences = []
        for exp in raw_experiences[:max_experiences]:
            exp_copy = dict(exp)
            exp_copy["duties"] = exp_copy.get("duties", [])[:max_duties_per_exp]
            selected_experiences.append(exp_copy)

        curated["work_history"] = selected_experiences
        curated["projects"] = raw_projects[:max_projects]
        curated["skills"] = raw_skills
        curated["tailoring_summary"] = {
            "mode": "default",
            "reason": "No job description provided; using primary recent experiences."
        }
        return curated

    # Job description provided: run keyword matching & scoring
    jd_keywords = extract_keywords(job_description)
    job_text_lower = job_description.lower()

    # 1. Score and rank work experiences
    scored_exps = []
    for exp in raw_experiences:
        score, matched_terms, curated_duties = score_experience(exp, jd_keywords, job_text_lower)
        exp_copy = dict(exp)
        exp_copy["duties"] = curated_duties[:max_duties_per_exp]
        exp_copy["_relevance_score"] = round(score, 2)
        exp_copy["_matched_keywords"] = matched_terms
        scored_exps.append((score, exp_copy))

    scored_exps.sort(key=lambda item: item[0], reverse=True)
    selected_experiences = [exp for _, exp in scored_exps[:max_experiences]]

    # 2. Score and rank projects
    scored_projs = []
    for proj in raw_projects:
        score, matched_terms = score_project(proj, jd_keywords, job_text_lower)
        proj_copy = dict(proj)
        proj_copy["_relevance_score"] = round(score, 2)
        proj_copy["_matched_keywords"] = matched_terms
        scored_projs.append((score, proj_copy))

    scored_projs.sort(key=lambda item: item[0], reverse=True)
    selected_projects = [proj for _, proj in scored_projs[:max_projects]]

    # 3. Curate skills: place matching skills at the top of each category
    curated_skills: dict[str, list[str]] = {}
    total_matched_skills: list[str] = []

    for category, skill_list in raw_skills.items():
        if isinstance(skill_list, list):
            matched = []
            unmatched = []
            for skill in skill_list:
                skill_lower = skill.lower()
                if skill_lower in jd_keywords or skill_lower in job_text_lower:
                    matched.append(skill)
                    total_matched_skills.append(skill)
                else:
                    unmatched.append(skill)
            curated_skills[category] = matched + unmatched
        else:
            curated_skills[category] = skill_list

    curated["work_history"] = selected_experiences
    curated["projects"] = selected_projects
    curated["skills"] = curated_skills

    all_matched = sorted(set(
        total_matched_skills +
        [kw for exp in selected_experiences for kw in exp.get("_matched_keywords", [])] +
        [kw for proj in selected_projects for kw in proj.get("_matched_keywords", [])]
    ))

    curated["tailoring_summary"] = {
        "mode": "tailored",
        "matched_keywords_count": len(all_matched),
        "key_matches": all_matched[:15],
        "selected_roles": [f"{e.get('title')} at {e.get('company')}" for e in selected_experiences],
        "selected_projects": [p.get("name") for p in selected_projects],
    }

    return curated
