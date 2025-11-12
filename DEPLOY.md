# Deployment Guide - Labs Environment

## Overview

The labs environment (labs.connect.dimagi.com) is deployed via GitHub Actions workflows. Deployments are triggered manually using the GitHub CLI.

## Prerequisites

1. **GitHub CLI installed**

   ```bash
   # Windows (using winget)
   winget install GitHub.cli

   # Or download from https://cli.github.com/
   ```

2. **GitHub CLI authenticated**

   ```bash
   gh auth login
   # Follow prompts to authenticate
   ```

3. **Push access to your fork**
   - Fork: `https://github.com/jjackson/commcare-connect`
   - Branch: `labs-main`

## Deployment Process

### Step 1: Ensure code is pushed to your fork

```bash
# Check current status
git status

# Stage and commit changes
git add <files>
git commit -m "Your commit message"

# Push to your fork
git push fork labs-main
```

### Step 2: Trigger GitHub Actions deployment

The deployment workflow is in `.github/workflows/deploy-labs.yml` and requires manual trigger.

```bash
# Trigger deployment WITHOUT migrations
gh workflow run deploy-labs.yml \
  --repo dimagi/commcare-connect \
  --ref labs-main \
  --field run_migrations=false

# Trigger deployment WITH migrations (if you added/changed models)
gh workflow run deploy-labs.yml \
  --repo dimagi/commcare-connect \
  --ref labs-main \
  --field run_migrations=true
```

**Note:** This assumes your changes are already in `dimagi/commcare-connect:labs-main`. If they're only in your fork, see Step 3.

### Step 3: If code is only in your fork

If your changes are in `jjackson/commcare-connect:labs-main` but not yet in `dimagi/commcare-connect:labs-main`, you need to:

**Option A: Create a Pull Request (Recommended)**

```bash
# Create PR from your fork to main repo
gh pr create \
  --repo dimagi/commcare-connect \
  --base labs-main \
  --head jjackson:labs-main \
  --title "Your PR title" \
  --body "Description of changes"

# After PR is merged, trigger deployment (see Step 2)
```

**Option B: Direct push (if you have write access)**

```bash
# This requires write access to dimagi/commcare-connect
git push origin labs-main
```

### Step 4: Monitor deployment

```bash
# Watch the workflow run
gh run watch --repo dimagi/commcare-connect

# Or view in browser
gh run list --repo dimagi/commcare-connect --workflow=deploy-labs.yml
gh run view <run-id> --repo dimagi/commcare-connect --web
```

## Quick Reference Commands

```bash
# Check workflow status
gh run list --repo dimagi/commcare-connect --workflow=deploy-labs.yml --limit 5

# View specific run logs
gh run view <run-id> --repo dimagi/commcare-connect --log

# Cancel a running deployment
gh run cancel <run-id> --repo dimagi/commcare-connect

# Rerun a failed deployment
gh run rerun <run-id> --repo dimagi/commcare-connect
```

## Deployment Checklist

Before deploying:

- [ ] Code is committed and pushed to fork
- [ ] All tests pass locally
- [ ] No linter errors
- [ ] Changes reviewed (if applicable)
- [ ] Database migrations needed? (Set run_migrations accordingly)

After deploying:

- [ ] Check deployment logs for errors
- [ ] Test the changes at https://labs.connect.dimagi.com
- [ ] Monitor CloudWatch logs if needed

## Troubleshooting

### "workflow not found" error

The workflow might not exist in the branch you're targeting. Ensure `deploy-labs.yml` exists in `dimagi/commcare-connect:labs-main`.

### "permissions denied" error

You need write access to trigger workflows in the main repo. Use the PR approach instead.

### Deployment fails

1. Check the GitHub Actions logs:
   ```bash
   gh run view <run-id> --repo dimagi/commcare-connect --log
   ```
2. Check CloudWatch logs for runtime errors
3. Common issues:
   - Docker build failures (check Dockerfile)
   - Migration failures (check model changes)
   - ECR login issues (check AWS credentials in GitHub secrets)

## Environment Details

- **AWS Region**: us-east-1
- **ECS Cluster**: labs-jj-cluster
- **Web Service**: labs-jj-web
- **Worker Service**: labs-jj-worker
- **ECR Repository**: labs-jj-commcare-connect
- **URL**: https://labs.connect.dimagi.com

## Emergency Rollback

If deployment causes issues:

```bash
# Find the last successful deployment
gh run list --repo dimagi/commcare-connect --workflow=deploy-labs.yml --status=success --limit 1

# Rerun that deployment
gh run rerun <previous-run-id> --repo dimagi/commcare-connect
```

## Related Files

- `.github/workflows/deploy-labs.yml` - Deployment workflow
- `tasks.py` - Local development tasks
- `deploy/` - Ansible/Kamal deployment configs (not used for labs)
