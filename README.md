# delete-workflow-runs

[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/11003/badge)](https://www.bestpractices.dev/projects/11003)
[![CI](https://github.com/tagdots/delete-workflow-runs/actions/workflows/ci.yaml/badge.svg)](https://github.com/tagdots/delete-workflow-runs/actions/workflows/ci.yaml)
[![marketplace](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/tagdots/delete-workflow-runs/refs/heads/badges/badges/marketplace.json)](https://github.com/marketplace/actions/delete-github-workflow-runs)
[![coverage](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/tagdots/delete-workflow-runs/refs/heads/badges/badges/coverage.json)](https://github.com/tagdots/delete-workflow-runs/actions/workflows/cron-tasks.yaml)

<br>

## ✅ What does delete-workflow-runs do?
**delete-workflow-runs** deletes workflow runs in GitHub repository.

<br>

<!--
## 😎 Why we create delete-workflow-runs?
**delete-workflow-runs** was created because some of the _most popular "delete workflow runs"_ actions on the GitHub marketplace:
- are not regularly updated (_supply chain risk_).
- do not show evidence of tests (_supply chain risk_).
- do not identify orphan workflow runs to delete (_eat up costs for no reason_).
- do not provide supportive information before a delete operation (_business risk you can't ignore_).
-->

## ⭐ Why switch to delete-workflow-runs?
- we reduce your supply chain risks with [openssf best practices](https://best.openssf.org) in our SDLC and operations.
- we identify orphan workflow runs that should be deleted when the parent workflow is deleted.
- we produce _API rate limit consumption estimate in dry-run_, so you can plan your delete task properly.
- we share evidence of code coverage results in action (click _Code Coverage » cron-tasks » badge-coverage_).
- we can run using [command line](https://github.com/tagdots/delete-workflow-runs?tab=readme-ov-file#-running-delete-workflow-runs-from-command-line) or GitHub Action [Delete GitHub Workflow Runs](https://github.com/marketplace/actions/delete-github-workflow-runs).

<br>

## 🏃 Running _delete-workflow-runs_ in GitHub action

Use the workflow examples below to create your own workflow inside `.github/workflows/`.

<br>

### Example 1 - Summary (MOCK Delete)
| Input | Workflow Spec | Result
|-------|-------------|----------|
| `scheduled run` | `- cron: '30 17 * * *'` | Run daily at 5:30 pm UTC
| `github token permissions` | `actions: read`<br>`contents: read` | MOCK delete requires read permission |
| `min-runs` | `10` | Keep the last 10 workflow runs for each workflow |
| `dry-run` | `true` | a. MOCK delete<br>b. Produce API rate limit consumption estimate<br>c. Get the JSON log file  |

### Example 1 - Workflow (MOCK Delete)
```yml
name: delete-github-workflow-runs

on:
  schedule:
    - cron: '30 17 * * *'

permissions:
  actions: read
  contents: read

jobs:
  delete-workflow-runs:
    runs-on: ubuntu-latest

    permissions:
      actions: read
      contents: read

    - name: Run delete-workflow-runs
      id: delete-workflow-runs
      uses: tagdots/delete-workflow-runs@4303b7da352de2004b0c5f118420cf9f1d63a370 # 1.2.33
      env:
        GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
      with:
        repo-url: ${{ github.server_url }}/${{ github.repository }}
        min-runs: 10
        dry-run: true

    - name: Get data
      id: get_data
      shell: bash
      run: |
        # get data from the last step
        cat data_dict.log | jq .
```

### Example 1 - Sample JSON Data File Output

Get the data output (data_dict.log) and extrat fields if necessary to:

- perform permanent delete after the dry-run if the usage estimate is below some threshold
- notify users if workflow-runs count is above an abnormal level
- ...etc.

![delete-01](https://raw.githubusercontent.com/tagdots/delete-workflow-runs/refs/heads/main/assets/delete-workflow-runs-01.png)

<br>

### Example 2 - Summary (Permanent delete)

| Input | Workflow Spec | Result
|-------|-------------|----------|
| `scheduled run` | `- cron: '30 17 * * *'` | Run daily at 5:30 pm UTC
| `github token permissions` | `actions: write`<br>`contents: read` | Delete requires write permission in `actions` |
| `max-days` | `10` | Keep runs in the last 10 days for each workflow |
| `dry-run` | `false` | a. Delete workflow runs<br>b. Get the JSON log file |

### Example 2 - Workflow (Permanent delete)
```yml
name: delete-github-workflow-runs

on:
  schedule:
    - cron: '30 17 * * *'

permissions:
  actions: read
  contents: read

jobs:
  delete-workflow-runs:
    runs-on: ubuntu-latest

    permissions:
      actions: write
      contents: read

    - id: delete-workflow-runs
      uses: tagdots/delete-workflow-runs@4303b7da352de2004b0c5f118420cf9f1d63a370 # 1.2.33
      env:
        GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
      with:
        repo-url: ${{ github.server_url }}/${{ github.repository }}
        max-days: 10
        dry-run: false

    - name: Get data
      id: get_data
      shell: bash
      run: |
        # get data from the last step
        cat data_dict.log | jq .
```

<br>

## 🖥 Running _delete-workflow-runs_ from command line

### Prerequisites
```
* Python (3.12+)
* GitHub fine-grained token (actions: write, contents: read)
```

<br>

### Setup _delete-workflow-runs_
```
~/work/test $ workon test
(test) ~/work/test $ export GH_TOKEN=github_pat_xxxxxxxxxxxxx
(test) ~/work/test $ pip install -U delete-workflow-runs
```

<br>

### Example 1 - Run for help
```
(test) ~/work/test $ delete-workflow-runs --help
Usage: delete-workflow-runs [OPTIONS]

Options:
  --dry-run BOOLEAN   (optional) default: true
  --repo-url TEXT     e.g. https://github.com/{owner}/{repo}  [required]
  --min-runs INTEGER  (optional) min. no. of runs to keep in a workflow
  --max-days INTEGER  (optional) max. no. of days to keep the run in a workflow
  --version           Show the version and exit.
  --help              Show this message and exit.
```

<br>

### Example 2 - Perform a MOCK delete to keep 10 workflow runs for each workflow

```
(test) ~/work/test $ delete-workflow-runs --min-runs 10 --dry-run true --repo-url https://github.com/tagdots/test

🚀 Starting Delete GitHub Action workflows (dry-run: True, min-runs: 10, max-days: None)

💪 Gathering All Workflow Runs...
Processing data... ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:00

Total Number of workflow runs : 129
Number of orphan workflow runs: 30
Number of active workflow runs: 99

🔍 Orphan Workflow Runs
Number of oustanding orphan workflow run(s): 30

(MOCK TO DELETE): [15058092121, 15034888458, 15078596910, 15034475367, 15090026832, 15090030896, 15084245242, 15084303419, 15239417433, 15239382675, 15239408367, 15239397843, 15239358005, 15235079202, 15233659220,
16556825410, 16510306546, 16430838958, 16306842822, 16332759286, 16405553071, 16393954546, 16358571373, 16382491807, 16545099147, 16533675262, 16484292026, 16458028383, 16547233105, 16434758197]

🔍 Active Workflow Runs
Number of oustanding active workflow run(s): 99

🐑 Active Workflow Runs (grouped by Workflow Name)
name
cd                    19
ci                    20
cron-tasks            19
dependabot-updates    21
sidecar-pr-target     20
dtype: int64

🗑️ Deleting 9 workflow runs from cd
(MOCK TO DELETE): [15806064859, 16104512541, 16250807024, 16434583247, 16434645985, 16434754825, 16434785233, 16434820611, 16546884995]

🗑️ Deleting 10 workflow runs from ci
(MOCK TO DELETE): [15950739193, 16094600811, 16094619137, 16244732902, 16395541601, 16434567109, 16434627400, 16434740215, 16546738070, 16547528347]

🗑️ Deleting 9 workflow runs from cron-tasks
(MOCK TO DELETE): [16434793676, 16434825852, 16434852708, 16434896839, 16434934116, 16434996622, 16435041248, 16453916385, 16520026786]

🗑️ Deleting 11 workflow runs from dependabot-updates
(MOCK TO DELETE): [15950716794, 16094417348, 16094600635, 16094600796, 16244713166, 16244779653, 16395351569, 16395525528, 16546581526, 16546719181, 16547922603]

🗑️ Deleting 10 workflow runs from sidecar-pr-target
(MOCK TO DELETE): [15514064562, 15658883423, 15950739190, 16244732841, 16395541582, 16434566916, 16434627267, 16434740066, 16546738013, 16547528240]

💥 Core API Rate Limit Info
API rate limit remaining: 4988
API rate limit Reset At : 2025-08-07 21:31:26+00:00 (UTC)

************************** API Usage Estimate ******************************
This delete can consume 162 units of your API limit.

Enough API limit to run this delete now? ✅ yes
****************************************************************************
```

<br>

### Example 3 - Delete workflow runs older than 10 days permanently

```
(test) ~/work/test $ delete-workflow-runs --max-days 10 --dry-run false --repo-url https://github.com/tagdots/test

🚀 Starting Delete GitHub Action workflows (dry-run: False, min-runs: None, max-days: 10)

💪 Gathering All Workflow Runs...
Processing data... ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:00

Total Number of workflow runs : 32
Number of orphan workflow runs: 0
Number of active workflow runs: 32

🔍 Orphan Workflow Runs
Number of oustanding orphan workflow run(s): 0

🔍 Active Workflow Runs
Number of oustanding active workflow run(s): 32

🐑 Active Workflow Runs (grouped by Workflow Name)
name
ci                     9
dependabot-updates     8
reusable-build-test    4
reusable-codeql        5
reusable-pre-commit    5
sidecar-pr-target      1
dtype: int64

🗑️ Deleting 1 workflow runs from ci
workflow run https://github.com/tagdots/test/actions/runs/16579872850 deleted
Processing data... ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:00

🗑️ Deleting 2 workflow runs from dependabot-updates
workflow run https://github.com/tagdots/test/actions/runs/16579973735 deleted
workflow run https://github.com/tagdots/test/actions/runs/16579973116 deleted
Processing data... ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:00

🗑️ Deleting 2 workflow runs from reusable-build-test
workflow run https://github.com/tagdots/test/actions/runs/16579881494 deleted
workflow run https://github.com/tagdots/test/actions/runs/16579883068 deleted
Processing data... ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:00

🗑️ Deleting 3 workflow runs from reusable-codeql
workflow run https://github.com/tagdots/test/actions/runs/16579884454 deleted
workflow run https://github.com/tagdots/test/actions/runs/16579886956 deleted
workflow run https://github.com/tagdots/test/actions/runs/16579885594 deleted
Processing data... ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:00

🗑️ Deleting 2 workflow runs from reusable-pre-commit
workflow run https://github.com/tagdots/test/actions/runs/16579877146 deleted
workflow run https://github.com/tagdots/test/actions/runs/16579878141 deleted
Processing data... ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:00

💥 Core API Rate Limit Info
API rate limit remaining: 4959
API rate limit Reset At : 2025-08-07 22:46:47+00:00 (UTC)
```

<br>

## 🔧 delete-workflow-runs command line options

| Input | Description | Default | Required | Notes |
|-------|-------------|----------|----------|----------|
| `repo-url` | Repository URL | `None` | Yes | e.g. https://github.com/{owner}/{repo} |
| `dry-run` | Dry-Run | `True` | No | - |
| `min-runs` | Min. no. of runs to <br>keep in a workflow | `None` | No | enter either min. runs or max. days |
| `max-days` | Max. no. of days to <br>keep run in a workflow | `None` | No | enter either min. runs or max. days |

<br>

## ⚠️ Summary of GitHub rate limit for standard repository
```
* 1,000 requests per hour per repository.
* No more than 100 concurrent requests are allowed.
* No more than 900 points per minute are allowed for REST API endpoints.
* No more than 90 seconds of CPU time per 60 seconds of real time is allowed.
* Make too many requests that consume excessive compute resources in a short period of time.
```

<br>

## ✍️ Notes
1. We don't present the starting and ending numbers of the API rate limit.  Based on our pioneer user feedbacks, other tasks could be running and consuming the API rate limit in parallel, which renders the numbers with mixed results.

1. We take a conservative approach and use only one worker thread, adding a 0.5-second delay after each delete to protect you from rate limit issues.  In the screenshot below, we used 16.5 minutes to delete 626 active workflow runs.  If not for the rate limit concern, we could have got it down to less than 5 minutes.

![delete-02](https://raw.githubusercontent.com/tagdots/delete-workflow-runs/refs/heads/main/assets/delete-workflow-runs-02.png)

<br>

## 😕  Troubleshooting

Open an [issue][issues]

<br>

## 🙏  Contributing

For pull requests to be accepted on this project, you should follow [PEP8][pep8] when creating/updating Python codes.

See [Contributing][contributing]

<br>

## 🙌 Appreciation
If you find this project helpful, please ⭐ star it.  **Thank you**.

<br>

## 📚 References

[GitHub API rate limit](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api?apiVersion=2022-11-28#primary-rate-limit-for-github_token-in-github-actions)

[How to fork a repo](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/working-with-forks/fork-a-repo)

<br>

[contributing]: https://github.com/tagdots/delete-workflow-runs/blob/main/CONTRIBUTING.md
[issues]: https://github.com/tagdots/delete-workflow-runs/issues
[pep8]: https://google.github.io/styleguide/pyguide.html
