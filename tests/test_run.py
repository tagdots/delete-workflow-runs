#!/usr/bin/env python

"""
Purpose: tests
"""

import os
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pandas as pd
import pytest
from click.testing import CliRunner
from github import GithubException

from delete_workflow_runs.run import (
    break_down_df_all_runs,
    check_user_inputs,
    delete_active_workflow_runs_max_days,
    delete_active_workflow_runs_min_runs,
    delete_orphan_workflow_runs,
    get_api_estimate,
    get_auth,
    get_owner_repo,
    main,
)


class TestGetAuth:
    def test_get_auth_success(self, monkeypatch):
        monkeypatch.setenv("GH_TOKEN", "valid_token")
        with patch("delete_workflow_runs.run.Github") as mock_github:
            mock_user = Mock()
            mock_user.login = "test_user"
            mock_gh = mock_github.return_value
            mock_gh.get_user.return_value = mock_user
            gh = get_auth()
            assert gh is not None
            mock_github.assert_called_once()

    def test_get_auth_missing_token(self, monkeypatch):
        if "GH_TOKEN" in os.environ:
            monkeypatch.delenv("GH_TOKEN")
        with pytest.raises(SystemExit) as excinfo:
            get_auth()
        assert excinfo.value.code == 1

    def test_get_auth_invalid_token(self, monkeypatch):
        if "GH_TOKEN" in os.environ:
            monkeypatch.setenv("GH_TOKEN", "")
        with pytest.raises(SystemExit) as excinfo:
            get_auth()
        assert excinfo.value.code == 1


class TestGetOwnerRepo:
    def test_https_url(self):
        repo_url = "https://github.com/owner/repo.git"
        assert get_owner_repo(repo_url) == "owner/repo"

    def test_ssh_url(self):
        repo_url = "git@github.com:owner/repo.git"
        assert get_owner_repo(repo_url) == "owner/repo"

    def test_no_git_suffix(self):
        repo_url = "https://github.com/owner/repo"
        assert get_owner_repo(repo_url) == "owner/repo"


class TestCheckUserInputs:
    def test_both_min_runs_and_max_days(self):
        repo = Mock()
        assert not check_user_inputs(repo, "https://github.com/owner/repo", 5, 5)

    def test_neither_min_nor_max(self):
        repo = Mock()
        assert not check_user_inputs(repo, "https://github.com/owner/repo", None, None)

    def test_min_runs_negative(self):
        repo = Mock()
        assert not check_user_inputs(repo, "https://github.com/owner/repo", -1, None)

    def test_max_days_negative(self):
        repo = Mock()
        assert not check_user_inputs(repo, "https://github.com/owner/repo", None, -1)

    def test_invalid_repo_url(self):
        repo = Mock()
        assert not check_user_inputs(repo, "invalid_url", 5, None)

    def test_valid_min_runs(self):
        repo = Mock()
        assert check_user_inputs(repo, "https://github.com/owner/repo", 5, None)

    def test_valid_max_days(self):
        repo = Mock()
        assert check_user_inputs(repo, "https://github.com/owner/repo", None, 5)


class TestGetApiEstimate:
    def test_api_estimate_calculation(self):
        orphan = 50
        active = 50
        total = orphan + active
        estimate = get_api_estimate(orphan, active)
        assert estimate == (total * 2) + (total//100 + 1) + 3


class TestBreakDownDfAllRuns:
    def test_break_down_with_orphans(self):
        df_all_runs = pd.DataFrame({
            "workflow_id": [101, 102, 201],
            "run_id": [1011, 1021, 2011],
            "created_at": [datetime(2023, 1, 1, tzinfo=timezone.utc)] * 3,
            "name": ["wf1", "wf2", "wf3"]
        })

        mock_workflow1 = Mock(id=101)
        mock_workflow2 = Mock(id=102)
        mock_repo = Mock()
        mock_repo.get_workflows.return_value = [mock_workflow1, mock_workflow2]
        df_orphan_runs, df_active_runs, list_orphan_ids = break_down_df_all_runs(mock_repo, df_all_runs)
        assert len(df_orphan_runs) == 1
        assert len(df_active_runs) == 2
        assert list_orphan_ids == [201]


class TestDeleteOrphanWorkflowRuns:
    """
    dry-run: delete orphan run ids
    """
    def test_delete_orphan_runs_dry_run(self):
        df_orphan = pd.DataFrame({"run_id": [101010, 101020]})
        mock_repo = Mock()
        mock_owner_repo = "owner/repo"
        count = delete_orphan_workflow_runs(mock_repo, mock_owner_repo, dry_run=True, df_orphan_runs=df_orphan)
        assert count == 2

    def test_delete_orphan_runs(self):
        df_orphan = pd.DataFrame({"run_id": [101, 102, 103]})
        mock_repo = Mock()
        mock_owner_repo = "owner/repo"
        count = delete_orphan_workflow_runs(mock_repo, mock_owner_repo, dry_run=False, df_orphan_runs=df_orphan)
        assert count == 3


class TestDeleteActiveWorkflowRunsMinRuns:
    """
    dry-run: delete 4 of 5 run ids from active workflows (on min-runs)
    """
    def test_delete_active_runs_min_runs_dry_run(self):
        df_active = pd.DataFrame({
            "name": ["workflow-01", "workflow-01", "workflow-01", "workflow-01", "workflow-01"],
            "run_id": [90001, 90002, 90003, 90004, 90005],
            "workflow_id": [101] * 5,
            "created_at": [datetime(2023, 1, 1, tzinfo=timezone.utc)] * 5
        })
        mock_repo = Mock()
        mock_owner_repo = "owner/repo"
        count = delete_active_workflow_runs_min_runs(
            mock_repo, mock_owner_repo, dry_run=True, min_runs=1, df=df_active
        )
        assert count == 4

    """
    dry-run: there is no active workflow to delete (on min-runs)
    """
    def test_delete_active_runs_min_runs_dry_run_no_delete(self):
        df_active = pd.DataFrame({
            "name": ["workflow-01", "workflow-01", "workflow-01", "workflow-01"],
            "run_id": [60001, 60002, 60003, 60004],
            "workflow_id": [1] * 4,
            "created_at": [datetime(2023, 1, 1, tzinfo=timezone.utc)] * 4
        })
        mock_repo = Mock()
        mock_owner_repo = "owner/repo"
        count = delete_active_workflow_runs_min_runs(
            mock_repo, mock_owner_repo, dry_run=True, min_runs=20, df=df_active
        )
        assert count == 0

    """
    delete 2 of 5 run ids (on min-runs)
    """
    def test_delete_active_runs_min_runs(self):
        df_active = pd.DataFrame({
            "name": ["workflow-01", "workflow-01", "workflow-01", "workflow-01", "workflow-01"],
            "run_id": [40001, 40002, 4003, 40004, 40005],
            "workflow_id": [1] * 5,
            "created_at": [datetime(2023, 1, 1, tzinfo=timezone.utc)] * 5
        })
        mock_repo = Mock()
        mock_owner_repo = "owner/repo"
        count = delete_active_workflow_runs_min_runs(
            mock_repo, mock_owner_repo, dry_run=False, min_runs=2, df=df_active
        )
        assert count == 3


class TestDeleteActiveWorkflowRunsMaxDays:
    """
    dry-run: delete 4 of 4 run ids from active workflows (on max-days)
    """
    def test_delete_active_runs_max_days_dry_run(self):
        df_active = pd.DataFrame({
            "name": ["workflow-01", "workflow-01", "workflow-01", "workflow-01"],
            "run_id": [30001, 30002, 30003, 30004],
            "workflow_id": [101] * 4,
            "created_at": [datetime(2023, 1, 1, tzinfo=timezone.utc)] * 4
        })
        mock_repo = Mock()
        mock_owner_repo = "owner/repo"
        count = delete_active_workflow_runs_max_days(
            mock_repo, mock_owner_repo, dry_run=True, max_days=30, df=df_active
        )
        assert count == 4

    """
    dry-run: delete ZERO run ids (on max-days)
    """
    def test_delete_active_runs_max_days_dry_run_no_delete(self):
        df_active = pd.DataFrame({
            "name": ["workflow-01", "workflow-01", "workflow-01", "workflow-01"],
            "run_id": [70001, 70002, 70003, 70004],
            "workflow_id": [101] * 4,
            "created_at": [datetime(2025, 1, 1, tzinfo=timezone.utc)] * 4
        })
        mock_repo = Mock()
        mock_owner_repo = "owner/repo"
        count = delete_active_workflow_runs_max_days(
            mock_repo, mock_owner_repo, dry_run=True, max_days=2000, df=df_active
        )
        assert count == 0

    """
    delete 4 run ids from active workflows (on max-days)
    """
    def test_delete_active_runs_max_days(self):
        df_active = pd.DataFrame({
            "name": ["workflow-1", "workflow-1", "workflow-1", "workflow-1"],
            "run_id": [50101, 50102, 50103, 50104],
            "workflow_id": [1] * 4,
            "created_at": [datetime(2023, 1, 1, tzinfo=timezone.utc)] * 4
        })
        mock_repo = Mock()
        mock_owner_repo = "owner/repo"
        count = delete_active_workflow_runs_max_days(
            mock_repo, mock_owner_repo, dry_run=False, max_days=30, df=df_active
        )
        assert count == 4


class TestMain:
    def test_cli_main_401(self, monkeypatch):
        runner = CliRunner()
        monkeypatch.setenv("GH_TOKEN", "invalid_token")
        with patch("delete_workflow_runs.run.get_auth") as mock_auth:
            mock_gh = Mock()
            mock_auth.return_value = mock_gh
            mock_gh.get_repo.side_effect = GithubException(401, "Authentication error")
            result = runner.invoke(
                main,
                [
                    "--repo-url", "https://github.com/owner/repo",
                    "--max-days", "30"
                ]
            )
            print(f'\nMain result: {result}')
            print(result.stdout)
            print(result.stderr)
            assert result.exit_code == 1

    def test_cli_main_403(self, monkeypatch):
        runner = CliRunner()
        monkeypatch.setenv("GH_TOKEN", "invalid_token")
        with patch("delete_workflow_runs.run.get_auth") as mock_auth:
            mock_gh = Mock()
            mock_auth.return_value = mock_gh
            mock_gh.get_repo.side_effect = GithubException(403, "Permission error")
            result = runner.invoke(
                main,
                [
                    "--repo-url", "https://github.com/owner/repo",
                    "--max-days", "30"
                ]
            )
            print(f'\nMain result: {result}')
            print(result.stdout)
            print(result.stderr)
            assert result.exit_code == 1

    def test_cli_main_404(self):
        runner = CliRunner()
        with patch("delete_workflow_runs.run.get_auth") as mock_auth:
            mock_gh = Mock()
            mock_auth.return_value = mock_gh
            mock_gh.get_repo.side_effect = GithubException(404, "Not found")
            result = runner.invoke(
                main,
                [
                    "--repo-url", "https://github.com/invalid/repo",
                    "--max-days", "30",
                    "--dry-run", "true"
                ]
            )
            print(f'\nMain result: {result}')
            print(result.stdout)
            print(result.stderr)
            assert result.exit_code == 1

    def test_cli_main_input_false(self):
        """
        Test main

        Expect Result: get false check_user_inputs
        """
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--repo-url", "https://github.com/tagdots/delete-workflow-runs",
                "--max-days", "NA",
                "--dry-run", "false"
            ]
        )
        print(f'\nMain result: {result}')
        print(result.stdout)
        print(result.stderr)
        assert result.exit_code == 2

    def test_cli_main_min_runs_dry_run(self):
        """
        Test main

        Expect Result: dry-run to keep only 100 workflow runs for each workflow
        """
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--repo-url", "https://github.com/tagdots/delete-workflow-runs",
                "--min-runs", 100,
                "--dry-run", "true"
            ]
        )
        print(f'\nMain result: {result}')
        print(result.stdout)
        print(result.stderr)
        assert result.exit_code == 0
        assert "dry-run: True" in result.output

    def test_cli_main_max_days_dry_run(self):
        """
        Test main

        Expect Result: dry-run to keep workflows in the last 5 days
        """
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--repo-url", "https://github.com/tagdots/delete-workflow-runs",
                "--max-days", 5,
                "--dry-run", "true"
            ]
        )
        print(f'\nMain result: {result}')
        print(result.stdout)
        print(result.stderr)
        assert result.exit_code == 0
        assert "dry-run: True" in result.output


if __name__ == "__main__":
    pytest.main()
