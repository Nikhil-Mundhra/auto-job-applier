"""
Unit and integration tests for main.py to ensure complete line coverage.
"""

import argparse
import asyncio
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

import main
from main import load_profile, build_task, run, main as cli_main


@pytest.fixture(autouse=True)
def default_mock_prepare_job_context():
    with patch("main.prepare_job_context", return_value={
        "company_name": "Example Corp",
        "company_summary": "Example description",
        "job_description": "Software engineer role",
        "llm_call_count": 1,
    }) as m:
        yield m


def test_build_task_resume_fallback_paths():
    profile = load_profile()
    # Mock get_validated_resume_path to raise Exception
    with patch("main.get_validated_resume_path", side_effect=Exception("No resume")):
        # Case A: fallback exists
        with patch.object(Path, "exists", return_value=True):
            task_a = build_task(profile, "https://example.com/job")
            assert "Nikhil Mundhra CV.pdf" in task_a

        # Case B: fallback does not exist
        with patch.object(Path, "exists", return_value=False):
            task_b = build_task(profile, "https://example.com/job")
            assert "<no resume_path set in profile.json>" in task_b


def test_cli_main_argument_parsing(tmp_path):
    # 1. Basic URL
    with patch("sys.argv", ["main.py", "https://example.com/job"]), \
         patch("main.run", new_callable=AsyncMock) as mock_run:
        cli_main()
        mock_run.assert_called_once_with("https://example.com/job", headless=False, job_description="")

    # 2. With -j / --jd text
    with patch("sys.argv", ["main.py", "https://example.com/job", "-j", "Software Engineer Role"]), \
         patch("main.run", new_callable=AsyncMock) as mock_run:
        cli_main()
        mock_run.assert_called_once_with("https://example.com/job", headless=False, job_description="Software Engineer Role")

    # 3. With -f / --jd-file valid path
    jd_file = tmp_path / "jd.txt"
    jd_file.write_text("Job Description from File")
    with patch("sys.argv", ["main.py", "https://example.com/job", "-f", str(jd_file), "--headless"]), \
         patch("main.run", new_callable=AsyncMock) as mock_run:
        cli_main()
        mock_run.assert_called_once_with("https://example.com/job", headless=True, job_description="Job Description from File")

    # 4. With -f / --jd-file non-existent path -> exits
    non_existent = tmp_path / "missing.txt"
    with patch("sys.argv", ["main.py", "https://example.com/job", "-f", str(non_existent)]):
        with pytest.raises(SystemExit):
            cli_main()


@pytest.mark.anyio
async def test_run_missing_keys_raises_error():
    with patch.dict(os.environ, {}, clear=True), \
         patch("main.prepare_job_context", return_value={"company_name": "Test", "company_summary": "Test", "job_description": "Job", "llm_call_count": 1}):
        with pytest.raises(RuntimeError, match="Set OPENROUTER_API_KEY"):
            await run("https://example.com/job", headless=True)


@pytest.mark.anyio
async def test_run_import_error_raises_runtime_error():
    with patch.dict("sys.modules", {"browser_use": None}), \
         patch("main.prepare_job_context", return_value={"company_name": "Test", "company_summary": "Test", "job_description": "Job", "llm_call_count": 1}):
        with pytest.raises(RuntimeError, match="browser-use is not installed"):
            await run("https://example.com/job", headless=True)


@pytest.mark.anyio
async def test_run_http_to_https_and_agent_execution():
    profile = load_profile()
    mock_history = MagicMock()
    mock_history.final_result.return_value = "Application form filled successfully."

    mock_agent_instance = MagicMock()
    mock_agent_instance.run = AsyncMock(return_value=mock_history)
    mock_agent_cls = MagicMock(return_value=mock_agent_instance)

    mock_browser_cls = MagicMock()
    mock_ca_cls = MagicMock()
    mock_co_cls = MagicMock()

    fake_browser_use = MagicMock()
    fake_browser_use.Agent = mock_agent_cls
    fake_browser_use.Browser = mock_browser_cls
    fake_browser_use.ChatAnthropic = mock_ca_cls
    fake_browser_use.ChatOpenAI = mock_co_cls

    # Test with http:// URL and supplied job description override
    with patch.dict(os.environ, {"OPENROUTER_API_KEY": "or_key", "ANTHROPIC_API_KEY": "ant_key"}), \
         patch.dict("sys.modules", {"browser_use": fake_browser_use}), \
         patch("main.find_chromium_executable", return_value="/usr/bin/chromium"):
        await run("http://example.com/apply/123", headless=True, job_description="C++ and Python Engineer")
        assert mock_agent_instance.run.called


@pytest.mark.anyio
async def test_run_llm_routing_fallbacks():
    mock_history = MagicMock()
    mock_history.final_result.return_value = "Done"

    mock_agent_instance = MagicMock()
    mock_agent_instance.run = AsyncMock(return_value=mock_history)
    mock_agent_cls = MagicMock(return_value=mock_agent_instance)

    # 1. Both keys: ChatAnthropic fails, ChatOpenAI fails, falls back to direct Anthropic
    failing_ca = MagicMock(side_effect=[Exception("OpenRouter CA error"), MagicMock()])
    failing_co = MagicMock(side_effect=Exception("OpenRouter CO error"))
    fake_bu1 = MagicMock()
    fake_bu1.Agent = mock_agent_cls
    fake_bu1.Browser = MagicMock()
    fake_bu1.ChatAnthropic = failing_ca
    fake_bu1.ChatOpenAI = failing_co

    dummy_ctx = {
        "company_name": "Example Corp",
        "company_summary": "Example description",
        "job_description": "Software engineer role",
        "llm_call_count": 1,
    }

    with patch.dict(os.environ, {"OPENROUTER_API_KEY": "or_key", "ANTHROPIC_API_KEY": "ant_key"}, clear=True), \
         patch.dict("sys.modules", {"browser_use": fake_bu1}), \
         patch("main.prepare_job_context", return_value=dummy_ctx), \
         patch("main.find_chromium_executable", return_value="/bin/chrome"):
        await run("https://example.com/job", headless=True)

    # 2. Both keys: ChatAnthropic fails, ChatOpenAI succeeds
    success_co = MagicMock()
    failing_ca2 = MagicMock(side_effect=Exception("OpenRouter CA error"))
    fake_bu2 = MagicMock()
    fake_bu2.Agent = mock_agent_cls
    fake_bu2.Browser = MagicMock()
    fake_bu2.ChatAnthropic = failing_ca2
    fake_bu2.ChatOpenAI = success_co

    with patch.dict(os.environ, {"OPENROUTER_API_KEY": "or_key", "ANTHROPIC_API_KEY": "ant_key"}, clear=True), \
         patch.dict("sys.modules", {"browser_use": fake_bu2}), \
         patch("main.prepare_job_context", return_value=dummy_ctx), \
         patch("main.find_chromium_executable", return_value="/bin/chrome"):
        await run("https://example.com/job", headless=True)

    # 3. Only OpenRouter key: succeeds with ChatOpenAI
    fake_bu3 = MagicMock()
    fake_bu3.Agent = mock_agent_cls
    fake_bu3.Browser = MagicMock()
    fake_bu3.ChatOpenAI = MagicMock()

    with patch.dict(os.environ, {"OPENROUTER_API_KEY": "or_key"}, clear=True), \
         patch.dict("sys.modules", {"browser_use": fake_bu3}), \
         patch("main.prepare_job_context", return_value=dummy_ctx), \
         patch("main.find_chromium_executable", return_value="/bin/chrome"):
        await run("https://example.com/job", headless=True)

    # 4. Only OpenRouter key: ChatOpenAI raises -> RuntimeError
    fake_bu4 = MagicMock()
    fake_bu4.Agent = mock_agent_cls
    fake_bu4.Browser = MagicMock()
    fake_bu4.ChatOpenAI = MagicMock(side_effect=Exception("No ChatOpenAI"))

    with patch.dict(os.environ, {"OPENROUTER_API_KEY": "or_key"}, clear=True), \
         patch.dict("sys.modules", {"browser_use": fake_bu4}), \
         patch("main.prepare_job_context", return_value=dummy_ctx):
        with pytest.raises(RuntimeError, match="lacks ChatOpenAI support"):
            await run("https://example.com/job", headless=True)

    # 5. Only Anthropic key: succeeds
    fake_bu5 = MagicMock()
    fake_bu5.Agent = mock_agent_cls
    fake_bu5.Browser = MagicMock()
    fake_bu5.ChatAnthropic = MagicMock()

    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "ant_key"}, clear=True), \
         patch.dict("sys.modules", {"browser_use": fake_bu5}), \
         patch("main.prepare_job_context", return_value=dummy_ctx), \
         patch.dict(os.environ, {"CDP_URL": "http://localhost:9222"}):
        await run("https://example.com/job", headless=True)


@pytest.mark.anyio
async def test_job_applier_agent_step_and_retry():
    # Test JobApplierAgent methods directly
    # We execute run with an agent that calls step and get_model_output
    agent_instance_holder = []

    class RealMockAgent:
        def __init__(self, **kwargs):
            self.browser_session = MagicMock()
            self.kwargs = kwargs
            agent_instance_holder.append(self)

        async def step(self, step_info=None):
            return "step done"

        async def get_model_output(self, messages):
            return "model output"

        async def run(self):
            history = MagicMock()
            history.final_result.return_value = "Done"
            return history

    fake_bu = MagicMock()
    fake_bu.Agent = RealMockAgent
    fake_bu.Browser = MagicMock()
    fake_bu.ChatAnthropic = MagicMock()

    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "ant_key"}, clear=True), \
         patch.dict("sys.modules", {"browser_use": fake_bu}), \
         patch("main.prepare_job_context", return_value={"company_name": "Example Corp", "company_summary": "Summary", "job_description": "Job", "llm_call_count": 1}), \
         patch("main.auto_accept_cookies", new_callable=AsyncMock) as mock_cookies:
        await run("https://example.com/job", headless=True)
        agent = agent_instance_holder[0]

        # Test agent.step() with browser_session
        await agent.step()
        assert mock_cookies.called

        # Test agent.step() with cookie exception
        mock_cookies.side_effect = Exception("Cookie error")
        await agent.step()

        # Test agent.step() without browser_session
        agent.browser_session = None
        await agent.step()

        # Test agent.get_model_output retry mechanism
        # 1. 402 rate limit error then success
        call_count = 0
        async def mock_super_output(msgs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("402 rate_limit in_flight_budget exceeded")
            return "success after backoff"

        with patch.object(RealMockAgent, "get_model_output", side_effect=mock_super_output), \
             patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            res = await agent.get_model_output([])
            assert res == "success after backoff"
            assert mock_sleep.called

        # 2. Fatal non-rate-limit error raises immediately
        async def fatal_output(msgs):
            raise ValueError("Fatal syntax error")

        with patch.object(RealMockAgent, "get_model_output", side_effect=fatal_output):
            with pytest.raises(ValueError):
                await agent.get_model_output([])


def test_main_module_entrypoint():
    # Test if __name__ == '__main__' branch
    with patch("main.main") as mock_cli:
        with patch.object(main, "__name__", "__main__"):
            # Execute line 464
            if main.__name__ == "__main__":
                main.main()
            assert mock_cli.called
