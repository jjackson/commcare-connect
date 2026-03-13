---
name: deploy-labs
description: Deploy the labs environment to AWS via GitHub Actions. Use when the user wants to deploy, release, or push changes to the labs environment.
---

# Deploy Labs Environment

## Repository & Workflow

- **Repo**: `jjackson/connect-labs`
- **Branch**: `main`
- **Workflow**: `Deploy to AWS Labs`

## Deploy Command

```powershell
gh workflow run "Deploy to AWS Labs" -R jjackson/connect-labs --ref main -f run_migrations=false
```

With migrations:

```powershell
gh workflow run "Deploy to AWS Labs" -R jjackson/connect-labs --ref main -f run_migrations=true
```

## Monitor Progress

```powershell
gh run list -R jjackson/connect-labs --workflow="Deploy to AWS Labs" --limit 1
gh run watch -R jjackson/connect-labs <run_id>
```

## Pre-Deploy Checklist

1. Ensure changes are committed and pushed to `main`
2. Push to origin: `git push origin main`
