# CHANGELOG

## 1.1.21 (2025-08-24)

### Fix

- polish documentation in README, cron-tasks, run, and action
- revise version with typo
- update hash and version in cron-tasks and README

## 1.1.18 (2025-08-23)

### Feat

- add action

## 1.1.14 (2025-08-20)

### Feat

- replace delete-branches-action to remove old branches and misc typo fixes

### Fix

- fix version not changing
- update README, test-run repo names, and run start header
- add fail-on-severity to dependency-review to detect vulnerabilities packages
- resolve mixed-returns

## 1.1.6 (2025-08-15)

### Fix

- fix marketplace url
- add tagged version to README and cron-tasks

## 1.1.3 (2025-08-14)

### Feat

- writing data to a dictionary and a file to allow integration with other tools

### Fix

- update corresponding test cases in the threading replacement
- use ThreadPoolExecutor in delete operations
- refactor api rate limit to use resources.core out of 2.7.0 pyGithub changes

## 1.0.0 (2025-08-09)

### Feat

- initial release

### Fix

- remove ossf badge placeholder because there is a problem to the ossf website
- update marketplace message-color
- add missing GH_TOKEN
- upgrade pygithub and fix breaking changes
- upgrade virtualenv
- fix cron tasks with desired tasks and update notifications
