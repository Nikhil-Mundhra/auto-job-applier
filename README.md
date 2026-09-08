# Local job application agent

Runs on a single MacBook. No cloud browser infra, no scaling, just Playwright
plus browser-use plus Claude, filling one application at a time while you
watch.

## Setup

```bash
cd job_app_agent
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
```

Open `.env` and add your real Anthropic API key (or OpenRouter API key).

```env
ANTHROPIC_API_KEY=sk-ant-...
# OR OpenRouter:
OPENROUTER_API_KEY=sk-or-v1-...
```

If both are set, the agent uses OpenRouter with `openai/gpt-4o` as the primary
model, and falls back to Anthropic Claude Sonnet 4 if OpenRouter fails.

If only `ANTHROPIC_API_KEY` is set, the agent uses Claude directly.

Then open `profile.json` and replace the example data with your own: name,
contact info, `resume_path` pointing at your actual resume file, work
history, education, and how you want screening questions like sponsorship
or relocation answered.

## Run it

### 1. Automated Run (Recommended)
You only need to supply the direct link to the job application:

```bash
python main.py "https://company.wd1.myworkdayjobs.com/en-US/careers/job/12345"
```

The system automatically:
1. **Extracts the Job Description**: Fast deterministic script parsing (JSON-LD schema & portal selectors) with an LLM fallback.
2. **Extracts Company Intelligence**: Pulls company background from the posting and the web (Wikipedia REST API).
3. **Enforces Strict LLM Budget**: Runs minimum 1 and at most 2 LLM calls for preparation (1 call on happy path, 2 calls if JD fallback extraction is required).
4. **Curates Your Portfolio**: Selects the top 2–3 most relevant experiences, projects, and skills from `profile.json` matched to the role.
5. **Pre-populates Company Fit**: Generates grounded answers for screening questions like *"Why do you want to work at [Company]?"*.

### 2. Manual Override (Optional)
If you wish to test with custom notes or an offline job description:

```bash
# Inline text:
python main.py "https://company.wd1.myworkdayjobs.com/en-US/careers/job/12345" \
  --jd "Seeking an AI Engineer with PyTorch, computer vision, and LLM experience..."

# Or from a file:
python main.py "https://company.wd1.myworkdayjobs.com/en-US/careers/job/12345" \
  --jd-file job_description.txt
```

A visible Chrome window will open. The agent narrates what it is doing in
the terminal. It is instructed to stop on the final review or submit page
and never click Submit itself, so you always do that step by hand. You can
also stop it at any point with Ctrl+C if it goes somewhere you did not
expect.

Use `--headless` only once you trust the flow for a given site, since you
lose the ability to watch it live.

## Notes

- `browser-use` moves fast (new releases every few weeks), so if `main.py`
  throws an import error, check the current API at
  https://docs.browser-use.com before assuming the script is wrong.
- Some portals put real anti bot protection in front of the form. This
  script does not try to defeat that; it is meant for applications you can
  already reach in an ordinary browser.
- Keep `profile.json` on your machine only. It is your personal data, not
  something to commit to a public repo.
