#!/usr/bin/env python

"""
Purpose: Delete GitHub Action Workflow Runs
"""

import os
import sys
import threading
import time
from datetime import timedelta
from pathlib import Path

import click
import pandas as pd
from github import (
    Auth,
    Github,
    GithubException,
    Repository,
)
from rich.console import Console
from rich.progress import Progress

from delete_workflow_runs import __version__


def get_auth():
    """
    Creates an instance of Github class to interact with GitHub API
    """
    try:
        gh_token = os.environ['GH_TOKEN']
        gh = Github(auth=Auth.Token(gh_token), per_page=100)
        return gh

    except KeyError:
        print("❌ Error: Environment variable (GH_TOKEN) not found.")
    except AssertionError:
        print("❌ Error: Environment variable (GH_TOKEN) is invalid")

    sys.exit(1)


def get_owner_repo(repo_url):
    """
    Get owner/repo for pyGitHub to interact with GitHub API

    Parameter(s):
    repo_url: repository url (e.g. https://github.com/{user/org}/repo.git)

    Return: owner/repo
    """
    owner_repo = '/'.join(repo_url.rsplit('/', 2)[-2:]).\
        replace('.git', '').replace('git@github.com:', '').replace('https://github.com/', '')
    return owner_repo


def check_user_inputs(repo, repo_url, min_runs, max_days):
    """
    Check user inputs

    Parameter(s):
    repo    : github repository object
    repo_url: github repository url
    min_runs: minimum number of runs to keep in a workflow
            : e.g. "min_runs = 5" means that all runs except the latest 5 in a workflow will be deleted
    max_days: maximum number of days to keep the run in a workflow
            : e.g. "max_days = 5" means that all runs oldr than 5 days in a workflow will be deleted

    Return: boolean
    """
    if min_runs is not None and max_days is not None:
        print("❌ Error: only enter one of min-runs or max-days")
        return False

    if min_runs is None and max_days is None:
        print("❌ Error: enter at lease one of min-runs or max-days")
        return False

    if min_runs is not None and (not isinstance(min_runs, int) or min_runs < 0):
        print("❌ Error: min-runs must be an integer (0 or more)")
        return False

    if max_days is not None and (not isinstance(max_days, int) or max_days < 0):
        print("❌ Error: max-days must be an integer (0 or more)")
        return False

    if ('github.com' not in repo_url and not isinstance(repo, Repository.Repository)):
        print("❌ Error: repo-url is not a valid github repository url")
        return False

    return True


def get_core_api_rate_limit(gh):
    """
    Get Core API Rate Limit (rate limit endpoint itself does not consume regular API quota)

    Parameter(s):
    gh: github class object from get_auth()

    Return: core api limit
    """
    rate_limit = gh.get_rate_limit()
    core_limit = rate_limit.rate
    return core_limit


def get_all_workflow_runs(repo):
    """
    Get all workflow runs

    Parameter(s):
    repo: github repository object

    Return: all workflow runs
    """
    print('💪 Gathering All Workflow Runs...')

    wf_runs = repo.get_workflow_runs()
    total_count = wf_runs.totalCount
    # per_page = 100 # total_pages = (total_count + per_page - 1) // per_page
    # print(f"Found {total_count} workflow runs across {total_pages} pages (100 runs/ page).")

    all_runs = []
    threads = []
    with Progress() as progress:
        overall_task = progress.add_task("[green]Processing data...\n", total=total_count)

        lock = threading.Lock()
        for runs in wf_runs:
            thread = threading.Thread(target=append_runs_to_list, args=(
                all_runs, runs.workflow_id, runs.id, runs.created_at, Path(runs.path).stem, lock))
            threads.append(thread)
            thread.start()
            progress.update(overall_task, advance=1)

        for thread in threads:
            thread.join()

    df_all_runs = pd.DataFrame(all_runs)
    return df_all_runs


def append_runs_to_list(all_runs, workflow_id, run_id, created_at, name, lock):
    """
    Append workflow runs to all_runs list

    Parameter(s):
    all_runs   : a list that contains all workflow runs
    created_at : timestamp of workflow run created at
    name       : workflow run name from workflow path
    run_id     : run id from workflow
    workflow_id: workflow id from all_runs

    Return: pandas dataframe that contains all workflow runs
    """
    with lock:
        all_runs.append({
            "workflow_id": workflow_id,
            "run_id": run_id,
            "created_at": created_at,
            "name": name
        })


def break_down_df_all_runs(repo, df_all_runs):
    """
    break down all workflow runs

    Parameter(s):
    repo       : github repository object
    df_all_runs: pandas dataframe that contains all workflow runs

    Return: active and orphan dataframes, list of orphan workflow ids
    """
    set_unique_all_workflow_ids = set(df_all_runs['workflow_id'].unique().tolist())

    set_unique_active_workflow_ids = set()
    for workflow in repo.get_workflows():
        set_unique_active_workflow_ids.add(
            workflow.id,
        )

    set_orphan_workflow_ids = set_unique_all_workflow_ids - set_unique_active_workflow_ids
    list_orphan_ids = list(set_orphan_workflow_ids) if len(set_orphan_workflow_ids) > 0 else []

    df_orphan_runs = df_all_runs[df_all_runs['workflow_id'].isin(list_orphan_ids)]\
        if len(df_all_runs) > 0 else pd.DataFrame()
    df_active_runs = df_all_runs[df_all_runs['workflow_id'].isin(list(set_unique_active_workflow_ids))]\
        if len(df_all_runs) > 0 else pd.DataFrame()

    df_orphan_runs = df_orphan_runs.sort_values(by='workflow_id') if len(df_orphan_runs) > 0 else pd.DataFrame()
    df_active_runs = df_active_runs.sort_values(by='workflow_id') if len(df_active_runs) > 0 else pd.DataFrame()

    return df_orphan_runs, df_active_runs, list_orphan_ids


def delete_orphan_workflow_runs(repo, owner_repo, dry_run, df_orphan_runs):
    """
    Delete orphan workflow runs

    Parameter(s):
    repo          : github repository object
    owner_repo    : required entry for pyGitHub get_repo method
    dry_run       : dry run
    df_orphan_runs: pandas dataframe that contains orphan workflow runs

    Return: total number of orphan workflow runs to be deleted
    """
    console = Console()
    list_run_id = df_orphan_runs['run_id'].to_list()
    total_count = df_orphan_runs.shape[0]

    if dry_run:
        console.print(f"\n([red]MOCK TO DELETE[/red]): [black]{list_run_id}[/black]\n")
    else:
        threads = []
        with Progress() as progress:
            overall_task = progress.add_task("[green]Processing data...\n", total=total_count)

            for workflow_run_id in list_run_id:
                thread = threading.Thread(target=delete_workflow_runs, args=(total_count, repo, workflow_run_id))
                threads.append(thread)
                thread.start()
                progress.update(overall_task, advance=1)

            for thread in threads:
                thread.join()

    return len(list_run_id)


def delete_active_workflow_runs_min_runs(repo, owner_repo, dry_run, min_runs, df):
    """
    Delete active workflow runs using min-runs option

    Parameter(s):
    repo      : github repository object
    owner_repo: required entry for pyGitHub get_repo method
    dry_run   : dry run
    df        : active workflow runs in pandas dataframe
    min_runs  : minimum number of runs to keep in a workflow
              : e.g. "min_runs = 5" means that all runs except the latest 5 in a workflow will be deleted

    Return: total number of active workflow runs to be deleted using min-runs argument
    """
    console = Console()
    delete_active_workflow_runs_count = 0

    """
    Group workflow runs by 'workflow name'
    from: <class 'pandas.core.frame.DataFrame'> to: <class 'pandas.core.groupby.generic.DataFrameGroupBy'>
    """
    df_groupby_name = df.groupby('name')

    """
    Count items for each group and create <class 'pandas.core.series.Series'>
    """
    group_count_series = df_groupby_name.size()
    print('\n🐑 Active Workflow Runs (grouped by Workflow Name)')
    print(f'{group_count_series}\n')

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
            result_df = df[df['name'].isin([filtered_group_names_index[i]])]
            result_df = result_df.sort_values(by='run_id', ascending=True)

            """
            Get the row count for each group; Calculate the number of rows to remove; Get all the rows to remove
            """
            group_count_before_min_runs = group_count_series.get(filtered_group_names_index[i])
            group_count = group_count_before_min_runs - min_runs
            result_df_after_min_runs = result_df.head(group_count)

            """
            Accumulate the total number of group_count to return for API estimate purpose
            """
            delete_active_workflow_runs_count += group_count

            print(f'\n🗑️ Deleting {group_count} workflow runs from {filtered_group_names_index[i]}')
            # print(result_df_after_min_runs) if necessary for debug purpose

            if dry_run:
                console.print(f"([red]MOCK TO DELETE[/red]): "
                              f"[black]{result_df_after_min_runs['run_id'].to_list()}[/black]")
            else:
                threads = []
                with Progress() as progress:
                    overall_task = progress.add_task("[green]Processing data...\n", total=group_count)

                    for index, row in result_df_after_min_runs.iterrows():
                        thread = threading.Thread(target=delete_workflow_runs, args=(group_count, repo, row['run_id']))
                        threads.append(thread)
                        thread.start()
                        progress.update(overall_task, advance=1)

                    for thread in threads:
                        thread.join()

    else:
        console.print(f'[red]With min-runs ({min_runs}), there is no active workflow run to delete[/red]')
    print('\n')

    return delete_active_workflow_runs_count


def delete_active_workflow_runs_max_days(repo, owner_repo, dry_run, max_days, df):
    """
    Delete active workflow runs using max-days option

    Parameter(s):
    repo      : github repository object
    owner_repo: required entry for pyGitHub get_repo method
    dry_run   : dry run
    df        : active workflow runs in pandas dataframe
    max_days  : maximum number of days to keep the run in a workflow
              : e.g. "max_days = 5" means that all runs oldr than 5 days in a workflow will be deleted

    Return: total number of active workflow runs to be deleted using max-days argument
    """
    console = Console()
    delete_active_workflow_runs_count = 0

    """
    Get cutoff date with (<class 'datetime.datetime'>) and convert to pandas timestamp for filtering next
    """
    current_date = pd.Timestamp.now(tz='UTC')
    cutoff_date = current_date - timedelta(days=max_days)
    cutoff_date = pd.to_datetime(cutoff_date, utc=True)

    """
    Group workflow runs by 'workflow name'
    from: <class 'pandas.core.frame.DataFrame'> to: <class 'pandas.core.groupby.generic.DataFrameGroupBy'>
    Count items for each group and create <class 'pandas.core.series.Series'>
    """
    df_groupby_name = df.groupby('name')
    group_count_series = df_groupby_name.size()
    print('\n🐑 Active Workflow Runs (grouped by Workflow Name)')
    print(f'{group_count_series}\n')

    """
    Filter workflow runs by created_at < cutoff_date with <class 'pandas.core.frame.DataFrame'>
    """
    filtered_group_names = df[df['created_at'] < cutoff_date]
    # print(filtered_group_names) if necessary for debug purpose

    """
    Group workflow runs by 'workflow name' and replace df_groupby_names
    from: <class 'pandas.core.frame.DataFrame'> to: <class 'pandas.core.groupby.generic.DataFrameGroupBy'>
    """
    df_groupby_name = filtered_group_names.groupby('name')

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
            result_df = filtered_group_names[filtered_group_names['name'].isin([filtered_group_names_index[i]])]
            result_df = result_df.sort_values(by='run_id', ascending=True)

            """
            Get the row count for each group
            Accumulate the total number of rows to return for API estimate purpose
            """
            group_count = group_count_series.get(filtered_group_names_index[i])
            delete_active_workflow_runs_count += group_count

            print(f'\n🗑️ Deleting {group_count} workflow runs from {filtered_group_names_index[i]}')
            if dry_run:
                console.print(f"([red]MOCK TO DELETE[/red]): [black]{result_df['run_id'].to_list()}[/black]")
            else:
                threads = []
                with Progress() as progress:
                    overall_task = progress.add_task("[green]Processing data...\n", total=group_count)

                    for index, row in result_df.iterrows():
                        thread = threading.Thread(target=delete_workflow_runs, args=(group_count, repo, row['run_id']))
                        threads.append(thread)
                        thread.start()
                        progress.update(overall_task, advance=1)

                    for thread in threads:
                        thread.join()

    else:
        console.print(f'[red]With max-days ({max_days}), there is no active workflow run to delete[/red]')
    print('\n')

    return delete_active_workflow_runs_count


def delete_workflow_runs(count, repo, workflow_run_id):  # pragma: no cover
    """
    Delete workflow runs

    Parameter(s):
    count          : number of workflow runs for each workflow namw
    repo           : github repository object
    workflow_run_id: github action workflow run id

    NOTE: when the count >= 100, the time delay is to stay under the secondary rate limit
    """
    try:
        workflow_run = repo.get_workflow_run(workflow_run_id)
        workflow_run.delete()
        print(f'workflow run {workflow_run.html_url} deleted')
        time.sleep(5) if count >= 100 else ''

    except GithubException as e:
        print(f'❌ Failed to delete workflow run {workflow_run_id}: {e}')


def get_api_estimate(orphan_runs_count, delete_runs_count):
    """
    Use dry-run to get API Usage Estimate

    Parameter(s):
    orphan_runs_count: number of orphan workflow runs to delete
    delete_runs_count: number of active workflow runs to delete

    NOTE:
    1. this script consumes 3 API limit at the minimum
    2. "delete workflow run" requires 2 API calls to 1) retrieve the workflow run object 2) call the delete method
    3. every additional page (100 rows) on paginationlist adds an additional API call
    """
    estimate = (
        ((orphan_runs_count + delete_runs_count) * 2) +
        ((orphan_runs_count + delete_runs_count)//100 + 1) + 3
    )
    return estimate


@click.command()
@click.option("--dry-run", required=False, type=bool, default=True, help="(optional) default: true")
@click.option("--repo-url", required=True, type=str, help="e.g. https://github.com/{owner}/{repo}")
@click.option("--min-runs", required=False, type=int, help="(optional) min. no. of runs to keep in a workflow")
@click.option("--max-days", required=False, type=int, help="(optional) max. no. of days to keep the run in a workflow")
@click.version_option(version=__version__)
def main(dry_run, repo_url, min_runs, max_days):
    console = Console()
    console.print(f"\n🚀 Starting to Delete GitHub Action workflows (dry-run: [red]{dry_run}[/red], "
                  f"min-runs: [red]{min_runs}[/red], max-days: [red]{max_days}[/red])\n")

    try:
        gh = get_auth()

        """display initial core api rate limit info at the beginning"""
        core_limit = get_core_api_rate_limit(gh)
        core_limit_start = core_limit.used
        print('\n💥 Core API Rate Limit (start)')
        print(f'API rate limit          : {core_limit.limit}')
        print(f'API rate limit remaining: {core_limit.remaining}\n\n')

        """setup github repo object"""
        owner_repo = get_owner_repo(repo_url)
        repo = gh.get_repo(owner_repo)

        if check_user_inputs(repo, repo_url, min_runs, max_days):
            delete_orphan_workflow_runs_count = 0
            delete_active_workflow_runs_count = 0

            """
            get all workflow runs
            """
            df_all_runs = get_all_workflow_runs(repo)
            if (len(df_all_runs) > 0):
                df_orphan_runs, df_active_runs, list_orphan_ids = break_down_df_all_runs(repo, df_all_runs)
            else:
                list_orphan_ids = []
                df_active_runs = pd.DataFrame()
                df_orphan_runs = pd.DataFrame()
            print(f'Number of orphan workflow IDs : {len(list_orphan_ids)}')
            print(f'Number of workflow runs       : {len(df_active_runs.index) + len(df_orphan_runs.index)}')
            print(f'Number of orphan workflow runs: {len(df_orphan_runs.index)}')
            print(f'Number of active workflow runs: {len(df_active_runs.index)}\n')

            """
            delete orphan workflow runs
            """
            print('\n🔍 Orphan Workflow Runs')
            print(f'Number of oustanding orphan workflow run(s): {len(df_orphan_runs.index)}')
            if len(df_orphan_runs.index) > 0:
                delete_orphan_workflow_runs_count = delete_orphan_workflow_runs(repo, owner_repo, dry_run, df_orphan_runs)

            """
            delete active workflow runs
            """
            print('\n🔍 Active Workflow Runs')
            print(f'Number of oustanding active workflow run(s): {len(df_active_runs.index)}\n')
            delete_active_workflow_runs_count = 0
            if len(df_active_runs.index) > 0:
                if (isinstance(min_runs, int) and min_runs >= 0):
                    delete_active_workflow_runs_count =\
                        delete_active_workflow_runs_min_runs(repo, owner_repo, dry_run, min_runs, df_active_runs)
                elif (isinstance(max_days, int) and max_days >= 0):
                    delete_active_workflow_runs_count =\
                        delete_active_workflow_runs_max_days(repo, owner_repo, dry_run, max_days, df_active_runs)

            """
            display core api rate limit info and create a usage estimate
            """
            core_limit = get_core_api_rate_limit(gh)
            print('\n💥 Core API Rate Limit (end)')
            print(f'API rate limit used     : {int(core_limit.used) - int(core_limit_start)}')
            print(f'API rate limit remaining: {core_limit.remaining}')
            print(f'API rate limit Reset At : {core_limit.reset} (UTC)\n')

            if dry_run:
                estimate = get_api_estimate(delete_orphan_workflow_runs_count, delete_active_workflow_runs_count)

                console.print('\n[blue]************************** API Usage Estimate ******************************[/blue]')
                console.print(f"This delete can consume [red]{estimate}[/red] of your API limit.  ")
                if (core_limit.remaining * 0.90) > estimate:
                    print('\nEnough API limit to run this delete now? ✅ yes')
                else:
                    print('\nEnough API limit to run this delete now? ❌ no')
                    console.print("[red](segment this delete into multiple runs)[/red]")
                console.print('[blue]****************************************************************************[/blue]')

    except Exception as e:
        print(f'❌ Exception Error: {e}')
        sys.exit(1)


if __name__ == '__main__':  # pragma: no cover
    main()
