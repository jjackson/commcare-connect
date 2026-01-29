---
name: deploy-labs
description: Deploy the labs environment to AWS via GitHub Actions. Use when the user wants to deploy, release, or push changes to the labs environment.
---

# Deploy Labs Environment

## Repository & Workflow

- **Fork repo**: `jjackson/commcare-connect`
- **Branch**: `labs-main`
- **Workflow**: `Deploy to AWS Labs`

## Deploy Command

```powershell
gh workflow run "Deploy to AWS Labs" -R jjackson/commcare-connect --ref labs-main -f run_migrations=false
```

With migrations:

```powershell
gh workflow run "Deploy to AWS Labs" -R jjackson/commcare-connect --ref labs-main -f run_migrations=true
```

## Monitor Progress

```powershell
gh run list -R jjackson/commcare-connect --workflow="Deploy to AWS Labs" --limit 1
gh run watch -R jjackson/commcare-connect <run_id>
```

## Pre-Deploy Checklist

1. Ensure changes are committed and pushed to `labs-main`
2. Push to fork if needed: `git push fork labs-main`
