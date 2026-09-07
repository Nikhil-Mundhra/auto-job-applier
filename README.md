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

Open `.env` and add your real Anthropic API key.

Then open `profile.json` and replace the example data with your own: name,
contact info, `resume_path` pointing at your actual resume file, work
history, education, and how you want screening questions like sponsorship
or relocation answered.

## Run it

```bash
python main.py "https://company.wd1.myworkdayjobs.com/en-US/careers/job/12345"
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
