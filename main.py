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
from pathlib import Path

from dotenv import load_dotenv
from browser_use import Agent, Browser, ChatAnthropic

load_dotenv()

PROFILE_PATH = Path(__file__).parent / "profile.json"


def load_profile() -> dict:
    with open(PROFILE_PATH, "r") as f:
        return json.load(f)


def build_task(profile: dict, job_url: str) -> str:
    """
    The profile is passed as structured JSON rather than a raw resume dump.
    That is what lets the agent answer a specific field like start_year or
    a screening question grounded in real data instead of guessing.
    """
    resume_path = profile.get("resume_path", "<no resume_path set in profile.json>")

    return f"""
You are filling out a job application at: {job_url}

Use the PROFILE JSON below as your only source of truth for personal
details, work history, education, and screening question answers. Do not
invent information that is not present in it. If a required field has no
matching data, leave it blank and list it at the end of your run instead
of guessing.

PROFILE:
{json.dumps(profile, indent=2)}

How to work:
1. Go through the application step by step. Portals like Workday load
   sections asynchronously and use custom dropdowns and date pickers, so
   wait for a section to finish rendering before you interact with it.
2. Match profile fields to form fields by meaning, not by exact label
   text (for example "Current employer" should map to the most recent
   entry in work_history).
3. For open ended screening questions, write short, professional answers
   grounded only in the profile data above.
4. When a resume or CV upload field appears, upload the file at:
   {resume_path}
5. Stop as soon as you reach the final review or submit page. Do not
   click Submit, Apply, or any equivalent final action under any
   circumstances. Take a screenshot of that page and end the run so a
   person can review it before anything is sent.
"""


async def run(job_url: str, headless: bool) -> None:
    profile = load_profile()
    task = build_task(profile, job_url)

    llm = ChatAnthropic(model="claude-sonnet-4-6")
    browser = Browser(headless=headless)

    agent = Agent(
        task=task,
        llm=llm,
        browser=browser,
        use_vision=True,
    )

    print("Starting agent. Watch the browser window; press Ctrl+C any time to stop.\n")
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
        "--headless",
        action="store_true",
        help="Run without a visible browser window (not recommended while testing)",
    )
    args = parser.parse_args()

    asyncio.run(run(args.job_url, headless=args.headless))


if __name__ == "__main__":
    main()
