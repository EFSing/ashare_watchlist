# RUNTIME STATE — GitHub Actions daily production

GITHUB_ACTIONS_DAILY_RUNTIME_V1

- this branch is operational state only
- never merge into master
- cloud workflow is the normal single writer
- local devices are read-only consumers unless explicit recovery
- no secrets
- no raw market evidence
- no generation input packages

The source authority is `origin/master`. This branch contains only the
allowlisted durable operational state restored and written by the cloud
workflow. Provider responses, K-lines, quotes, sectors, generation inputs,
and temporary validation data remain on the ephemeral runner and are never
committed here.
