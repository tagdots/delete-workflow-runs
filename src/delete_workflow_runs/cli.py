"""
GitHub Action Workflow Run Cleaner

This CLI tool deletes GitHub Actions workflow runs from a repository
based on either a minimum number of recent runs to keep (min-runs)
or a maximum age in days (max-days). It also removes runs belonging
to orphaned (deleted) workflows.

Usage:
    delete-workflow-runs --repo-url <url> [--min-runs N] [--max-days N] [--dry-run]

Environment:
    GH_TOKEN - required GitHub personal access token with action write scope.
"""

import concurrent.futures
import json
import os
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Tuple

import click
import pandas as pd
from github import (
    Auth,
    BadCredentialsException,
    Github,
    GithubException,
    Repository,
    UnknownObjectException,
)
from rich.console import Console
from rich.progress import Progress

from delete_workflow_runs import __version__


def get_auth() -> Github:
    """
    Creates an instance of Github class to interact with GitHub API

    Returns
    -------
    Github
        Authenticated Github client instance with rate limit verification.

    Raises
    ------
    KeyError
        If GH_TOKEN environment variable is not set.
    PermissionError
        If the provided GH_TOKEN is invalid.
    """
    try:
        gh_token = os.environ["GH_TOKEN"]
        gh = Github(auth=Auth.Token(gh_token), per_page=100)
        gh.get_rate_limit()
        return gh

    except KeyError:
        raise KeyError("GitHub Token - not found")
    except BadCredentialsException:
        raise PermissionError("GitHub Token - bad credential")


def get_repo(gh, repo_url: str) -> Repository.Repository:
    """
    Get owner/repo and repo object from pyGitHub to interact with GitHub API

    Parameters
    ----------
    gh : Github
        Authenticated Github client from get_auth().
    repo_url : str
        Repository URL in either HTTPS or SSH format.
        Examples: ``https://github.com/{user/org}/repo.git`` or
        ``git@github.com:{user/org}/repo.git``

    Returns
    -------
    Repository.Repository
        pyGitHub Repository object.

    Raises
    ------
    ValueError
        If the URL does not contain a valid GitHub hostname or the
        repository cannot be found.
    """
    try:
        list_gh_substrings = ["https://github.com", "git@github.com:"]
        if not any(gh_substring in repo_url for gh_substring in list_gh_substrings):
            raise ValueError(f"repo-url ({repo_url}) is invalid")

        owner_repo = (
            "/".join(repo_url.rsplit("/", 2)[-2:])
            .replace(".git", "")
            .replace("git@github.com:", "")
            .replace("https://github.com/", "")
        )
        repo = gh.get_repo(owner_repo)

        return repo

    except UnknownObjectException as e:
        raise ValueError(f"{repo_url} repository not found ({e.status})")


def check_user_inputs(min_runs: int | None, max_days: int | None) -> bool:
    """
    Validate user-provided min-runs and max-days inputs.

    The function enforces that exactly one of min-runs or max-days is provided,
    and that any provided value is a non-negative integer.

    Parameters
    ----------
    min_runs : int or None
        Minimum number of recent runs to keep in a workflow.
        For example, ``min_runs=5`` keeps only the latest 5 runs per workflow.
    max_days : int or None
        Maximum age (in days) of workflow runs to keep.
        For example, ``max_days=5`` deletes runs older than 5 days.

    Returns
    -------
    bool
        ``True`` if inputs are valid, ``False`` otherwise.
    """
    if min_runs is not None and max_days is not None:
        print("❌ Error: only enter one of min-runs or max-days")
        return False

    if min_runs is None and max_days is None:
        print("❌ Error: enter at least one of min-runs or max-days")
        return False

    if min_runs is not None and (not isinstance(min_runs, int) or min_runs < 0):
        print("❌ Error: min-runs must be an integer (0 or more)")
        return False

    if max_days is not None and (not isinstance(max_days, int) or max_days < 0):
        print("❌ Error: max-days must be an integer (0 or more)")
        return False

    return True


def get_core_api_rate_limit(gh: Github) -> Tuple[int, datetime]:
    """
    Get Core API Rate Limit information.

    The rate limit endpoint itself does not consume regular API quota.

    Parameters
    ----------
    gh : Github
        Authenticated Github client from get_auth().

    Returns
    -------
    Tuple[int, datetime]
        A tuple of ``(remaining_requests, reset_time)`` where
        ``remaining_requests`` is the number of API calls left and
        ``reset_time`` is the UTC datetime when the rate limit resets.
    """
    RateLimitOverview = gh.get_rate_limit()
    core = RateLimitOverview.resources.core
    core_reset = core.reset
    core_remaining = core.remaining

    print("\n💥 Core API Rate Limit Info")
    print(f"API rate limit remaining: {core_remaining}")
    print(f"API rate limit reset at : {core_reset} (UTC)\n")

    return (core_remaining, core_reset)


def get_all_workflow_runs(repo: Repository.Repository) -> pd.DataFrame:
    """
    Fetch all workflow runs from a GitHub repository using parallel threads.

    Parameters
    ----------
    repo : Repository.Repository
        pyGitHub Repository object.

    Returns
    -------
    pd.DataFrame
        DataFrame with columns ``workflow_id``, ``run_id``, ``created_at``,
        and ``name`` for each workflow run found.
    """
    print("💪 Gathering All Workflow Runs...")

    wf_runs = repo.get_workflow_runs()
    total_count = wf_runs.totalCount
    print(f"Found {total_count} workflow runs.")

    all_runs = []
    threads = []
    with Progress() as progress:
        overall_task = progress.add_task("[green]Processing data...\n", total=total_count)

        lock = threading.Lock()
        for runs in wf_runs:
            thread = threading.Thread(
                target=append_runs_to_list,
                args=(all_runs, runs.workflow_id, runs.id, runs.created_at, Path(runs.path).stem, lock),
            )
            threads.append(thread)
            thread.start()
            progress.update(overall_task, advance=1)

        for thread in threads:
            thread.join()

    df_all_runs = pd.DataFrame(all_runs)
    return df_all_runs


def append_runs_to_list(
    all_runs: list, workflow_id: int, run_id: int, created_at: datetime, name: str, lock: threading.Lock
):
    """
    Thread-safe helper to append a single workflow run dict to a shared list.

    Parameters
    ----------
    all_runs : list
        Shared list that accumulates all workflow run records.
    workflow_id : int
        Workflow identifier from the GitHub API.
    run_id : int
        Unique run identifier from the workflow.
    created_at : datetime
        Timestamp of when the workflow run was created.
    name : str
        Workflow run name derived from the workflow file path.
    lock : threading.Lock
        Lock for thread-safe access to ``all_runs``.

    Returns
    -------
    None
    """
    with lock:
        all_runs.append({"workflow_id": workflow_id, "run_id": run_id, "created_at": created_at, "name": name})


def break_down_df_all_runs(repo: Repository.Repository, df_all_runs: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Separate workflow runs into orphan runs (deleted workflows) and active runs.

    Parameters
    ----------
    repo : Repository.Repository
        GitHub repository object.
    df_all_runs : pd.DataFrame
        DataFrame containing all workflow runs.

    Returns
    -------
    Tuple[pd.DataFrame, pd.DataFrame]
        ``(df_orphan_runs, df_active_runs)`` where:
        - ``df_orphan_runs``: Runs belonging to non-existent workflows
        - ``df_active_runs``: Runs belonging to existing workflows
    """
    set_unique_all_workflow_ids = set(df_all_runs["workflow_id"].unique().tolist())

    set_unique_active_workflow_ids = set()
    for workflow in repo.get_workflows():
        set_unique_active_workflow_ids.add(
            workflow.id,
        )

    set_orphan_workflow_ids = set_unique_all_workflow_ids - set_unique_active_workflow_ids
    list_orphan_ids = list(set_orphan_workflow_ids) if len(set_orphan_workflow_ids) > 0 else []

    df_orphan_runs = (
        df_all_runs[df_all_runs["workflow_id"].isin(list_orphan_ids)] if len(df_all_runs) > 0 else pd.DataFrame()
    )
    df_active_runs = (
        df_all_runs[df_all_runs["workflow_id"].isin(list(set_unique_active_workflow_ids))]
        if len(df_all_runs) > 0
        else pd.DataFrame()
    )

    df_orphan_runs = df_orphan_runs.sort_values(by="workflow_id") if len(df_orphan_runs) > 0 else pd.DataFrame()
    df_active_runs = df_active_runs.sort_values(by="workflow_id") if len(df_active_runs) > 0 else pd.DataFrame()

    return (df_orphan_runs, df_active_runs)


def delete_orphan_workflow_runs(repo: Repository.Repository, dry_run: bool, df_orphan_runs: pd.DataFrame) -> int:
    """
    Delete orphan workflow runs (runs belonging to deleted workflows).

    Parameters
    ----------
    repo : Repository.Repository
        GitHub repository object.
    dry_run : bool
        If True, only count runs without deleting.
    df_orphan_runs : pd.DataFrame
        DataFrame containing orphan workflow runs.

    Returns
    -------
    int
        Number of orphan workflow runs deleted (or would be deleted in dry-run mode).
    """
    console = Console()
    list_run_id = df_orphan_runs["run_id"].to_list()
    total_count = df_orphan_runs.shape[0]

    if dry_run:
        console.print(f"\n([red]MOCK TO DELETE[/red]): [black]{list_run_id}[/black]\n")
    else:
        with Progress() as progress:
            overall_task = progress.add_task("[green]Processing data...\n", total=total_count)

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                for workflow_run_id in list_run_id:
                    futures = [executor.submit(delete_workflow_runs, total_count, repo, workflow_run_id)]
                    for _ in concurrent.futures.as_completed(futures):
                        progress.update(overall_task, advance=1)

    return len(list_run_id)


def delete_active_workflow_runs_min_runs(repo: Repository.Repository, dry_run: bool, min_runs: int, df: pd.DataFrame) -> int:
    """
    Delete active workflow runs exceeding the minimum run threshold.

    Groups runs by workflow name, then deletes runs from each group
    that exceed the specified minimum number of runs to keep.

    Parameters
    ----------
    repo : Repository.Repository
        GitHub repository object.
    dry_run : bool
        If True, only count runs without deleting.
    min_runs : int
        Minimum number of recent runs to keep per workflow.
        For example, ``min_runs=5`` keeps only the latest 5 runs per workflow.
    df : pd.DataFrame
        DataFrame containing active workflow runs.

    Returns
    -------
    int
        Total number of active workflow runs deleted (or would be deleted in dry-run mode).
    """
    console = Console()
    delete_active_workflow_runs_count = 0

    """
    Group workflow runs by 'workflow name'
    from: <class 'pandas.core.frame.DataFrame'> to: <class 'pandas.core.groupby.generic.DataFrameGroupBy'>
    """
    df_groupby_name = df.groupby("name")

    """
    Count items for each group and create <class 'pandas.core.series.Series'>
    """
    group_count_series = df_groupby_name.size()
    print("\n🐑 Active Workflow Runs (grouped by Workflow Name)")
    print(f"{group_count_series.to_string()}\n")

    """
    Filter groups (count > min_runs) into <class 'pandas.core.indexes.base.Index'>
    """
    filtered_group_names_index = group_count_series[group_count_series > min_runs].index
    if filtered_group_names_index.size > 0:
        for i in range((len(filtered_group_names_index))):
            """
            Select rows from filtered group name into <class 'pandas.core.frame.DataFrame'>
            Sort rows by run_id instead of created_at which can have duplicate rows
            """
            result_df = df[df["name"].isin([filtered_group_names_index[i]])]
            result_df = result_df.sort_values(by="run_id", ascending=True)

            """
            Get the row count for each group; Calculate the number of rows to remove; Get all the rows to remove
            note: group_count_series.get() may result in int | None >> a tmp var in transit >> ensure group_count is int
            """
            group_count_before_min_runs_tmp = group_count_series.get(filtered_group_names_index[i])
            group_count_before_min_runs = group_count_before_min_runs_tmp if group_count_before_min_runs_tmp else 0
            group_count = group_count_before_min_runs - min_runs
            result_df_after_min_runs = result_df.head(group_count)

            """
            Accumulate the total number of group_count to return for API estimate purpose
            """
            delete_active_workflow_runs_count += group_count

            print(f"\n🗑️ Deleting {group_count} workflow runs from {filtered_group_names_index[i]}")
            # print(result_df_after_min_runs) if necessary for debug purpose

            if dry_run:
                console.print(
                    f"([red]MOCK TO DELETE[/red]): " f"[black]{result_df_after_min_runs['run_id'].to_list()}[/black]"
                )
            else:
                with Progress() as progress:
                    overall_task = progress.add_task("[green]Processing data...\n", total=group_count)

                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                        for index, row in result_df_after_min_runs.iterrows():
                            futures = [executor.submit(delete_workflow_runs, group_count, repo, row["run_id"])]
                            for _ in concurrent.futures.as_completed(futures):
                                progress.update(overall_task, advance=1)

    else:
        console.print(f"[red]With min-runs ({min_runs}) for each workflow, there is no active workflow run to delete.[/red]")
    print("\n")

    return delete_active_workflow_runs_count


def delete_active_workflow_runs_max_days(repo: Repository.Repository, dry_run: bool, max_days: int, df: pd.DataFrame) -> int:
    """
    Delete active workflow runs older than the specified number of days.

    Groups runs by workflow name, then deletes runs from each group
    that are older than the specified maximum number of days.

    Parameters
    ----------
    repo : Repository.Repository
        GitHub repository object.
    dry_run : bool
        If True, only count runs without deleting.
    max_days : int
        Maximum age in days; runs older than this will be deleted.
        For example, ``max_days=5`` deletes runs older than 5 days.
    df : pd.DataFrame
        DataFrame containing active workflow runs.

    Returns
    -------
    int
        Total number of active workflow runs deleted (or would be deleted in dry-run mode).
    """
    console = Console()
    delete_active_workflow_runs_count = 0

    """
    Get cutoff date with (<class 'datetime.datetime'>) and convert to pandas timestamp for filtering next
    """
    current_date = pd.Timestamp.now(tz="UTC")
    cutoff_date = current_date - timedelta(days=max_days)

    """
    Group workflow runs by 'workflow name'
    from: <class 'pandas.core.frame.DataFrame'> to: <class 'pandas.core.groupby.generic.DataFrameGroupBy'>
    Count items for each group and create <class 'pandas.core.series.Series'>
    """
    df_groupby_name = df.groupby("name")
    group_count_series = df_groupby_name.size()
    print("\n🐑 Active Workflow Runs (grouped by Workflow Name)")
    print(f"{group_count_series.to_string()}\n")

    """
    Filter workflow runs by created_at < cutoff_date with <class 'pandas.core.frame.DataFrame'>
    """
    filtered_group_names = df[df["created_at"] < cutoff_date]
    # print(filtered_group_names) if necessary for debug purpose

    """
    Group workflow runs by 'workflow name' and replace df_groupby_names
    from: <class 'pandas.core.frame.DataFrame'> to: <class 'pandas.core.groupby.generic.DataFrameGroupBy'>
    """
    df_groupby_name = filtered_group_names.groupby("name")

    """
    Count items for each group and create <class 'pandas.core.series.Series'>
    """
    group_count_series = df_groupby_name.size()

    """
    convert from <class 'pandas.core.series.Series'> to <class 'pandas.core.indexes.base.Index'>
    e.g. Index(['ci', 'dependabot-updates'], dtype='object', name='name')
    """
    filtered_group_names_index = group_count_series.index
    if filtered_group_names_index.size > 0:
        for i in range((len(filtered_group_names_index))):
            """
            Select rows from filtered group name into <class 'pandas.core.frame.DataFrame'>
            Sort rows by run_id because reusable workflows may duplicate rows in timestamp
            """
            result_df = filtered_group_names[filtered_group_names["name"].isin([filtered_group_names_index[i]])]
            result_df = result_df.sort_values(by="run_id", ascending=True)

            """
            Get the row count for each group
            Accumulate the total number of rows to return for API estimate purpose
            note: group_count_series.get() may result in int | None >> a tmp var in transit >> ensure group_count is int
            """
            group_count_tmp = group_count_series.get(filtered_group_names_index[i])
            group_count = group_count_tmp if group_count_tmp else 0
            delete_active_workflow_runs_count += group_count

            print(f"\n🗑️ Deleting {group_count} workflow runs from {filtered_group_names_index[i]}")
            if dry_run:
                console.print(f"([red]MOCK TO DELETE[/red]): [black]{result_df['run_id'].to_list()}[/black]")
            else:
                with Progress() as progress:
                    overall_task = progress.add_task("[green]Processing data...\n", total=group_count)

                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                        for index, row in result_df.iterrows():
                            futures = [executor.submit(delete_workflow_runs, group_count, repo, row["run_id"])]
                            for _ in concurrent.futures.as_completed(futures):
                                progress.update(overall_task, advance=1)

    else:
        console.print(f"[red]With max-days ({max_days}) for each workflow, there is no active workflow run to delete.[/red]")
    print("\n")

    return delete_active_workflow_runs_count


def delete_workflow_runs(count: int, repo: Repository.Repository, workflow_run_id: int) -> int:
    """
    Delete a single workflow run from the repository.

    Parameters
    ----------
    count : int
        Total number of workflow runs for the current workflow name (used for progress tracking).
    repo : Repository.Repository
        GitHub repository object.
    workflow_run_id : int
        GitHub Actions workflow run ID to delete.

    Returns
    -------
    int
        Always returns 1 to indicate one run was processed.

    Raises
    ------
    GithubException
        If the run cannot be deleted (e.g., already deleted or permissions issue).
    """
    try:
        workflow_run = repo.get_workflow_run(workflow_run_id)
        workflow_run.delete()
        print(f"workflow run {workflow_run.html_url} deleted")
        time.sleep(0.5)
        return workflow_run_id

    except GithubException as e:  # pragma: no cover
        print(f"❌ Failed to delete workflow run {workflow_run_id}: {e}")
        return 0


def get_api_estimate(orphan_runs_count: int, delete_runs_count: int) -> int:
    """
    Estimate the number of API calls needed to delete workflow runs.

    Parameters
    ----------
    orphan_runs_count : int
        Number of orphan workflow runs to delete.
    delete_runs_count : int
        Number of active workflow runs to delete.

    Returns
    -------
    int
        Estimated total API calls needed for the delete operation.

    Notes
    -----
    - This script consumes 3 API calls at minimum.
    - Every page (100 items) on the pagination list consumes 1 API call.
    - Deleting a workflow run requires 2 API calls:
      1) retrieve the workflow run object
      2) call the delete method
    """
    estimate = ((orphan_runs_count + delete_runs_count) * 2) + ((orphan_runs_count + delete_runs_count) // 100 + 1) + 3
    return estimate


def write_data_dict(
    dry_run: bool,
    repo_url: str,
    min_runs: int,
    max_days: int,
    core_remaining: int,
    core_reset: datetime,
    core_usage_estimate: int,
    delete_active_workflow_runs_count: int,
    delete_orphan_workflow_runs_count: int,
):
    """
    Write data_dict to a file

    Parameter(s):
    dry_run                          : dry run
    repo_url                         : repository url
    max_days                         : maximum number of days to keep the run in a workflow
    min_runs                         : minimum number of runs to keep in a workflow
    core_remaining                   : core api rate limit remaining
    core_reset                       : core api rate limit reset at
    core_usage_estimate              : core api rate limit consumption for delete operation
    delete_active_workflow_runs_count: number of active workflow runs to delete
    delete_orphan_workflow_runs_count: number of orphan workflow runs to delete
    """
    data_dict = {}
    data_dict.update(
        {
            "dry-run": dry_run,
            "repo-url": repo_url,
            "min-runs": min_runs,
            "max-days": max_days,
            "core-limit-remaining": core_remaining,
            "core-limit-reset": str(core_reset),
            "core-limit-usage-estimate": core_usage_estimate,
            "delete-active-workflow-runs-count": delete_active_workflow_runs_count,
            "delete-orphan-workflow-runs-count": delete_orphan_workflow_runs_count,
        }
    )
    with open("data_dict.log", "w") as f:
        json.dump(data_dict, f, indent=2)


@click.command()
@click.option("--dry-run", required=False, type=bool, default=True, show_default=True)
@click.option("--repo-url", required=True, type=str, help="e.g. https://github.com/{owner}/{repo}")
@click.option("--min-runs", required=False, type=int, help="minimum number of runs to keep in a workflow")
@click.option("--max-days", required=False, type=int, help="maximum number of days to keep the run in a workflow")
@click.version_option(version=__version__)
def main(dry_run, repo_url, min_runs, max_days):
    """
    Main entry point for the workflow run deletion CLI.

    Parses command-line arguments, validates inputs, authenticates with GitHub,
    fetches workflow runs, identifies orphan and active runs, and deletes
    runs based on the specified criteria (min-runs or max-days).

    Supports dry-run mode to preview deletions without actually removing runs.

    Displays API rate limit information and usage estimates.
    """
    console = Console()
    print(
        f"\n🚀 Starting to Delete GitHub Action workflows (dry-run: {dry_run}, "
        + f"min-runs: {min_runs}, max-days: {max_days})\n"
    )

    # Initialize data
    core_remaining = 0
    core_reset = datetime.now() + timedelta(hours=1)
    core_usage_estimate = 0
    delete_orphan_workflow_runs_count = 0
    delete_active_workflow_runs_count = 0

    try:
        gh = get_auth()
        repo = get_repo(gh, repo_url)

        if check_user_inputs(min_runs, max_days):
            # Get all workflow runs
            df_all_runs = get_all_workflow_runs(repo)
            if len(df_all_runs) > 0:
                df_orphan_runs, df_active_runs = break_down_df_all_runs(repo, df_all_runs)
            else:
                df_active_runs = pd.DataFrame()
                df_orphan_runs = pd.DataFrame()
            print(f"\nTotal Number of workflow runs : {len(df_active_runs.index) + len(df_orphan_runs.index)}")
            print(f"Number of orphan workflow runs: {len(df_orphan_runs.index)}")
            print(f"Number of active workflow runs: {len(df_active_runs.index)}\n")

            # Delete orphan workflow runs
            print("\n🔍 Orphan Workflow Runs")
            print(f"Number of outstanding orphan workflow run(s): {len(df_orphan_runs.index)}")
            if len(df_orphan_runs.index) > 0:
                delete_orphan_workflow_runs_count = delete_orphan_workflow_runs(repo, dry_run, df_orphan_runs)

            # Delete active workflow runs
            print("\n🔍 Active Workflow Runs")
            print(f"Number of outstanding active workflow run(s): {len(df_active_runs.index)}\n")
            if len(df_active_runs.index) > 0:
                if isinstance(min_runs, int) and min_runs >= 0:
                    delete_active_workflow_runs_count = delete_active_workflow_runs_min_runs(
                        repo, dry_run, min_runs, df_active_runs
                    )
                elif isinstance(max_days, int) and max_days >= 0:
                    delete_active_workflow_runs_count = delete_active_workflow_runs_max_days(
                        repo, dry_run, max_days, df_active_runs
                    )
                delete_active_workflow_runs_count = (
                    delete_active_workflow_runs_count.item()
                    if not isinstance(delete_active_workflow_runs_count, int)
                    else delete_active_workflow_runs_count
                )

            # Display core API rate limit info and create a usage estimate
            core_remaining, core_reset = get_core_api_rate_limit(gh)
            if dry_run:
                core_usage_estimate = get_api_estimate(delete_orphan_workflow_runs_count, delete_active_workflow_runs_count)

                console.print("\n[blue]************************** API Usage Estimate ******************************[/blue]")
                console.print(f"This delete command can consume [red]{core_usage_estimate}[/red] units of your API limit.")
                if (core_remaining * 0.90) > core_usage_estimate:
                    console.print("\nEnough API limit to run this delete now? ✅ yes")
                else:
                    console.print("\nEnough API limit to run this delete now? ❌ no")
                    console.print("[red](segment this delete into multiple runs)[/red]")
                console.print("[blue]****************************************************************************[/blue]")

        # Write data_dict to a file for data feed to integrate with other tools
        write_data_dict(
            dry_run,
            repo_url,
            min_runs,
            max_days,
            core_remaining,
            core_reset,
            core_usage_estimate,
            delete_active_workflow_runs_count,
            delete_orphan_workflow_runs_count,
        )

    except Exception as e:
        print(f"Error: {e}\n")
        sys.exit(1)


if __name__ == "__main__":  # pragma: no cover
    main()
