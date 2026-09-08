"""
Direct Application Auto-Filler (Deterministic, 0 API Calls).
Uses Playwright, profile.json, matcher.py, cookie_handler.py, and resume_uploader.py
to fill the application form accurately, attach Nikhil Mundhra CV.pdf, and stop for human review.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
import json
import os
from pathlib import Path
import re
from typing import Any, Optional

from playwright.async_api import async_playwright

from main import load_profile
from matcher import (
    curate_profile,
    detect_application_region,
    calculate_desired_salary,
    get_tool_experience,
    get_resume_skills_set,
)
from cookie_handler import COOKIE_AUTO_ACCEPT_JS
from resume_uploader import get_validated_resume_path, RESUME_INPUT_SELECTORS


def find_chromium_executable() -> Optional[str]:
    """Auto-detect Chromium / Google Chrome binary on macOS."""
    playwright_cache = Path.home() / "Library/Caches/ms-playwright"
    if playwright_cache.exists():
        for chrome_bin in playwright_cache.glob("**/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"):
            if chrome_bin.exists() and os.access(chrome_bin, os.X_OK):
                return str(chrome_bin)
        for chrome_bin in playwright_cache.glob("**/chrome-headless-shell"):
            if chrome_bin.exists() and os.access(chrome_bin, os.X_OK):
                return str(chrome_bin)
    for p in [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    ]:
        if os.path.exists(p) and os.access(p, os.X_OK):
            return p
    return None


async def fill_application(
    job_url: str,
    headless: bool = False,
    pause_for_review: bool = True,
    screenshot_path: Optional[str] = None,
) -> dict[str, Any]:
    """
    Directly navigates to the job form, auto-accepts cookies, fills personal and address fields,
    attaches the PDF resume, and pauses for human review before any submission.
    """
    profile = load_profile()
    curated = curate_profile(profile, job_url=job_url)
    resume_path = get_validated_resume_path(profile)

    address_info = curated.get("address", {})
    region = curated.get("target_region", "uae").upper()

    print(f"🚀 Direct Auto-Applier (0 API Calls)")
    print(f"🔗 Target: {job_url}")
    print(f"📍 Region: {region} ({curated.get('location')})")
    print(f"🏠 Address: {address_info.get('street_address')}, {address_info.get('city')}, {address_info.get('state_province')} {address_info.get('postal_code')}")
    print(f"📞 Phone: {curated.get('phone')}")
    print(f"📄 Resume: {resume_path.name}")

    exe_path = find_chromium_executable()
    chrome_args = [
        "--use-mock-keychain",
        "--password-store=basic",
        "--disable-features=Translate",
    ]

    results = {
        "fields_filled": [],
        "resume_uploaded": False,
        "cookies_accepted": False,
        "screenshot": None,
    }

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            executable_path=exe_path,
            args=chrome_args,
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        print(f"🌐 Navigating to {job_url}...")
        await page.goto(job_url, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(2000)

        # 1. Deterministic Cookie Auto-Acceptance
        try:
            cookie_res = await page.evaluate(COOKIE_AUTO_ACCEPT_JS)
            if isinstance(cookie_res, dict) and cookie_res.get("accepted"):
                print(f"🍪 Auto-accepted cookies prompt ({cookie_res.get('method')}: {cookie_res.get('text', '')})")
                results["cookies_accepted"] = True
            # Also check for explicit JazzHR / Job Board ALLOW buttons
            allow_btn = page.locator("button:has-text('ALLOW'), button:has-text('Allow'), a:has-text('ALLOW')").first
            if await allow_btn.count() > 0 and await allow_btn.is_visible():
                await allow_btn.click()
                print("🍪 Clicked cookie ALLOW button")
                results["cookies_accepted"] = True
        except Exception as e:
            print(f"⚠️ Cookie handler notice: {e}")

        # 2. Dynamic Region Detection from Live Page Content
        body_text = ""
        try:
            body_text = await page.inner_text("body")
            page_region = detect_application_region(job_description=body_text, job_url=job_url)
            if page_region != curated.get("target_region"):
                curated = curate_profile(profile, job_description=body_text, job_url=job_url)
                address_info = curated.get("address", {})
                region = page_region.upper()
                print(f"📍 Detected target region from job page content: {region} ({curated.get('location')})")
                print(f"🏠 Address updated to: {address_info.get('street_address')}, {address_info.get('city')}, {address_info.get('state_province')} {address_info.get('postal_code')}")
                print(f"📞 Phone updated to: {curated.get('phone')}")
        except Exception as e:
            print(f"⚠️ Page content region analysis notice: {e}")

        # Helper to check if a form field is required (via asterisk, required attr, aria-required, etc.)
        async def is_field_required(locator) -> bool:
            try:
                req = await locator.get_attribute("required")
                if req is not None and req.lower() != "false":
                    return True
                aria_req = await locator.get_attribute("aria-required")
                if aria_req == "true":
                    return True
                info = await locator.evaluate("""e => {
                    let p = e.parentElement;
                    while (p && p.tagName.toLowerCase() !== "form") {
                        let l = p.querySelector("label");
                        if (l) return { text: l.innerText, className: l.className + " " + (p.className || "") };
                        p = p.parentElement;
                    }
                    return { text: "", className: "" };
                }""")
                text = info.get("text", "")
                cls = info.get("className", "")
                if "*" in text or "required" in text.lower() or "required" in cls.lower():
                    return True
            except Exception:
                pass
            return False

        # Helper to safely fill an input if it exists
        async def try_fill(selectors: list[str], value: str, label_name: str) -> bool:
            if not value:
                return False
            for sel in selectors:
                try:
                    locator = page.locator(sel).first
                    if await locator.count() > 0 and await locator.is_visible():
                        await locator.fill(value)
                        print(f"  ✍️  {label_name}: {value} (via {sel})")
                        results["fields_filled"].append(label_name)
                        return True
                except Exception:
                    continue
            return False

        # Helper to safely select dropdown
        async def try_select(
            selectors: list[str],
            value_pattern: str,
            label_name: str,
            alternative_patterns: Optional[list[str]] = None,
        ) -> bool:
            patterns = [value_pattern] + (alternative_patterns or [])
            for sel in selectors:
                try:
                    locator = page.locator(sel).first
                    if await locator.count() > 0 and await locator.is_visible():
                        options = await locator.locator("option").all_inner_texts()
                        target_opt = None
                        # 1. Exact match
                        for pat in patterns:
                            for opt in options:
                                if opt.strip().lower() == pat.lower():
                                    target_opt = opt.strip()
                                    break
                            if target_opt:
                                break
                        # 2. Substring match (avoiding false matches like female for male)
                        if not target_opt:
                            for pat in patterns:
                                for opt in options:
                                    opt_clean = opt.strip().lower()
                                    if pat.lower() in opt_clean:
                                        if pat.lower() == "male" and "female" in opt_clean:
                                            continue
                                        target_opt = opt.strip()
                                        break
                                if target_opt:
                                    break
                        if target_opt:
                            await locator.select_option(label=target_opt)
                            print(f"  ☑️  {label_name}: {target_opt}")
                            results["fields_filled"].append(label_name)
                            return True
                except Exception:
                    continue
            return False

        # Helper to safely check radio/checkbox
        async def try_check(selectors: list[str], label_name: str) -> bool:
            for sel in selectors:
                try:
                    locator = page.locator(sel).first
                    if await locator.count() > 0:
                        await locator.check(force=True)
                        print(f"  🔘 {label_name} checked")
                        results["fields_filled"].append(label_name)
                        return True
                except Exception:
                    continue
            return False

        print("\n📝 Filling application fields...")

        # Contact Details
        full_name = curated.get("full_name", "Nikhil Mundhra")
        parts = full_name.split(" ", 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else ""

        await try_fill(["#resumator-firstname-value", "input[name='first_name']", "#first_name", "input[name*='firstname' i]"], first_name, "First Name")
        await try_fill(["#resumator-lastname-value", "input[name='last_name']", "#last_name", "input[name*='lastname' i]"], last_name, "Last Name")
        await try_fill(["#resumator-email-value", "input[name='email']", "#email", "input[type='email']"], curated.get("email", ""), "Email Address")
        await try_fill(["#resumator-phone-value", "input[name='phone']", "#phone", "input[type='tel']"], curated.get("phone", ""), "Phone Number")

        # Address Details
        await try_fill(["#resumator-address-value", "input[name='address']", "#address", "input[placeholder*='Address' i]"], address_info.get("street_address", ""), "Address Line 1")
        await try_fill(["#resumator-city-value", "input[name='city']", "#city", "input[placeholder*='City' i]"], address_info.get("city", ""), "City")
        await try_fill(["#resumator-state-value", "input[name='state']", "#state", "input[placeholder*='State' i]"], address_info.get("state_province", ""), "State/Province")
        await try_fill(["#resumator-postal-value", "input[name='postal']", "#postal_code", "#zip", "input[placeholder*='Postal' i]"], address_info.get("postal_code", ""), "Postal Code")

        # Links
        await try_fill(["input[name*='linkedin' i]", "#linkedin", "input[placeholder*='LinkedIn' i]"], curated.get("linkedin", ""), "LinkedIn")
        await try_fill(["input[name*='github' i]", "#github", "input[placeholder*='GitHub' i]"], curated.get("github", ""), "GitHub")
        await try_fill(["input[name*='website' i]", "input[name*='portfolio' i]"], curated.get("portfolio_website", ""), "Portfolio")

        # Resume Upload
        print("\n📎 Uploading Resume PDF...")
        resume_uploaded = False
        for sel in ["#resumator-resume-value"] + RESUME_INPUT_SELECTORS:
            try:
                locator = page.locator(sel).first
                if await locator.count() > 0:
                    await locator.set_input_files(str(resume_path))
                    print(f"  ✅ Resume attached: {resume_path.name} (via {sel})")
                    results["resume_uploaded"] = True
                    resume_uploaded = True
                    break
            except Exception:
                continue

        if not resume_uploaded:
            # Try clicking upload dropzone if input wasn't directly settable
            try:
                dropzone = page.locator("#resumator-choose-upload, .resumator-file-upload-drop-zone, button:has-text('Upload Resume')").first
                if await dropzone.count() > 0:
                    async with page.expect_file_chooser() as fc_info:
                        await dropzone.click()
                    fc = await fc_info.value
                    await fc.set_files(str(resume_path))
                    print(f"  ✅ Resume attached via dropzone file chooser: {resume_path.name}")
                    results["resume_uploaded"] = True
            except Exception as e:
                print(f"  ⚠️ Resume dropzone click error: {e}")

        # Date of Birth (DOB) Fields
        dob = curated.get("date_of_birth", "28/10/2005")
        dob_iso = curated.get("dob_iso", "2005-10-28")
        dob_day = str(curated.get("dob_day", "28"))
        dob_month = str(curated.get("dob_month", "10"))
        dob_year = str(curated.get("dob_year", "2005"))
        month_names = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
        month_idx = int(dob_month) - 1 if dob_month.isdigit() and 1 <= int(dob_month) <= 12 else 9
        month_name = month_names[month_idx]

        # 1. Full Date of Birth inputs
        dob_filled = False
        for sel in [
            "input[name*='dob' i]",
            "input[name*='birth_date' i]",
            "input[name*='birthdate' i]",
            "input[id*='dob' i]",
            "input[id*='birth_date' i]",
            "input[placeholder*='dob' i]",
            "input[placeholder*='birth date' i]",
            "input[placeholder*='date of birth' i]",
        ]:
            try:
                locator = page.locator(sel).first
                if await locator.count() > 0 and await locator.is_visible():
                    inp_type = (await locator.get_attribute("type") or "").lower()
                    placeholder = (await locator.get_attribute("placeholder") or "").lower()
                    if inp_type == "date":
                        val_used = dob_iso
                    elif "mm/dd" in placeholder or "mm-dd" in placeholder:
                        val_used = f"{dob_month.zfill(2)}/{dob_day.zfill(2)}/{dob_year}"
                    else:
                        val_used = dob
                    await locator.fill(val_used)
                    print(f"  ✍️  Date of Birth: {val_used} (via {sel})")
                    results["fields_filled"].append("Date of Birth")
                    dob_filled = True
                    break
            except Exception:
                continue

        # 2. Split Date of Birth inputs / dropdowns (Day, Month, Year)
        if not dob_filled:
            day_filled = await try_fill(["input[name*='birth_day' i]", "input[name*='dob_day' i]", "#birth_day", "#dob_day"], dob_day, "DOB Day")
            if not day_filled:
                await try_select(["select[name*='birth_day' i]", "select[name*='dob_day' i]", "#birth_day", "#dob_day"], dob_day, "DOB Day", alternative_patterns=[str(int(dob_day)) if dob_day.isdigit() else dob_day])

            month_filled = await try_fill(["input[name*='birth_month' i]", "input[name*='dob_month' i]", "#birth_month", "#dob_month"], dob_month, "DOB Month")
            if not month_filled:
                await try_select(["select[name*='birth_month' i]", "select[name*='dob_month' i]", "#birth_month", "#dob_month"], dob_month, "DOB Month", alternative_patterns=[str(int(dob_month)) if dob_month.isdigit() else dob_month, month_name, month_name[:3]])

            year_filled = await try_fill(["input[name*='birth_year' i]", "input[name*='dob_year' i]", "#birth_year", "#dob_year"], dob_year, "DOB Year")
            if not year_filled:
                await try_select(["select[name*='birth_year' i]", "select[name*='dob_year' i]", "#birth_year", "#dob_year"], dob_year, "DOB Year")

        # EEO / Demographic Self-Identification (Optional fields)
        print("\n📋 Filling Voluntary Demographic / Self-Identification Fields...")
        gender_val = curated.get("gender", "Male")
        ethnicity_val = curated.get("ethnicity", "North Indian")

        # Gender
        await try_select(
            ["#resumator-eeo_gender-value", "select[name*='gender' i]", "select[name*='eeo_gender' i]"],
            gender_val,
            "Gender",
            alternative_patterns=["Male", "Man"],
        )

        # Race / Ethnicity (Asian / South Asian is standard EEOC category for North Indian)
        await try_select(
            ["#resumator-eeo_race-value", "select[name*='race' i]", "select[name*='ethnicity' i]"],
            "Asian",
            "Race/Ethnicity",
            alternative_patterns=[
                "Asian (Not Hispanic or Latino)",
                "Asian",
                "South Asian",
                "Asian Indian",
                ethnicity_val,
                "Indian",
            ],
        )
        await try_check(["#resumator-eeoc_veteran-value_2", "#resumator-eeoc_veteran-value_0", "input[name*='veteran' i][value='2']"], "Veteran Status (Not a Veteran)")
        await try_check(["#resumator-eeoc_disability-value-2", "#resumator-eeoc_disability-value-0", "input[name*='disability' i][value='2']"], "Disability Status (No Disability)")
        await try_fill(["#resumator-eeoc_disability_signature-value", "input[name*='signature' i]"], full_name, "Disability Electronic Signature")
        await try_fill(["#resumator-eeoc_disability_date-value", "input[name*='date' i]"], datetime.now().strftime("%m/%d/%Y"), "Disability Form Date")

        # Questionnaire & Custom Screening Questions
        print("\n📝 Filling Questionnaire & Screening Questions...")

        # 1. Standard Education & Academics
        await try_select(
            ["#resumator-education-value", "select[name*='education' i]"],
            "College - Bachelor of Science",
            "Highest Education Completed",
            alternative_patterns=["Bachelor of Science", "Bachelor", "BSc", "College - Bachelor", "Some College"],
        )
        await try_fill(
            ["#resumator-college-value", "input[name*='college' i]", "input[name*='university' i]"],
            "New York University Abu Dhabi",
            "College or University",
        )
        # GPA: optional -> leave blank, required -> 3.6
        gpa_loc = page.locator("#resumator-gpa-value, input[name*='gpa' i]").first
        if await gpa_loc.count() > 0 and await gpa_loc.is_visible():
            if await is_field_required(gpa_loc):
                await gpa_loc.fill("3.6")
                print("  ✍️  GPA (Required): 3.6")
                results["fields_filled"].append("GPA")
            else:
                await gpa_loc.fill("")
                print("  ℹ️  GPA: Optional -> Left blank")

        # 2. Work Availability & Preferences
        await try_select(["#resumator-relocate-value", "select[name*='relocate' i]"], "Yes", "Willing to Relocate")
        await try_select(["#resumator-over18-value", "select[name*='over18' i]", "select[name*='18' i]"], "Yes", "18 Years or Older")
        await try_select(["#resumator-evenings-value", "select[name*='evenings' i]"], "Yes", "Can Work Evenings")

        # Desired salary (nearer to upper end)
        salary_loc = page.locator("#resumator-salary-value, input[name*='salary' i]").first
        if await salary_loc.count() > 0 and await salary_loc.is_visible():
            inp_type = (await salary_loc.get_attribute("type") or "").lower()
            placeholder = (await salary_loc.get_attribute("placeholder") or "").lower()
            numeric_only = inp_type == "number" or "number" in placeholder or "digit" in placeholder
            desired_sal = calculate_desired_salary(body_text, region=curated.get("target_region", "uae"), numeric_only=numeric_only)
            await salary_loc.fill(desired_sal)
            print(f"  ✍️  Desired Salary (Upper End): {desired_sal}")
            results["fields_filled"].append("Desired Salary")

        # Earliest start date (handle datepicker inputs)
        start_input = page.locator("#resumator-start-value, input[name*='start' i]").first
        if await start_input.count() > 0 and await start_input.is_visible():
            classes = await start_input.get_attribute("class") or ""
            is_summer_2027 = "2027" in job_url or "2027" in body_text[:600] or "summer" in body_text[:600].lower()
            if "datepicker" in classes.lower():
                from datetime import timedelta
                start_val = "05/17/2027" if is_summer_2027 else (datetime.now() + timedelta(days=7)).strftime("%m/%d/%Y")
            else:
                start_val = "May 2027" if is_summer_2027 else "Immediate / flexible"
            await start_input.fill(start_val)
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(300)
            print(f"  ✍️  Earliest Start Date: {start_val}")
            results["fields_filled"].append("Earliest Start Date")

        await try_fill(
            ["#resumator-wmyu-value", "textarea[name*='wmyu' i]", "textarea[name*='unique' i]"],
            "CS @ NYU (3.9 GPA), founder of VivahGo AI platform & built production GNNs. I combine research rigor with full-stack execution.",
            "What Makes You Unique",
        )

        # 3. Direct All-Select Processor (ensures no unselected dropdown is missed)
        try:
            selects = await page.locator("select").all()
            for s in selects:
                try:
                    if not await s.is_visible():
                        continue
                    val = (await s.input_value() or "").strip()
                    is_unselected = (
                        not val
                        or val in ["0", "-1", "resumator_no_selection", "No answer", "-- No answer --"]
                        or "no_selection" in val.lower()
                    )
                    if not is_unselected:
                        continue

                    label_text = await s.evaluate("""e => {
                        let p = e.parentElement;
                        while (p && p.tagName.toLowerCase() !== "form") {
                            let l = p.querySelector("label");
                            if (l) return l.innerText;
                            p = p.parentElement;
                        }
                        return "";
                    }""")
                    label_clean = re.sub(r"[\*\:\?]+$", "", label_text).strip().lower()
                    opts = [o.strip() for o in await s.locator("option").all_inner_texts()]

                    # GPA Dropdown handling (Required -> 3.6 bracket; Optional -> leave blank)
                    if "gpa" in label_clean:
                        is_req = "*" in label_text or "required" in label_text.lower() or await is_field_required(s)
                        if is_req:
                            for opt in opts:
                                if any(x in opt.lower() for x in ["3.5 and above", "3.5 - 4.0", "3.5+", "3.6", "3.5 to"]):
                                    await s.select_option(label=opt)
                                    print(f"  ☑️  {label_text.strip()} (Required): {opt}")
                                    results["fields_filled"].append(label_text.strip())
                                    break
                        else:
                            print(f"  ℹ️  {label_text.strip()}: Optional -> Left unselected")

                    # Relocation & Housing (Always Yes)
                    elif any(k in label_clean for k in ["relocate", "relocation", "housing", "bengaluru", "bangalore", "area", "pittsburgh"]):
                        if "Yes" in opts:
                            await s.select_option(label="Yes")
                            print(f"  ☑️  {label_text.strip()}: Yes")
                            results["fields_filled"].append(label_text.strip())

                    # State or School location (e.g. PA, NY, etc. -> NYU is in NY)
                    elif any(k in label_clean for k in ["states", "live or go to school"]):
                        if "Yes" in opts:
                            await s.select_option(label="Yes")
                            print(f"  ☑️  {label_text.strip()}: Yes")
                            results["fields_filled"].append(label_text.strip())

                    # School Year / Class Standing
                    elif any(k in label_clean for k in ["school year", "current year", "academic year", "class standing"]):
                        for opt in ["Junior", "Senior planning to attend graduate school", "Sophomore"]:
                            if opt in opts:
                                await s.select_option(label=opt)
                                print(f"  ☑️  {label_text.strip()}: {opt}")
                                results["fields_filled"].append(label_text.strip())
                                break

                    # Preferred Engineering Team
                    elif any(k in label_clean for k in ["preferred team", "which team"]):
                        for opt in opts:
                            if any(k in opt.lower() for k in ["application", "enterprise", "software", "development"]):
                                await s.select_option(label=opt)
                                print(f"  ☑️  {label_text.strip()}: {opt}")
                                results["fields_filled"].append(label_text.strip())
                                break

                    # Programming Language Comfort
                    elif any(k in label_clean for k in ["programming language", "most experienced", "comfortable in"]):
                        for lang in ["Python", "JavaScript", "TypeScript", "C++", "Java", "C#"]:
                            if lang in opts:
                                await s.select_option(label=lang)
                                print(f"  ☑️  {label_text.strip()}: {lang}")
                                results["fields_filled"].append(label_text.strip())
                                break

                    elif any(k in label_clean for k in ["internet", "connection"]):
                        if "Yes" in opts:
                            await s.select_option(label="Yes")
                            print(f"  ☑️  {label_text.strip()}: Yes")
                            results["fields_filled"].append(label_text.strip())
                    elif any(k in label_clean for k in ["18", "age", "older"]):
                        if "Yes" in opts:
                            await s.select_option(label="Yes")
                            print(f"  ☑️  {label_text.strip()}: Yes")
                            results["fields_filled"].append(label_text.strip())
                    elif any(k in label_clean for k in ["evening", "shift", "weekend"]):
                        if "Yes" in opts:
                            await s.select_option(label="Yes")
                            print(f"  ☑️  {label_text.strip()}: Yes")
                            results["fields_filled"].append(label_text.strip())

                    # Visa Sponsorship / Work Authorization
                    elif any(k in label_clean for k in ["sponsorship", "visa", "authorized to work", "work authorization"]):
                        asks_without = any(w in label_clean for w in ["without", "do not require", "don't require", "without company"])
                        if asks_without:
                            target = "No" if curated.get("target_region") not in ["india", "uae"] else "Yes"
                        else:
                            target = "Yes" if curated.get("target_region") not in ["india", "uae"] else "No"
                        for opt in opts:
                            if opt.lower().startswith(target.lower()) or target.lower() in opt.lower():
                                await s.select_option(label=opt)
                                print(f"  ☑️  {label_text.strip()}: {opt}")
                                results["fields_filled"].append(label_text.strip())
                                break

                    elif any(k in label_clean for k in ["experience", "years", "how long", "worked with"]):
                        for opt_cand in ["1 year", "1", "6 months", "< 1 year", "0-1 years", "1-2 years", "1 - 2 years"]:
                            if opt_cand in opts:
                                await s.select_option(label=opt_cand)
                                print(f"  ☑️  {label_text.strip()}: {opt_cand}")
                                results["fields_filled"].append(label_text.strip())
                                break
                except Exception:
                    continue
        except Exception as e:
            print(f"⚠️ Selects processor notice: {e}")

        # 4. Checkbox Questionnaires Processor
        try:
            form_groups = await page.locator(".form-group, .resumator-row, fieldset").all()
            for fg in form_groups:
                try:
                    cbs = await fg.locator("input[type='checkbox']").all()
                    if not cbs:
                        continue
                    lbl_el = fg.locator("label").first
                    lbl_text = (await lbl_el.inner_text()).strip() if await lbl_el.count() > 0 else ""
                    lbl_clean = re.sub(r"[\*\:\?]+$", "", lbl_text).strip().lower()

                    if any(k in lbl_clean for k in ["sms", "terms", "policy", "privacy"]):
                        continue

                    # Internship vs Co-op
                    if any(k in lbl_clean for k in ["internship", "co-op"]):
                        for cb in cbs:
                            val = (await cb.get_attribute("value") or "").strip()
                            cb_lbl = await cb.evaluate("e => e.parentElement ? e.parentElement.innerText : ''")
                            if "internship" in val.lower() or "internship" in cb_lbl.lower():
                                if not await cb.is_checked():
                                    await cb.check(force=True)
                                    print(f"  ☑️  {lbl_text}: Checked Internship")
                                    results["fields_filled"].append("Internship choice")

                    # Level of work experience
                    elif any(k in lbl_clean for k in ["work experience", "previous work"]):
                        for cb in cbs:
                            val = (await cb.get_attribute("value") or "").strip()
                            cb_lbl = await cb.evaluate("e => e.parentElement ? e.parentElement.innerText : ''")
                            target_checks = ["internship", "summer", "part-time"]
                            if any(tc in val.lower() or tc in cb_lbl.lower() for tc in target_checks):
                                if not await cb.is_checked():
                                    await cb.check(force=True)
                                    print(f"  ☑️  Work Exp: Checked {val or cb_lbl.strip()}")
                                    results["fields_filled"].append(f"Work exp: {val or cb_lbl.strip()}")

                    # Applicable skills / training
                    elif any(k in lbl_clean for k in ["training", "skills", "technologies", "proficient"]):
                        skills_set = get_resume_skills_set(profile)
                        all_skills = skills_set.union({
                            "ui/ux", "web app development", "devops", "bash", "database management",
                            "c/c++", "linux", "aws", "python", "javascript", "typescript", "sql"
                        })
                        for cb in cbs:
                            val = (await cb.get_attribute("value") or "").strip()
                            cb_lbl = await cb.evaluate("e => e.parentElement ? e.parentElement.innerText : ''")
                            candidate_text = (val or cb_lbl).strip().lower()
                            matched = False
                            for sk in all_skills:
                                if sk in candidate_text or candidate_text in sk:
                                    matched = True
                                    break
                            if matched:
                                if not await cb.is_checked():
                                    await cb.check(force=True)
                                    print(f"  ☑️  Skill: Checked {val or cb_lbl.strip()}")
                                    results["fields_filled"].append(f"Skill: {val or cb_lbl.strip()}")

                    # Areas of interest
                    elif any(k in lbl_clean for k in ["areas of interest", "interests", "focus"]):
                        target_interests = [
                            "api design", "graphical interface", "ui", "linux", "robotics",
                            "motion planning", "web programming", "data analysis", "data visualization"
                        ]
                        for cb in cbs:
                            val = (await cb.get_attribute("value") or "").strip()
                            cb_lbl = await cb.evaluate("e => e.parentElement ? e.parentElement.innerText : ''")
                            candidate_text = (val or cb_lbl).strip().lower()
                            if any(ti in candidate_text for ti in target_interests):
                                if not await cb.is_checked():
                                    await cb.check(force=True)
                                    print(f"  ☑️  Interest: Checked {val or cb_lbl.strip()}")
                                    results["fields_filled"].append(f"Interest: {val or cb_lbl.strip()}")
                except Exception:
                    continue
        except Exception as e:
            print(f"⚠️ Checkbox questionnaire notice: {e}")

        # 5. Custom Input & Textarea Matching for ATS Questionnaire Fields
        try:
            form_fields = await page.locator(".form-group, .resumator-row, div:has(> label)").all()
            for field in form_fields:
                try:
                    label_el = field.locator("label").first
                    if await label_el.count() == 0:
                        continue
                    label_raw = (await label_el.inner_text()).strip()
                    label_clean = re.sub(r"[\*\:\?]+$", "", label_raw).strip().lower()

                    # Handle text inputs and textareas
                    inp_el = field.locator("input[type='text'], textarea").first
                    if await inp_el.count() > 0 and await inp_el.is_visible():
                        curr_val = await inp_el.input_value()
                        if not curr_val or not curr_val.strip():
                            if "college" in label_clean or "university" in label_clean:
                                if "other" not in label_clean and "attended" not in label_clean:
                                    await inp_el.fill("New York University Abu Dhabi")
                                    print(f"  ✍️  {label_raw}: New York University Abu Dhabi")
                                    results["fields_filled"].append(label_raw)
                            elif "degree" in label_clean or "major" in label_clean:
                                await inp_el.fill("BSc in Computer Science")
                                print(f"  ✍️  {label_raw}: BSc in Computer Science")
                                results["fields_filled"].append(label_raw)
                            elif any(k in label_clean for k in ["source", "how did you hear", "hear of"]):
                                await inp_el.fill("LinkedIn")
                                print(f"  ✍️  {label_raw}: LinkedIn")
                                results["fields_filled"].append(label_raw)
                            elif "full stack" in label_clean and "experience" in label_clean:
                                await inp_el.fill("2 years")
                                print(f"  ✍️  {label_raw}: 2 years")
                                results["fields_filled"].append(label_raw)
                            elif "technologies" in label_clean and ("worked" in label_clean or "frontend" in label_clean):
                                ans = "Frontend: React, Next.js, TypeScript, JavaScript, Tailwind CSS, HTML/CSS. Backend: Node.js, Express, Python, Flask, MongoDB, REST APIs, Docker, Git."
                                await inp_el.fill(ans)
                                print(f"  ✍️  {label_raw}: {ans[:60]}...")
                                results["fields_filled"].append(label_raw)
                            elif "javascript frameworks" in label_clean:
                                ans = "React, Next.js, Node.js, Express, Astro.js, Capacitor, Vue.js"
                                await inp_el.fill(ans)
                                print(f"  ✍️  {label_raw}: {ans}")
                                results["fields_filled"].append(label_raw)
                            elif "salary" in label_clean or "compensation" in label_clean or "hourly" in label_clean or "rate" in label_clean:
                                inp_type = (await inp_el.get_attribute("type") or "").lower()
                                placeholder = (await inp_el.get_attribute("placeholder") or "").lower()
                                numeric_only = inp_type == "number" or "number" in placeholder or "digit" in placeholder
                                is_hourly = "hour" in label_clean or "rate" in label_clean or "hourly" in placeholder
                                desired_sal = calculate_desired_salary(
                                    body_text,
                                    region=curated.get("target_region", "uae"),
                                    numeric_only=numeric_only,
                                    is_hourly=is_hourly,
                                )
                                await inp_el.fill(desired_sal)
                                print(f"  ✍️  {label_raw} (Upper End): {desired_sal}")
                                results["fields_filled"].append(label_raw)
                            elif "experience" in label_clean or "how many years" in label_clean or "years" in label_clean or "months" in label_clean:
                                inp_type = (await inp_el.get_attribute("type") or "").lower()
                                is_num = inp_type == "number"
                                expects_m = "month" in label_clean
                                ans = get_tool_experience(label_clean, profile, numeric_only=is_num, expects_months=expects_m)
                                await inp_el.fill(ans)
                                print(f"  ✍️  {label_raw}: {ans}")
                                results["fields_filled"].append(label_raw)
                            elif "start date" in label_clean or "earliest start" in label_clean:
                                is_summer_2027 = "2027" in job_url or "2027" in body_text[:600]
                                ans = "05/17/2027" if is_summer_2027 else "Immediate / flexible"
                                await inp_el.fill(ans)
                                print(f"  ✍️  {label_raw}: {ans}")
                                results["fields_filled"].append(label_raw)
                            elif "unique" in label_clean or "catch our eye" in label_clean:
                                ans = "CS @ NYU (3.9 GPA), founder of VivahGo AI platform & built production GNNs. I combine research rigor with full-stack execution."
                                await inp_el.fill(ans)
                                print(f"  ✍️  {label_raw}: {ans}")
                                results["fields_filled"].append(label_raw)
                except Exception:
                    continue
        except Exception as e:
            print(f"⚠️ Inputs processor notice: {e}")

        await page.wait_for_timeout(1000)

        # Save Review Screenshot
        target_shot = screenshot_path or str(Path.cwd() / "application_review.png")
        await page.screenshot(path=target_shot, full_page=True)
        print(f"\n📸 Full-page review screenshot saved to: {target_shot}")
        results["screenshot"] = target_shot

        print("\n" + "=" * 60)
        print("🛑 STOPPED BEFORE SUBMIT (HUMAN-IN-THE-LOOP SAFETY GATE)")
        print("All candidate details, address fields, and resume have been populated.")
        print("The browser window is open for your manual review.")
        print("Press Enter in this terminal (or Ctrl+C) when you are finished.")
        print("=" * 60 + "\n")

        if pause_for_review and not headless:
            print("👀 Browser window is open on your screen for your manual review.")
            print("The session will stay open until you close the browser window or press Ctrl+C.")
            try:
                while not page.is_closed():
                    await asyncio.sleep(1)
            except (KeyboardInterrupt, asyncio.CancelledError):
                pass

        try:
            if not browser.is_connected():
                pass
            else:
                await browser.close()
        except Exception:
            pass
        return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Directly fill an application form without LLM API calls.")
    parser.add_argument("job_url", help="URL to job application form")
    parser.add_argument("--headless", action="store_true", help="Run browser headlessly")
    parser.add_argument("--screenshot", type=str, default=None, help="Path to save full-page review screenshot")
    args = parser.parse_args()

    asyncio.run(fill_application(args.job_url, headless=args.headless, screenshot_path=args.screenshot))


if __name__ == "__main__":
    main()
