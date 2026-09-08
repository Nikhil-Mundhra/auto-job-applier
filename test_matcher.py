"""
Tests for portfolio curation and relevance matching in matcher.py and build_task() in main.py.
"""

import json
from pathlib import Path
from matcher import extract_keywords, curate_profile, detect_application_region
from main import load_profile, build_task


def test_ai_engineer_matching():
    profile = load_profile()
    ai_jd = """
    We are seeking an AI Engineer / Machine Learning Researcher to build cutting-edge
    deep learning models, computer vision systems, and LLM applications.
    Requirements:
    - Experience with Python, PyTorch, and convolutional neural networks (CNN)
    - Exposure to Graph Neural Networks (GNN) and LLM explainability / prompt engineering
    - ETL data pipelines and API development
    """
    curated = curate_profile(profile, job_description=ai_jd)

    experiences = curated["work_history"]
    assert len(experiences) <= 3
    assert experiences[0]["company"] == "Kanerika Software Pvt. Ltd."
    assert "Kanerika" in experiences[0]["company"]

    # Capstone CNN should be selected as the top project
    projects = curated["projects"]
    assert len(projects) >= 1
    assert projects[0]["name"] == "OCT Analyser Capstone"

    # PyTorch and Python should be present in skills
    languages = curated["skills"]["programming_languages"]
    assert "Python" in languages[:3]


def test_fullstack_matching():
    profile = load_profile()
    fullstack_jd = """
    Senior Full Stack Developer needed to build high scale web and mobile applications.
    Requirements:
    - Proficiency in React, TypeScript, Node.js, Express, and MongoDB
    - Experience in system design, Capacitor / cross-platform mobile apps, and REST APIs
    - Proven track record of owning full product lifecycle from UI/UX to cloud deployment
    """
    curated = curate_profile(profile, job_description=fullstack_jd)

    experiences = curated["work_history"]
    # VivahGo (Founder & Lead Software Engineer) should be top
    assert experiences[0]["company"] == "VivahGo Planners"

    # Cool Reminders should be selected as a relevant project
    project_names = [p["name"] for p in curated["projects"]]
    assert "Cool Reminders Web App" in project_names

    # React, Node.js, Express should be prioritized in frameworks
    frameworks = curated["skills"]["frameworks_and_libraries"]
    assert frameworks[0] in ["React", "Node.js", "Express", "MongoDB Atlas"]


def test_cybersecurity_matching():
    profile = load_profile()
    cyber_jd = """
    Industrial Cybersecurity Intern / Systems Engineer.
    Responsibilities:
    - Evaluate operational technology (OT) cybersecurity models and network segmentation
    - Ensure compliance with IEC 62443 international standards
    - Conduct system validation and verification (V&V) and diagnostics
    """
    curated = curate_profile(profile, job_description=cyber_jd)

    experiences = curated["work_history"]
    assert experiences[0]["company"] == "Alstom Transport India Limited"
    assert "iec 62443" in [k.lower() for k in experiences[0]["_matched_keywords"]]


def test_data_analyst_matching():
    profile = load_profile()
    data_jd = """
    Marketing Data Analyst:
    - Statistical analysis using STATA and Python
    - Customer segmentation, churn prediction, and e-commerce analytics (Shopify)
    - SQL database querying and digital marketing optimization
    """
    curated = curate_profile(profile, job_description=data_jd)

    experiences = curated["work_history"]
    assert experiences[0]["company"] == "Phool.co"


def test_default_empty_jd():
    profile = load_profile()
    curated = curate_profile(profile, job_description="")
    assert curated["tailoring_summary"]["mode"] == "default"
    assert len(curated["work_history"]) == 3
    assert len(curated["projects"]) == 2


def test_build_task_prompt():
    profile = load_profile()
    ai_jd = "Python, PyTorch, Deep Learning, Computer Vision Researcher"
    task = build_task(profile, job_url="https://example.com/careers/apply", job_description=ai_jd)

    assert "https://example.com/careers/apply" in task
    assert "CURATED PROFILE:" in task
    assert "Kanerika Software Pvt. Ltd." in task
    assert "Stop as soon as you reach the final review or submit page" in task
    assert "click Submit" in task


def test_detect_application_region():
    # India URLs
    assert detect_application_region(job_url="https://cigna.wd5.myworkdayjobs.com/en-US/cignacareers/job/Hyderabad-India/Software-Engineering-Analyst") == "india"
    assert detect_application_region(job_url="https://jobs.lever.co/company-india/12345") == "india"
    assert detect_application_region(job_url="https://careers.google.co.in/jobs/123") == "india"
    assert detect_application_region(job_url="https://hpe.wd5.myworkdayjobs.com/job/Bengaluru-Karntaka-India/Systems-Software-Engineer") == "india"

    # India Job Descriptions
    india_jd = "Role: Full Stack Engineer\nLocation: Bengaluru, India\nTech: React, Node.js"
    assert detect_application_region(job_description=india_jd) == "india"

    delhi_jd = "Software Developer based in New Delhi. Requirements: Python, Django."
    assert detect_application_region(job_description=delhi_jd) == "india"

    # US / UAE / International positions
    us_jd = "Cloud Engineer in Reston, VA. Requires Active Top Secret Clearance and US Citizenship."
    assert detect_application_region(job_description=us_jd, job_url="http://acclaimtechnicalservices.applytojob.com/apply/Q9pBqegwWF/Cloud-Engineer-20260194") == "uae"

    uae_jd = "AI Research Scientist at Technology Innovation Institute, Abu Dhabi, UAE."
    assert detect_application_region(job_description=uae_jd) == "uae"

    empty_jd = ""
    assert detect_application_region(job_description=empty_jd) == "uae"


def test_indiana_not_matched_as_india():
    # Jobs in Indiana state (USA) should NOT match India
    indiana_url = "https://stryker.wd1.myworkdayjobs.com/en-US/strykercareers/job/Fort-Wayne-Indiana/Summer-2027-Internship---Software-Engineering---Indiana_R572631"
    assert detect_application_region(job_url=indiana_url) == "uae"

    indianapolis_url = "https://simon.wd1.myworkdayjobs.com/en-US/simon/job/Indianapolis-IN/Intern---Front-End-Developer_R13975"
    assert detect_application_region(job_url=indianapolis_url) == "uae"

    indiana_jd = "Software Engineer needed at our headquarters in Fort Wayne, Indiana. Must be authorized to work in the US."
    assert detect_application_region(job_description=indiana_jd) == "uae"


def test_address_curation_india():
    profile = load_profile()
    india_url = "https://kyndryl.wd5.myworkdayjobs.com/en-US/kyndrylprofessionalcareers/job/Gurgaon-Haryana-India/Software-Developer---AI_R-63233"
    curated = curate_profile(profile, job_description="AI Developer in Gurgaon, India", job_url=india_url)

    assert curated["target_region"] == "india"
    assert curated["phone"] == "+91 7060410033"
    assert "79, West Mukherjee Nagar" in curated["address"]["street_address"]
    assert curated["address"]["city"] == "New Delhi"
    assert curated["address"]["postal_code"] == "110009"
    assert curated["address"]["country"] == "India"


def test_address_curation_uae_and_intl():
    profile = load_profile()
    intl_url = "http://acclaimtechnicalservices.applytojob.com/apply/Q9pBqegwWF/Cloud-Engineer-20260194"
    curated = curate_profile(profile, job_description="Cloud Engineer in Reston, VA", job_url=intl_url)

    assert curated["target_region"] == "uae"
    assert curated["phone"] == "+971 503526342"
    assert "New York University Abu Dhabi" in curated["address"]["street_address"]
    assert curated["address"]["city"] == "Abu Dhabi"
    assert curated["address"]["country"] == "United Arab Emirates"


def test_build_task_address_mapping():
    profile = load_profile()
    # Test UAE / International address prompt mapping
    intl_task = build_task(profile, job_url="http://acclaimtechnicalservices.applytojob.com/apply/Q9pBqegwWF/Cloud-Engineer-20260194")
    assert "ADDRESS & CONTACT INFORMATION (APPLICATION TARGET REGION: UAE):" in intl_task
    assert 'Address / Street / Address Line 1: "New York University Abu Dhabi, Saadiyat Island, P.O. Box 129188"' in intl_task
    assert 'City: "Abu Dhabi"' in intl_task
    assert 'Country: "United Arab Emirates"' in intl_task
    assert '+971 503526342' in intl_task

    # Test India address prompt mapping
    india_url = "https://aresmgmt.wd1.myworkdayjobs.com/en-US/external/job/Mumbai-India/Full-Stack-Developer"
    india_task = build_task(profile, job_url=india_url, job_description="Full Stack Developer in Mumbai, India")
    assert "ADDRESS & CONTACT INFORMATION (APPLICATION TARGET REGION: INDIA):" in india_task
    assert 'Address / Street / Address Line 1: "79, West Mukherjee Nagar"' in india_task
    assert 'City: "New Delhi"' in india_task
    assert 'Postal / Zip Code: "110009"' in india_task
    assert 'Country: "India"' in india_task
    assert '+91 7060410033' in india_task


def test_demographics_and_dob():
    profile = load_profile()
    # Profile JSON level
    assert profile.get("gender") == "Male"
    assert profile.get("ethnicity") == "North Indian"
    assert profile.get("nationality") == "Indian"
    assert profile.get("date_of_birth") == "28/10/2005"
    assert profile.get("dob_iso") == "2005-10-28"
    assert profile.get("dob_day") in ["28", 28]
    assert profile.get("dob_month") in ["10", 10]
    assert profile.get("dob_year") in ["2005", 2005]

    # Screening preferences level
    prefs = profile.get("screening_preferences", {})
    assert prefs.get("gender") == "Male"
    assert prefs.get("ethnicity") == "North Indian"
    assert prefs.get("date_of_birth") == "28/10/2005"

    # Curate profile level
    curated = curate_profile(profile, job_url="http://acclaimtechnicalservices.applytojob.com/apply/Q9pBqegwWF/Cloud-Engineer-20260194")
    assert curated["gender"] == "Male"
    assert curated["ethnicity"] == "North Indian"
    assert curated["nationality"] == "Indian"
    assert curated["date_of_birth"] == "28/10/2005"
    assert curated["dob_iso"] == "2005-10-28"

    # Task prompt level
    task = build_task(profile, job_url="http://acclaimtechnicalservices.applytojob.com/apply/Q9pBqegwWF/Cloud-Engineer-20260194")
    assert "Gender: Male" in task
    assert "Ethnicity / Race: North Indian" in task
    assert 'Date of Birth (DD/MM/YYYY): "28/10/2005"' in task
    assert 'Date of Birth (ISO YYYY-MM-DD): "2005-10-28"' in task


def test_salary_and_unlisted_tools():
    from matcher import calculate_desired_salary, get_tool_experience
    profile = load_profile()

    # Salary near upper end
    jd_with_range = "The proposed salary range for this position is: $100,000.00 - $190,000"
    assert calculate_desired_salary(jd_with_range) in ["$175,000", "$180,000"]
    assert calculate_desired_salary(jd_with_range, numeric_only=True) in ["175000", "180000"]

    # Salary default when no range is posted
    assert "18" in calculate_desired_salary("", region="india")
    assert "120" in calculate_desired_salary("", region="uae")

    # Tool experience: in resume
    assert get_tool_experience("python", profile) == "2 years"
    assert get_tool_experience("react", profile, numeric_only=True) == "2"

    # Tool experience: NOT in resume -> 1 year or 6 months
    assert get_tool_experience("PHP Laravel/Lumen", profile) == "1 year"
    assert get_tool_experience("PHP Laravel/Lumen", profile, numeric_only=True) == "1"
    assert get_tool_experience("Kubernetes", profile, expects_months=True) == "6 months"
    assert get_tool_experience("Kubernetes", profile, numeric_only=True, expects_months=True) == "6"

    # Build task prompt contains rules
    task = build_task(profile, job_url="http://advicemedia.applytojob.com/apply/xpWlOQ91He/Full-Stack-Engineer-I")
    assert "When GPA is optional (no asterisk *, not required), LEAVE IT BLANK." in task
    assert 'fill: "3.6"' in task
    assert "nearer to the upper end of the posted compensation range" in task
    assert 'ALWAYS answer "Yes"' in task
    assert 'write either "1 year" or "6 months"' in task


if __name__ == "__main__":
    test_ai_engineer_matching()
    test_fullstack_matching()
    test_cybersecurity_matching()
    test_data_analyst_matching()
    test_default_empty_jd()
    test_build_task_prompt()
    test_detect_application_region()
    test_indiana_not_matched_as_india()
    test_address_curation_india()
    test_address_curation_uae_and_intl()
    test_build_task_address_mapping()
    test_demographics_and_dob()
    test_salary_and_unlisted_tools()
    print("All tests passed successfully!")
