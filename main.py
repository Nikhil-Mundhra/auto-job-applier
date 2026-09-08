"""
Local job application agent (macOS, single machine, no cloud infra needed)

Architecture, matching the three layer pattern:
  1. Semantic profile layer   -> profile.json
  2. Visual agentic loop      -> browser_use.Agent + ChatAnthropic (vision on)
  3. Human in the loop gate   -> the agent is instructed to stop before the
                                 final Submit / Apply click, and you review
                                 the open browser window yourself

Usage:
    python main.py "https://company.wd1.myworkdayjobs.com/en-US/careers/job/..."
    python main.py "https://jobs.example.com/apply/123" --headless
"""

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

load_dotenv()

from matcher import curate_profile
from jd_extractor import prepare_job_context
from resume_uploader import (
    get_validated_resume_path,
    create_resume_controller,
    attach_file_chooser_interceptor,
)
from cookie_handler import auto_accept_cookies, get_cookie_init_script
from browser_config import find_chromium_executable, get_browser_launch_args

PROFILE_PATH = Path(__file__).parent / "profile.json"


def load_profile() -> dict:
    with open(PROFILE_PATH, "r") as f:
        return json.load(f)


def build_task(
    profile: dict,
    job_url: str,
    job_description: str = "",
    company_context: Optional[dict] = None,
) -> str:
    """
    Curates the user profile to match the target job description (skills, roles,
    and duties), incorporates company intelligence, and ensures the candidate's
    resume PDF (Nikhil Mundhra CV.pdf) is automatically submitted.
    """
    curated = curate_profile(profile, job_description=job_description, job_url=job_url)

    try:
        resume_path = str(get_validated_resume_path(profile))
    except Exception:
        fallback = Path(__file__).parent / "Portfolio" / "Nikhil Mundhra CV.pdf"
        resume_path = str(fallback) if fallback.exists() else "<no resume_path set in profile.json>"

    address_info = curated.get("address", {})
    region_label = curated.get("target_region", "uae").upper()
    street = address_info.get("street_address", "")
    line2 = address_info.get("address_line2", "")
    city = address_info.get("city", "")
    state_prov = address_info.get("state_province", "")
    postal = address_info.get("postal_code", "")
    country = address_info.get("country", "")
    formatted_addr = address_info.get("formatted", "")
    phone = curated.get("phone", "")

    address_block = f"""
ADDRESS & CONTACT INFORMATION (APPLICATION TARGET REGION: {region_label}):
- Target Address for this Application:
  * Address / Street / Address Line 1: "{street}"
  * Address Line 2 (if separate field exists): "{line2}"
  * City: "{city}"
  * State / Province / Region: "{state_prov}"
  * Postal / Zip Code: "{postal}"
  * Country: "{country}"
  * Full Formatted Address (if single-line field): "{formatted_addr}"
- Candidate Contact Phone:
  * Phone Number: "{phone}"
  * Note: For country code or dialing prefix dropdowns, select "{country}".
"""

    jd_context_block = ""
    if job_description.strip():
        jd_context_block = f"""
TARGET JOB DESCRIPTION (FOR SCREENING CONTEXT):
{job_description.strip()}
"""

    company_block = ""
    if company_context:
        company_name = company_context.get("company_name", "the company")
        company_summary = company_context.get("company_summary", "")
        why_answer = company_context.get("why_company_answer", "")
        culture_fit = company_context.get("culture_mission_match", "")

        company_block = f"""
COMPANY INTELLIGENCE & SCREENING ALIGNMENT:
- Company Name: {company_name}
- About the Company: {company_summary}
- Mission & Culture Fit: {culture_fit}
- Recommended Answer for 'Why do you want to work at {company_name}?':
  "{why_answer}"
"""

    gender = curated.get("gender", "Male")
    ethnicity = curated.get("ethnicity", "North Indian")
    nationality = curated.get("nationality", "Indian")
    dob = curated.get("date_of_birth", "28/10/2005")
    dob_iso = curated.get("dob_iso", "2005-10-28")
    dob_day = curated.get("dob_day", "28")
    dob_month = curated.get("dob_month", "10")
    dob_year = curated.get("dob_year", "2005")

    personal_block = f"""
PERSONAL, DEMOGRAPHIC & EEO INFORMATION:
- Full Name: Nikhil Mundhra
- Gender: {gender} (for dropdowns: "Male" or "Man")
- Ethnicity / Race: {ethnicity} (for US EEO dropdowns: select "Asian" or "Asian (Not Hispanic or Latino)")
- Nationality / Citizenship: {nationality}
- Date of Birth:
  * Date of Birth (DD/MM/YYYY): "{dob}"
  * Date of Birth (ISO YYYY-MM-DD): "{dob_iso}"
  * Day: "{dob_day}"
  * Month: "{dob_month}" (October)
  * Year: "{dob_year}"
- Veteran Status: Not a veteran ("I am not a protected veteran")
- Disability Status: No disability ("No, I do not have a disability")
"""

    compact_curated = {
        "full_name": curated.get("full_name", ""),
        "gender": gender,
        "ethnicity": ethnicity,
        "nationality": nationality,
        "date_of_birth": dob,
        "dob_iso": dob_iso,
        "dob_day": dob_day,
        "dob_month": dob_month,
        "dob_year": dob_year,
        "email": curated.get("email", ""),
        "phone": curated.get("phone", ""),
        "location": curated.get("location", ""),
        "address": address_info,
        "education": curated.get("education", []),
        "work_history": [
            {k: v for k, v in exp.items() if not k.startswith("_")}
            for exp in curated.get("work_history", [])
        ],
        "projects": [
            {k: v for k, v in p.items() if not k.startswith("_")}
            for p in curated.get("projects", [])
        ],
        "skills": curated.get("skills", {}),
        "screening_preferences": curated.get("screening_preferences", {}),
    }

    return f"""
You are filling out a job application at: {job_url}

Use the CURATED PROFILE JSON, ADDRESS DETAILS, and COMPANY INTELLIGENCE below as your
source of truth for personal details, work history, education, and screening question answers.
Do not invent information that is not present in it. If a required field has no matching data,
leave it blank and list it at the end of your run instead of guessing.
{address_block}
{personal_block}
{jd_context_block}
{company_block}
CURATED PROFILE:
{json.dumps(compact_curated, indent=2)}

How to work:
1. Go through the application step by step. Portals like Workday load
   sections asynchronously and use custom dropdowns and date pickers, so
   wait for a section to finish rendering before you interact with it.
2. Match profile fields to form fields by meaning, not by exact label
   text (for example "Current employer" should map to the most recent
   entry in work_history).
3. ADDRESS & CONTACT DETAILS:
   When filling address blocks (such as 'Address', 'City', 'State/Province', 'Postal', 'Country'):
   - Use the values from ADDRESS & CONTACT INFORMATION above.
   - For 'Address' or 'Street Address' input, fill: "{street}"
   - For 'City' input, fill: "{city}"
   - For 'State/Province' or 'State' or 'Province' input/dropdown, enter/select: "{state_prov}"
   - For 'Postal' or 'Zip' or 'Postal Code' input, fill: "{postal}"
   - For 'Country' dropdown/input, select/enter: "{country}"
   - For 'Phone' or 'Phone Number' input, fill: "{phone}"
4. BATCHING INSTRUCTION:
   Proactively batch all co-located, visible form fields together in a single step rather than pausing between them (e.g., fill First Name, Last Name, Email, Phone, Address, City, State/Province, Postal Code, and Country all in one single multi-action step).
5. Fill work history and project fields using the curated entries in
   CURATED PROFILE above. Do not attempt to add arbitrary or extra
   unlisted roles.
6. For open ended screening questions:
   - For role-specific questions ("Tell us about relevant experience", "Describe
     your experience with X"), ground answers in the matched experiences,
     projects, and duties listed in CURATED PROFILE.
   - For company-specific questions ("Why do you want to work here?", "What
     interests you about our mission?"), use the recommended answers and
     points in COMPANY INTELLIGENCE & SCREENING ALIGNMENT above.
   -  Write short, direct answers grounded only in the profile data above, 
   in a normal human voice, not a marketing voice. 
   Do not use: delve, leverage, robust, seamless, foster, streamline,
   unlock, elevate, moreover, furthermore, "it's important to note," "in
   today's fast paced world," "I'm thrilled to," or "passionate about"
   without a specific fact behind it. Do not restate the question before
   answering it. Do not use em dashes or semicolons to link two clauses,
   just end the sentence. Vary sentence length instead of writing three
   sentences of the same shape in a row. Ground each answer in one concrete
   detail from work_history or education rather than an abstract claim.
7. RESUME / CV AUTO-UPLOAD:
   When a resume or CV upload section, button, or dropzone appears:
   - You can invoke the custom `upload_resume` action directly.
   - Alternatively, clicking 'Upload', 'Browse', or the dropzone will trigger
     the system's filechooser interceptor, which automatically attaches:
     {resume_path}
   - Verify that the file name (e.g. 'Nikhil Mundhra CV.pdf') is displayed
     as attached before navigating to the next page.
8. GPA INSTRUCTION:
   - When GPA is optional (no asterisk *, not required), LEAVE IT BLANK.
   - When GPA is required (has * or required attribute), fill: "3.6".
9. DESIRED SALARY INSTRUCTION:
   - Always request nearer to the upper end of the posted compensation range for the role (e.g. if the posting lists $100,000 - $190,000, specify $180,000; if in India with ₹12L - ₹18L, specify ₹18,00,000).
10. RELOCATION INSTRUCTION:
   - When asked if willing to relocate, ALWAYS answer "Yes".
11. UNLISTED TOOLS & FRAMEWORKS:
   - When asked for experience with a tool or framework not listed in the candidate's profile/resume, write either "1 year" or "6 months" depending on input type (e.g., "1" or "1 year" for years, "6" or "6 months" for months).
12. Stop as soon as you reach the final review or submit page. Do not
   click Submit, Apply, or any equivalent final action under any
   circumstances. Take a screenshot of that page and end the run so a
   person can review it before anything is sent.
"""


async def run(job_url: str, headless: bool, job_description: str = "") -> None:
    if job_url.startswith("http://"):
        job_url = "https://" + job_url[len("http://") :]

    profile = load_profile()

    # Step 1: Automatic Job & Company Context Preparation
    print(f"🔍 Analyzing application target: {job_url}")
    if not job_description.strip():
        print("⚡ Extracting job description & company background automatically from the web...")
        job_ctx = prepare_job_context(job_url, profile)
        job_description = job_ctx.get("job_description", "")
        company_context = job_ctx
    else:
        print("📄 Using supplied job description override, extracting company background...")
        job_ctx = prepare_job_context(
            job_url,
            profile,
            html_content=f"<html><body>{job_description}</body></html>",
        )
        company_context = job_ctx

    task = build_task(
        profile,
        job_url,
        job_description=job_description,
        company_context=company_context,
    )

    # Print summary feedback
    print(f"\n🏢 Company: {company_context.get('company_name', 'Unknown')}")
    print(f"📖 Overview: {company_context.get('company_summary', '')[:120]}...")
    print(f"🤖 LLM calls used for prep: {company_context.get('llm_call_count', 0)} (Budget constraint: 1 <= calls <= 2)")

    curated = curate_profile(profile, job_description=job_description, job_url=job_url)
    target_region = curated.get("target_region", "uae").upper()
    selected_addr = curated.get("address", {})
    print(f"📍 Target Region: {target_region} ({curated.get('location', '')})")
    print(f"🏠 Address: {selected_addr.get('street_address', '')}, {selected_addr.get('city', '')} {selected_addr.get('postal_code', '')}, {selected_addr.get('country', '')}")
    print(f"📞 Phone: {curated.get('phone', '')}")

    summary = curated.get("tailoring_summary", {})
    if summary.get("mode") == "tailored":
        print(f"🎯 Matched {summary.get('matched_keywords_count', 0)} keywords from job description.")
        print(f"💼 Curated experiences: {', '.join(summary.get('selected_roles', []))}")
        print(f"🛠️  Curated projects: {', '.join(summary.get('selected_projects', []))}\n")
    else:
        print("ℹ️  Using default primary experiences.\n")

    try:
        from browser_use import Agent, Browser, ChatAnthropic
    except ImportError as e:
        raise RuntimeError(
            "browser-use is not installed in the active environment. "
            "Install with: pip install browser-use playwright && playwright install"
        ) from e

    # OpenRouter with gpt-4o as primary, Claude (Anthropic) as fallback
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")

    if openrouter_key and anthropic_key:
        # Both set: prefer OpenRouter (gpt-4o), fallback to Claude on error
        try:
            from browser_use import ChatAnthropic as _CA

            llm = _CA(
                model="claude-sonnet-4-6",
                anthropic_api_key=openrouter_key,
                # OpenRouter provides an Anthropic-compatible endpoint;
                # browser-use's ChatAnthropic will route through it when
                # the key is supplied and no ANTHROPIC_API_KEY overrides it.
            )
            print("Using OpenRouter with Claude Sonnet 4 (fallback to direct Anthropic if needed)")
        except Exception:
            # Fallback: use OpenAI model via OpenRouter directly
            try:
                from browser_use import ChatOpenAI as _CO

                llm = _CO(
                    model="openai/gpt-4o",
                    api_key=openrouter_key,
                    base_url="https://openrouter.ai/api/v1",
                    max_completion_tokens=600,
                )
                print("Using OpenRouter with openai/gpt-4o")
            except Exception:
                # Last resort: direct Anthropic
                llm = ChatAnthropic(model="claude-sonnet-4-6", anthropic_api_key=anthropic_key)
                print("Falling back to direct Anthropic Claude Sonnet 4")
    elif openrouter_key:
        try:
            from browser_use import ChatOpenAI as _CO

            model_name = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
            llm = _CO(
                model=model_name,
                api_key=openrouter_key,
                base_url="https://openrouter.ai/api/v1",
                max_completion_tokens=600,
            )
            print(f"Using OpenRouter with {model_name}")
        except Exception:
            raise RuntimeError(
                "OPENROUTER_API_KEY set but browser-use lacks ChatOpenAI support. "
                "Set ANTHROPIC_API_KEY too for Claude fallback."
            )
    elif anthropic_key:
        llm = ChatAnthropic(model="claude-sonnet-4-6")
        print("Using Anthropic Claude Sonnet 4 (direct)")
    else:
        raise RuntimeError(
            "Set OPENROUTER_API_KEY and/or ANTHROPIC_API_KEY in .env"
        )
    resume_path = get_validated_resume_path(profile)
    print(f"📄 Target Resume PDF: {resume_path.name}")
    print(f"   ({resume_path})")

    controller = create_resume_controller(resume_path)

    exe_path = find_chromium_executable()
    if exe_path:
        print(f"Browser binary: {exe_path}")

    browser_args = get_browser_launch_args()

    cdp_url = os.getenv("CDP_URL")
    user_data_dir = os.getenv("BROWSER_USER_DATA_DIR")

    browser = Browser(
        headless=headless,
        executable_path=exe_path if not cdp_url else None,
        cdp_url=cdp_url,
        user_data_dir=user_data_dir,
        args=browser_args,
        ignore_default_args=["--enable-automation"],
    )

    class JobApplierAgent(Agent):
        """
        Enhanced browser-use Agent with deterministic cookie auto-acceptance
        and OpenRouter in-flight rate limit backoff.
        """
        async def step(self, step_info: Any = None) -> None:
            if self.browser_session:
                try:
                    await auto_accept_cookies(self.browser_session)
                except Exception:
                    pass
            return await super().step(step_info)

        async def get_model_output(self, input_messages: list[Any]) -> Any:
            for attempt in range(4):
                try:
                    return await super().get_model_output(input_messages)
                except Exception as e:
                    err = str(e)
                    if ("402" in err or "in_flight_budget" in err or "rate_limit" in err) and attempt < 3:
                        wait_sec = 25 * (attempt + 1)
                        print(f"\n⏳ OpenRouter in-flight limit reached: waiting {wait_sec}s for request settlement (retry {attempt + 1}/3)...")
                        await asyncio.sleep(wait_sec)
                    else:
                        raise e

    agent = JobApplierAgent(
        task=task,
        llm=llm,
        browser=browser,
        controller=controller,
        use_vision=True,
        vision_detail_level="low",
        initial_actions=[{"navigate": {"url": job_url}}],
        max_actions_per_step=10,
        max_history_items=6,
        max_clickable_elements_length=20000,
        llm_timeout=120,
    )

    print("\nStarting agent. Watch the browser window; press Ctrl+C any time to stop.\n")
    history = await agent.run()

    print("\nAgent stopped before submitting. Review the open page yourself.")
    print("Summary of what it did:")
    print(history.final_result())


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fill a job application from a structured profile, then stop for human review."
    )
    parser.add_argument("job_url", help="Direct link to the job application form")
    parser.add_argument(
        "-j",
        "--jd",
        type=str,
        default="",
        help="Job description text for tailoring portfolio experiences and keywords",
    )
    parser.add_argument(
        "-f",
        "--jd-file",
        type=Path,
        default=None,
        help="Path to a text/markdown file containing the job description",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run without a visible browser window (not recommended while testing)",
    )
    args = parser.parse_args()

    job_description = args.jd
    if args.jd_file:
        if not args.jd_file.exists():
            parser.error(f"Job description file not found: {args.jd_file}")
        with open(args.jd_file, "r", encoding="utf-8") as f:
            job_description = f.read()

    asyncio.run(run(args.job_url, headless=args.headless, job_description=job_description))


if __name__ == "__main__":
    main()
