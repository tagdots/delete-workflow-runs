# CHANGELOG

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
