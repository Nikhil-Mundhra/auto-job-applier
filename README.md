# Auto Job Applier

A local-first, privacy-preserving job application automation system designed to run on a single machine. Operates without cloud browser infrastructure, filling job applications accurately and halting strictly before final submission for human review.

For complete architectural details, subsystem specifications, and sequence diagrams, refer to [architecture.md](file:///Users/nikhilmundhra/Documents/Github/auto-job-applier/architecture.md).

---

## Key Features

- **Dual Execution Pathways**:
  - **Direct Deterministic Mode (`direct_fill.py`)**: 0 LLM API calls. High-speed Playwright automation using semantic label heuristics, DOM matching, and automatic resume upload.
  - **AI Agentic Mode (`main.py`)**: Vision-driven autonomous agent using `browser-use` and multi-modal LLMs (OpenRouter GPT-4o / Claude Sonnet) for dynamic multi-step portals.
- **Strictly Bounded LLM Overhead**: When running AI preparation, `jd_extractor.py` guarantees at most 2 LLM calls (1 on standard path, 2 if fallback extraction is needed). Direct mode uses 0 LLM calls.
- **Automatic Multi-Region Routing**: `matcher.py` detects application region from URL and job content, automatically routing between domestic Indian address/phone and international UAE / NYU Abu Dhabi contact details.
- **Deterministic Cookie Dismissal**: Zero-token auto-acceptance across major CMPs (OneTrust, Cookiebot, Osano, Didomi, TrustArc, Workday) traversing shadow DOM trees.
- **Multi-Modal Resume Attachment**: Resolves target PDF resume (`Portfolio/Nikhil Mundhra CV.pdf`) and attaches it via DOM inputs, file chooser event interception, and controller actions.
- **Stealth & Retail Browser Integration**: Auto-detects installed retail browsers (Opera GX, Google Chrome, Brave), injects anti-detection arguments, masks `navigator.webdriver`, and supports persistent sessions and CDP attachment.
- **Human-in-the-Loop Safety Gate**: The system strictly halts on the review stage and never clicks final Submit, keeping the browser open for candidate verification.

---

## Setup

```bash
cd auto-job-applier
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
```

### Environment Configuration

Open `.env` and configure your API credentials and optional browser settings:

```env
# LLM Providers (Required only for AI Agentic Mode)
ANTHROPIC_API_KEY=sk-ant-...
# OR OpenRouter:
OPENROUTER_API_KEY=sk-or-v1-...

# Browser Settings (Optional)
# Explicit path to browser executable (default auto-detects Opera GX, Chrome, Brave)
# BROWSER_EXECUTABLE_PATH=/Applications/Opera GX.app/Contents/MacOS/Opera

# Persistent browser profile path to maintain cookies and sessions across runs
# BROWSER_USER_DATA_DIR=~/.auto-job-applier/browser_profile

# Connect to an already-running browser instance via Chrome DevTools Protocol
# CDP_URL=http://localhost:9222
```

- If both `OPENROUTER_API_KEY` and `ANTHROPIC_API_KEY` are configured, the agent uses OpenRouter with `openai/gpt-4o` as primary and falls back to Anthropic Claude Sonnet 4 if needed.
- If only `ANTHROPIC_API_KEY` is configured, Claude is used directly.
- Direct mode (`direct_fill.py`) requires no API keys and incurs zero LLM cost.

### Profile Configuration

Open `profile.json` and configure your personal details:
- **Contact & Demographics**: Name, email, phone numbers, and addresses for both UAE/International and India regions.
- **Resume Location**: Path to your PDF resume (defaults to `Portfolio/Nikhil Mundhra CV.pdf`).
- **Work History & Projects**: Roles, organizations, dates, technology stacks, and duty bullet points.
- **Skills Taxonomy**: Categorized technical and domain proficiencies.
- **Screening Preferences**: Sponsorship requirements, work authorization, relocation preferences, start dates, and salary expectations.

---

## Usage

### Option 1: Direct Deterministic Mode (0 API Calls, Recommended for Standard ATS)

Fills standard ATS application forms (Workday, Greenhouse, Lever, Ashby, JazzHR) without incurring LLM token costs.

```bash
# Visible browser window (recommended):
python direct_fill.py "https://jobs.lever.co/company/job-id"

# Custom screenshot path:
python direct_fill.py "https://boards.greenhouse.io/company/jobs/12345" --screenshot review.png

# Headless mode:
python direct_fill.py "https://jobs.lever.co/company/job-id" --headless
```

The script will:
1. Detect application region and select corresponding address and phone.
2. Launch browser with stealth settings (Opera GX / Chrome / Brave).
3. Auto-accept cookie banners via shadow DOM evaluation.
4. Locate resume input and attach `Nikhil Mundhra CV.pdf`.
5. Populate personal, contact, education, work experience, and screening fields.
6. Capture a full-page review screenshot (`application_review.png`).
7. Halt and keep the browser window open for your manual review and final submission.

---

### Option 2: AI Agentic Mode (browser-use + LLM)

Uses vision-assisted agent loop for complex, multi-page, or non-standard application portals.

```bash
# Automated run with online job description extraction:
python main.py "https://company.wd1.myworkdayjobs.com/en-US/careers/job/12345"

# Inline job description text:
python main.py "https://company.wd1.myworkdayjobs.com/en-US/careers/job/12345" \
  --jd "Seeking an AI Engineer with PyTorch, computer vision, and LLM experience..."

# Job description from file:
python main.py "https://company.wd1.myworkdayjobs.com/en-US/careers/job/12345" \
  --jd-file job_description.txt
```

The agent will:
1. Extract the job description deterministically (JSON-LD schema & ATS selectors) with LLM fallback only if needed.
2. Fetch company intelligence via the Wikipedia REST API.
3. Enforce strict LLM call budgeting (1 call standard, at most 2 calls).
4. Curate the top 2-3 most relevant experiences, projects, and matching skills.
5. Launch the vision agent, navigate the form, upload resume, and fill screening fields.
6. Stop strictly on the final review stage for manual human review and submission.

---

## Running Tests

Run the comprehensive unit and integration test suite:

```bash
.venv/bin/pytest
```

The test suite validates:
- Browser configuration, executable detection, and stealth scripts (`test_browser_config.py`).
- Deterministic cookie detection across CMP frameworks (`test_cookie_handler.py`).
- Job description extraction, Wikipedia enrichment, and LLM budget bounds (`test_extractor_and_budget.py`).
- Regional address detection, salary targeting, keyword matching, and portfolio curation (`test_matcher.py`).
- Resume resolution, ATS selector mapping, filechooser interception, and controller actions (`test_resume_uploader.py`).

---

## Security & Operational Notes

- **Never Auto-Submits**: Neither engine will ever click final Submit. You always inspect the form and complete submission manually.
- **Local Data Only**: Keep `profile.json` and `.env` on your local machine. Do not commit sensitive personal credentials to public repositories.
- **Anti-Bot Considerations**: The browser launcher includes stealth flags and masks automation attributes. The scripts are intended for public application forms accessible in standard consumer browsers.
