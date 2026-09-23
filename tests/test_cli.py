"""
Unit tests

This test suite covers the main CLI functions including authentication,
repository handling, user input validation, API estimation, workflow run
classification, and deletion operations.
"""

import os
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pandas as pd
import pytest
from click.testing import CliRunner
from github import GithubException

from delete_workflow_runs.cli import (
    break_down_df_all_runs,
    check_user_inputs,
    delete_active_workflow_runs_max_days,
    delete_active_workflow_runs_min_runs,
    delete_orphan_workflow_runs,
    get_api_estimate,
    get_auth,
    get_repo,
    main,
)


class TestGetAuth:
    """Tests for the get_auth() function which authenticates with GitHub API.

    These tests verify that the authentication function correctly handles:
    - Valid token authentication
    - Missing token scenarios
    - Invalid token scenarios
    """

    def test_get_auth_success(self, monkeypatch):
        """Test successful authentication with a valid token.

        Verifies that get_auth() returns a valid GitHub client when
        a valid GH_TOKEN is provided in the environment.
        """
        monkeypatch.setenv("GH_TOKEN", "valid_token")
        with patch("delete_workflow_runs.cli.Github") as mock_github:
            mock_user = Mock()
            mock_user.login = "test_user"
            mock_gh = mock_github.return_value
            mock_gh.get_user.return_value = mock_user
            gh = get_auth()
            assert gh is not None
            mock_github.assert_called_once()

    def test_get_auth_missing_token(self, monkeypatch):
        """Test authentication failure when GH_TOKEN is missing.

        Verifies that get_auth() raises KeyError when no token is
        provided in the environment variables.
        """
        if "GH_TOKEN" in os.environ:
            monkeypatch.delenv("GH_TOKEN")
        with pytest.raises(KeyError):
            get_auth()

    def test_get_auth_invalid_token(self, monkeypatch):
        """Test authentication failure with an invalid token.

        Verifies that get_auth() raises PermissionError when an
        invalid or expired token is provided.
        """
        if "GH_TOKEN" in os.environ:
            monkeypatch.setenv("GH_TOKEN", "1212212")
        with pytest.raises(PermissionError):
            get_auth()


class TestGetRepo:
    """Tests for the get_repo() function which extracts repository information from URLs.

    These tests verify that the function correctly handles both HTTPS and SSH repository URLs.
    """

    def test_https_url(self, monkeypatch):
        """Test repository URL parsing with HTTPS format.

        Verifies that get_repo() correctly parses HTTPS URLs in the format:
        https://github.com/owner/repo.git
        """
        monkeypatch.setenv("GH_TOKEN", "valid_token")
        with patch("delete_workflow_runs.cli.Github") as mock_github:
            mock_user = Mock()
            mock_user.login = "test_user"
            mock_gh = mock_github.return_value
            mock_gh.get_user.return_value = mock_user
            gh = get_auth()
            repo_url = "https://github.com/owner/repo.git"
            assert get_repo(gh, repo_url)

    def test_ssh_url(self, monkeypatch):
        """Test repository URL parsing with SSH format.

        Verifies that get_repo() correctly parses SSH URLs in the format:
        git@github.com:owner/repo.git
        """
        monkeypatch.setenv("GH_TOKEN", "valid_token")
        with patch("delete_workflow_runs.cli.Github") as mock_github:
            mock_user = Mock()
            mock_user.login = "test_user"
            mock_gh = mock_github.return_value
            mock_gh.get_user.return_value = mock_user
            gh = get_auth()
            repo_url = "git@github.com:owner/repo.git"
            assert get_repo(gh, repo_url)


class TestCheckUserInputs:
    """Tests for the check_user_inputs() validation function.

    This function validates that exactly one of min_runs or max_days is provided,
    and that any provided value is non-negative.

    Test cases cover:
    - Both parameters provided (invalid)
    - Neither parameter provided (invalid)
    - Negative values (invalid)
    - Valid single parameter values
    """

    def test_both_min_runs_and_max_days(self):
        """Test rejection when both min_runs and max_days are provided.

        Verifies that check_user_inputs() returns False when both parameters
        are specified, as only one deletion criterion should be used at a time.
        """
        assert not check_user_inputs(5, 5)

    def test_neither_min_nor_max(self):
        """Test rejection when neither min_runs nor max_days is provided.

        Verifies that check_user_inputs() returns False when no deletion
        criteria are specified at all.
        """
        assert not check_user_inputs(None, None)

    def test_min_runs_negative(self):
        """Test rejection of negative min_runs value.

        Verifies that check_user_inputs() returns False when min_runs is
        negative, as only non-negative integers are valid.
        """
        assert not check_user_inputs(-1, None)

    def test_max_days_negative(self):
        """Test rejection of negative max_days value.

        Verifies that check_user_inputs() returns False when max_days is
        negative, as only non-negative integers are valid.
        """
        assert not check_user_inputs(None, -1)

    def test_valid_min_runs(self):
        """Test acceptance of valid min_runs parameter.

        Verifies that check_user_inputs() returns True when a positive
        min_runs value is provided without max_days.
        """
        assert check_user_inputs(5, None)

    def test_valid_max_days(self):
        """Test acceptance of valid max_days parameter.

        Verifies that check_user_inputs() returns True when a positive
        max_days value is provided without min_runs.
        """
        assert check_user_inputs(None, 5)


class TestGetApiEstimate:
    """Tests for the get_api_estimate() function which calculates API usage estimates.

    This function estimates the number of API calls needed for deletion operations,
    which helps users understand their API rate limit consumption.
    """

    def test_api_estimate_calculation(self):
        """Test API estimate calculation with equal orphan and active runs.

        Verifies that get_api_estimate() correctly calculates the total API
        usage estimate using the formula: (total * 2) + (total // 100 + 1) + 3
        where total = orphan + active runs.
        """
        orphan = 50
        active = 50
        total = orphan + active
        estimate = get_api_estimate(orphan, active)
        assert estimate == (total * 2) + (total // 100 + 1) + 3


class TestBreakDownDfAllRuns:
    """Tests for the break_down_df_all_runs() function which separates workflow runs.

    This function categorizes workflow runs into orphan runs (from deleted workflows)
    and active runs (from existing workflows), which is essential for the deletion
    logic.
    """

    def test_break_down_with_orphans(self):
        """Test separation of workflow runs when orphans are present.

        Verifies that break_down_df_all_runs() correctly identifies runs
        belonging to deleted workflows as orphans and separates them from
        active runs belonging to existing workflows.
        """
        df_all_runs = pd.DataFrame(
            {
                "workflow_id": [101, 102, 201],
                "run_id": [1011, 1021, 2011],
                "created_at": [datetime(2023, 1, 1, tzinfo=timezone.utc)] * 3,
                "name": ["wf1", "wf2", "wf3"],
            }
        )

        mock_workflow1 = Mock(id=101)
        mock_workflow2 = Mock(id=102)
        mock_repo = Mock()
        mock_repo.get_workflows.return_value = [mock_workflow1, mock_workflow2]
        df_orphan_runs, df_active_runs = break_down_df_all_runs(mock_repo, df_all_runs)
        assert len(df_orphan_runs) == 1
        assert len(df_active_runs) == 2


class TestDeleteOrphanWorkflowRuns:
    """Tests for the delete_orphan_workflow_runs() function.

    This function deletes workflow runs that are no longer associated with
    any existing workflow definition in the repository (orphan runs).

    Test cases cover both dry-run and actual deletion scenarios.
    """

    def test_delete_orphan_runs_dry_run(self):
        """Test dry-run mode for deleting orphan workflow runs.

        Verifies that in dry-run mode, the function counts the number of
        orphan runs without actually deleting them from the repository.
        """
        df_orphan = pd.DataFrame({"run_id": [101010, 101020]})
        mock_repo = Mock()
        count = delete_orphan_workflow_runs(mock_repo, dry_run=True, df_orphan_runs=df_orphan)
        assert count == 2

    def test_delete_orphan_runs(self):
        """Test actual deletion of orphan workflow runs.

        Verifies that the function correctly deletes orphan runs from the
        repository when not in dry-run mode.
        """
        df_orphan = pd.DataFrame({"run_id": [101, 102, 103]})
        mock_repo = Mock()
        count = delete_orphan_workflow_runs(mock_repo, dry_run=False, df_orphan_runs=df_orphan)
        assert count == 3


class TestDeleteActiveWorkflowRunsMinRuns:
    """Tests for the delete_active_workflow_runs_min_runs() function.

    This function deletes older workflow runs when the number of runs exceeds
    the minimum threshold (min_runs), keeping only the most recent runs.

    Test cases cover:
    - Dry-run deletion with min_runs threshold
    - No deletion when min_runs is higher than actual run count
    - Actual deletion of older runs
    """

    def test_delete_active_runs_min_runs_dry_run_true(self):
        """Test dry-run deletion with min_runs threshold.

        Verifies that with 5 runs and min_runs=1, the function identifies
        4 runs for deletion in dry-run mode (keeping only the most recent run).
        """
        df_active = pd.DataFrame(
            {
                "name": [
                    "workflow-01",
                    "workflow-01",
                    "workflow-01",
                    "workflow-01",
                    "workflow-01",
                ],
                "run_id": [90001, 90002, 90003, 90004, 90005],
                "workflow_id": [101] * 5,
                "created_at": [datetime(2023, 1, 1, tzinfo=timezone.utc)] * 5,
            }
        )
        mock_repo = Mock()
        count = delete_active_workflow_runs_min_runs(mock_repo, dry_run=True, min_runs=1, df=df_active)
        assert count == 4

    def test_delete_active_runs_min_runs_dry_run_true_no_delete(self):
        """Test dry-run with min_runs threshold higher than actual run count.

        Verifies that when min_runs (20) is much higher than the actual
        number of runs (4), no runs are marked for deletion.
        """
        df_active = pd.DataFrame(
            {
                "name": ["workflow-01", "workflow-01", "workflow-01", "workflow-01"],
                "run_id": [60001, 60002, 60003, 60004],
                "workflow_id": [1] * 4,
                "created_at": [datetime(2023, 1, 1, tzinfo=timezone.utc)] * 4,
            }
        )
        mock_repo = Mock()
        count = delete_active_workflow_runs_min_runs(mock_repo, dry_run=True, min_runs=20, df=df_active)
        assert count == 0

    def test_delete_active_runs_min_runs_dry_run_false(self):
        """Test actual deletion with min_runs threshold.

        Verifies that the function correctly deletes runs when not in
        dry-run mode, keeping only the specified minimum number of runs.
        """
        df_active = pd.DataFrame(
            {
                "name": [
                    "workflow-01",
                    "workflow-01",
                    "workflow-01",
                    "workflow-01",
                    "workflow-01",
                ],
                "run_id": [40001, 40002, 4003, 40004, 40005],
                "workflow_id": [1] * 5,
                "created_at": [datetime(2023, 1, 1, tzinfo=timezone.utc)] * 5,
            }
        )
        mock_repo = Mock()
        count = delete_active_workflow_runs_min_runs(mock_repo, dry_run=False, min_runs=2, df=df_active)
        assert count == 3


class TestDeleteActiveWorkflowRunsMaxDays:
    """Tests for the delete_active_workflow_runs_max_days() function.

    This function deletes workflow runs that are older than a specified number of days
    (max_days), keeping only recent runs within the threshold.

    Test cases cover:
    - Dry-run deletion of old runs
    - No deletion when all runs are within the threshold
    - Actual deletion of expired runs
    """

    def test_delete_active_runs_max_days_dry_run_true(self):
        """Test dry-run deletion of runs older than max_days threshold.

        Verifies that with 4 runs all older than 30 days, the function
        identifies all 4 runs for deletion in dry-run mode.
        """
        df_active = pd.DataFrame(
            {
                "name": ["workflow-01", "workflow-01", "workflow-01", "workflow-01"],
                "run_id": [30001, 30002, 30003, 30004],
                "workflow_id": [101] * 4,
                "created_at": [datetime(2023, 1, 1, tzinfo=timezone.utc)] * 4,
            }
        )
        mock_repo = Mock()
        count = delete_active_workflow_runs_max_days(mock_repo, dry_run=True, max_days=30, df=df_active)
        assert count == 4

    def test_delete_active_runs_max_days_dry_run_true_no_wf_delete(self):
        """Test dry-run with all runs within the max_days threshold.

        Verifies that when all runs are newer than max_days (2000 days),
        no runs are marked for deletion.
        """
        df_active = pd.DataFrame(
            {
                "name": ["workflow-01", "workflow-01", "workflow-01", "workflow-01"],
                "run_id": [70001, 70002, 70003, 70004],
                "workflow_id": [101] * 4,
                "created_at": [datetime(2025, 1, 1, tzinfo=timezone.utc)] * 4,
            }
        )
        mock_repo = Mock()
        count = delete_active_workflow_runs_max_days(mock_repo, dry_run=True, max_days=2000, df=df_active)
        assert count == 0

    def test_delete_active_runs_max_days_dry_run_false(self):
        """Test actual deletion of runs older than max_days threshold.

        Verifies that the function correctly deletes runs when not in
        dry-run mode, removing only runs older than the specified threshold.
        """
        df_active = pd.DataFrame(
            {
                "name": ["workflow-1", "workflow-1", "workflow-1", "workflow-1"],
                "run_id": [50101, 50102, 50103, 50104],
                "workflow_id": [1] * 4,
                "created_at": [datetime(2023, 1, 1, tzinfo=timezone.utc)] * 4,
            }
        )
        mock_repo = Mock()
        count = delete_active_workflow_runs_max_days(mock_repo, dry_run=False, max_days=30, df=df_active)
        assert count == 4


class TestMainMock:
    """Tests for the main() CLI function with mocked GitHub API responses.

    These tests verify that the CLI correctly handles various error scenarios
    by mocking GitHub API responses, including authentication errors (401, 403),
    repository not found errors (404), and invalid repository URLs.
    """

    def test_cli_main_mock_401(self, monkeypatch):
        """Test CLI handling of 401 Unauthorized error.

        Verifies that when the GitHub API returns a 401 error (authentication
        failure), the CLI exits with code 1 and handles the error gracefully.
        """
        runner = CliRunner()
        monkeypatch.setenv("GH_TOKEN", "invalid_token")
        with patch("delete_workflow_runs.cli.get_auth") as mock_auth:
            mock_gh = Mock()
            mock_auth.return_value = mock_gh
            mock_gh.get_repo.side_effect = GithubException(401, "Authentication error")
            result = runner.invoke(
                main,
                ["--repo-url", "https://github.com/owner/repo", "--max-days", "30"],
            )
            assert result.exit_code == 1

    def test_cli_main_mock_403(self, monkeypatch):
        """Test CLI handling of 403 Forbidden error.

        Verifies that when the GitHub API returns a 403 error (permission
        denied), the CLI exits with code 1 and handles the error gracefully.
        """
        runner = CliRunner()
        monkeypatch.setenv("GH_TOKEN", "invalid_token")
        with patch("delete_workflow_runs.cli.get_auth") as mock_auth:
            mock_gh = Mock()
            mock_auth.return_value = mock_gh
            mock_gh.get_repo.side_effect = GithubException(403, "Permission error")
            result = runner.invoke(
                main,
                ["--repo-url", "https://github.com/owner/repo", "--max-days", "30"],
            )
            assert result.exit_code == 1

    def test_cli_main_mock_404(self):
        """Test CLI handling of 404 Not Found error.

        Verifies that when the GitHub API returns a 404 error (repository
        not found), the CLI exits with code 1 and displays an appropriate error.
        """
        runner = CliRunner()
        with patch("delete_workflow_runs.cli.get_auth") as mock_auth:
            mock_gh = Mock()
            mock_auth.return_value = mock_gh
            mock_gh.get_repo.side_effect = GithubException(404, "Not found")
            result = runner.invoke(
                main,
                [
                    "--repo-url",
                    "https://github.com/invalid/repo",
                    "--max-days",
                    "30",
                    "--dry-run",
                    "true",
                ],
            )
            assert result.exit_code == 1

    def test_cli_main_mock_non_github_url(self):
        """Test CLI handling of invalid repository URL.

        Verifies that when an invalid GitHub URL is provided (not matching
        the expected GitHub hostname patterns), the CLI exits with code 1.
        """
        runner = CliRunner()
        with patch("delete_workflow_runs.cli.get_auth") as mock_auth:
            mock_gh = Mock()
            mock_auth.return_value = mock_gh
            result = runner.invoke(
                main,
                [
                    "--repo-url",
                    "https://github-test.com/owner/repo",
                    "--max-days",
                    "30",
                    "--dry-run",
                    "true",
                ],
            )
            assert result.exit_code == 1


class TestMain:
    """End-to-end tests for the main() CLI entry point using Click's CliRunner.

    These tests verify the full CLI workflow including argument parsing,
    GitHub API interaction (real or mocked), and output generation.
    """

    def test_cli_main_input_false(self):
        """Test CLI with invalid input parameter.

        Verifies that when an invalid value ("NA") is provided for max-days,
        the CLI exits with code 2 (usage error) due to Click's type validation.
        """
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--repo-url",
                "https://github.com/tagdots/delete-workflow-runs",
                "--max-days",
                "NA",
                "--dry-run",
                "false",
            ],
        )
        assert result.exit_code == 2

    def test_cli_main_min_runs_dry_run(self):
        """Test CLI with min-runs parameter in dry-run mode.

        Verifies that the CLI executes successfully with --min-runs 100
        and --dry-run true, keeping only the 100 most recent runs per workflow.
        """
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--repo-url",
                "https://github.com/tagdots/delete-workflow-runs",
                "--min-runs",
                "100",
                "--dry-run",
                "true",
            ],
        )
        assert result.exit_code == 0
        assert "dry-run: True" in result.output

    def test_cli_main_max_days_dry_run(self):
        """Test CLI with max-days parameter in dry-run mode.

        Verifies that the CLI executes successfully with --max-days 5
        and --dry-run true, keeping only workflows from the last 5 days.
        """
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--repo-url",
                "https://github.com/tagdots/delete-workflow-runs",
                "--max-days",
                "5",
                "--dry-run",
                "true",
            ],
        )
        assert result.exit_code == 0
        assert "dry-run: True" in result.output

    def test_cli_main_min_runs_dry_run_404(self):
        """Test CLI with non-existent repository (404 error).

        Verifies that when the repository doesn't exist, the CLI exits
        with a non-zero code and displays an appropriate error message.
        """
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--repo-url",
                "https://github.com/tagdots/repo-not-found",
                "--min-runs",
                "100",
                "--dry-run",
                "true",
            ],
        )
        assert result.exit_code > 0
        assert "dry-run: True" in result.output
        assert "repository not found" in result.output

    def test_cli_main_both_min_runs_and_max_days(self):
        """Test CLI with both --min-runs and --max-days provided.

        Verifies that when both parameters are specified, check_user_inputs()
        returns False and the CLI skips the deletion logic (covers branch 684->735).
        """
        runner = CliRunner()
        with patch("delete_workflow_runs.cli.write_data_dict") as mock_write:
            result = runner.invoke(
                main,
                [
                    "--repo-url",
                    "https://github.com/tagdots/delete-workflow-runs",
                    "--min-runs",
                    "5",
                    "--max-days",
                    "5",
                    "--dry-run",
                    "true",
                ],
            )
            assert result.exit_code == 0
            mock_write.assert_called_once()

    def test_cli_main_dry_run_false(self):
        """Test CLI with dry_run=False (actual deletion mode).

        Verifies that when --dry-run is set to false, the CLI proceeds
        with actual deletion operations (covers branch 722->735).
        """
        runner = CliRunner()
        active_df = pd.DataFrame(
            {
                "name": ["workflow-01"],
                "run_id": [1],
                "workflow_id": [101],
                "created_at": [datetime(2023, 1, 1, tzinfo=timezone.utc)],
            }
        )
        with (
            patch("delete_workflow_runs.cli.get_auth"),
            patch("delete_workflow_runs.cli.get_repo", return_value=Mock()),
            patch("delete_workflow_runs.cli.get_all_workflow_runs", return_value=active_df),
            patch("delete_workflow_runs.cli.break_down_df_all_runs", return_value=(pd.DataFrame(), active_df)),
            patch("delete_workflow_runs.cli.delete_orphan_workflow_runs", return_value=0),
            patch("delete_workflow_runs.cli.delete_active_workflow_runs_min_runs", return_value=pd.Series([0])),
            patch("delete_workflow_runs.cli.get_core_api_rate_limit", return_value=(1000, datetime.now(timezone.utc))),
            patch("delete_workflow_runs.cli.write_data_dict") as mock_write,
        ):
            result = runner.invoke(
                main,
                [
                    "--repo-url",
                    "https://github.com/tagdots/delete-workflow-runs",
                    "--min-runs",
                    "1",
                    "--dry-run",
                    "false",
                ],
            )
            assert result.exit_code == 0
            mock_write.assert_called_once()

    def test_cli_main_insufficient_api_limit(self):
        """Test CLI when API rate limit is insufficient.

        Verifies that the CLI displays a warning message when the estimated
        API usage exceeds the available rate limit (covers branches 730-731).
        """
        runner = CliRunner()
        active_df = pd.DataFrame(
            {
                "name": ["workflow-01"] * 100,
                "run_id": list(range(1, 101)),
                "workflow_id": [101] * 100,
                "created_at": [datetime(2023, 1, 1, tzinfo=timezone.utc)] * 100,
            }
        )
        with (
            patch("delete_workflow_runs.cli.get_auth"),
            patch("delete_workflow_runs.cli.get_repo", return_value=Mock()),
            patch("delete_workflow_runs.cli.get_all_workflow_runs", return_value=active_df),
            patch("delete_workflow_runs.cli.break_down_df_all_runs", return_value=(pd.DataFrame(), active_df)),
            patch("delete_workflow_runs.cli.delete_orphan_workflow_runs", return_value=0),
            patch("delete_workflow_runs.cli.delete_active_workflow_runs_min_runs", return_value=pd.Series([99])),
            patch("delete_workflow_runs.cli.get_core_api_rate_limit", return_value=(10, datetime.now(timezone.utc))),
            patch("delete_workflow_runs.cli.write_data_dict") as mock_write,
        ):
            result = runner.invoke(
                main,
                [
                    "--repo-url",
                    "https://github.com/tagdots/delete-workflow-runs",
                    "--min-runs",
                    "1",
                    "--dry-run",
                    "true",
                ],
            )
            assert result.exit_code == 0
            assert "❌ no" in result.output
            mock_write.assert_called_once()

    def test_cli_main_empty_workflow_runs(self):
        """Test CLI when repository has no workflow runs.

        Verifies that the CLI handles the case where get_all_workflow_runs()
        returns an empty DataFrame, skipping the deletion logic entirely.
        """
        runner = CliRunner()
        empty_df = pd.DataFrame()
        with (
            patch("delete_workflow_runs.cli.get_auth"),
            patch("delete_workflow_runs.cli.get_repo", return_value=Mock()),
            patch("delete_workflow_runs.cli.get_all_workflow_runs", return_value=empty_df),
            patch("delete_workflow_runs.cli.get_core_api_rate_limit", return_value=(1000, datetime.now(timezone.utc))),
            patch("delete_workflow_runs.cli.write_data_dict") as mock_write,
        ):
            result = runner.invoke(
                main,
                [
                    "--repo-url",
                    "https://github.com/tagdots/delete-workflow-runs",
                    "--min-runs",
                    "1",
                    "--dry-run",
                    "true",
                ],
            )
            assert result.exit_code == 0
            mock_write.assert_called_once()

    def test_cli_main_with_orphan_runs(self):
        """Test CLI with orphan workflow runs present.

        Verifies that the CLI correctly identifies and processes orphan runs
        (runs from deleted workflows) when they exist in the repository.
        """
        runner = CliRunner()
        orphan_df = pd.DataFrame(
            {
                "name": ["old-workflow"],
                "run_id": [101],
                "workflow_id": [999],
                "created_at": [datetime(2023, 1, 1, tzinfo=timezone.utc)],
            }
        )
        with (
            patch("delete_workflow_runs.cli.get_auth"),
            patch("delete_workflow_runs.cli.get_repo", return_value=Mock()),
            patch("delete_workflow_runs.cli.get_all_workflow_runs", return_value=orphan_df),
            patch("delete_workflow_runs.cli.break_down_df_all_runs", return_value=(orphan_df, pd.DataFrame())),
            patch("delete_workflow_runs.cli.delete_orphan_workflow_runs", return_value=1),
            patch("delete_workflow_runs.cli.get_core_api_rate_limit", return_value=(1000, datetime.now(timezone.utc))),
            patch("delete_workflow_runs.cli.write_data_dict") as mock_write,
        ):
            result = runner.invoke(
                main,
                [
                    "--repo-url",
                    "https://github.com/tagdots/delete-workflow-runs",
                    "--min-runs",
                    "1",
                    "--dry-run",
                    "true",
                ],
            )
            assert result.exit_code == 0
            mock_write.assert_called_once()

    def test_cli_main_max_days_with_invalid_min_runs(self):
        """Test CLI with valid max_days but invalid min_runs.

        Verifies that the CLI correctly uses max_days as the deletion criterion
        when min_runs is invalid (covers branch 710->714, elif with max_days).
        """
        runner = CliRunner()
        active_df = pd.DataFrame(
            {
                "name": ["workflow-01"],
                "run_id": [1],
                "workflow_id": [101],
                "created_at": [datetime(2023, 1, 1, tzinfo=timezone.utc)],
            }
        )
        with (
            patch("delete_workflow_runs.cli.get_auth"),
            patch("delete_workflow_runs.cli.get_repo", return_value=Mock()),
            patch("delete_workflow_runs.cli.get_all_workflow_runs", return_value=active_df),
            patch("delete_workflow_runs.cli.break_down_df_all_runs", return_value=(pd.DataFrame(), active_df)),
            patch("delete_workflow_runs.cli.delete_orphan_workflow_runs", return_value=0),
            patch("delete_workflow_runs.cli.delete_active_workflow_runs_max_days", return_value=pd.Series([0])),
            patch("delete_workflow_runs.cli.get_core_api_rate_limit", return_value=(1000, datetime.now(timezone.utc))),
            patch("delete_workflow_runs.cli.write_data_dict") as mock_write,
        ):
            result = runner.invoke(
                main,
                [
                    "--repo-url",
                    "https://github.com/tagdots/delete-workflow-runs",
                    "--max-days",
                    "30",
                    "--dry-run",
                    "true",
                ],
            )
            assert result.exit_code == 0
            mock_write.assert_called_once()

    def test_cli_main_both_invalid_params(self):
        """Test CLI with both min_runs and max_days set to invalid values.

        Verifies that the CLI handles the case where both parameters are invalid
        (negative values) and gracefully completes without error (covers branch 710->714, elif skipped).
        """
        runner = CliRunner()
        active_df = pd.DataFrame(
            {
                "name": ["workflow-01"],
                "run_id": [1],
                "workflow_id": [101],
                "created_at": [datetime(2023, 1, 1, tzinfo=timezone.utc)],
            }
        )
        with (
            patch("delete_workflow_runs.cli.check_user_inputs", return_value=True),
            patch("delete_workflow_runs.cli.get_auth"),
            patch("delete_workflow_runs.cli.get_repo", return_value=Mock()),
            patch("delete_workflow_runs.cli.get_all_workflow_runs", return_value=active_df),
            patch("delete_workflow_runs.cli.break_down_df_all_runs", return_value=(pd.DataFrame(), active_df)),
            patch("delete_workflow_runs.cli.delete_orphan_workflow_runs", return_value=0),
            patch("delete_workflow_runs.cli.get_core_api_rate_limit", return_value=(1000, datetime.now(timezone.utc))),
            patch("delete_workflow_runs.cli.write_data_dict") as mock_write,
        ):
            result = runner.invoke(
                main,
                [
                    "--repo-url",
                    "https://github.com/tagdots/delete-workflow-runs",
                    "--min-runs",
                    "-1",
                    "--max-days",
                    "-1",
                    "--dry-run",
                    "true",
                ],
            )
            assert result.exit_code == 0
            mock_write.assert_called_once()


if __name__ == "__main__":
    pytest.main()
