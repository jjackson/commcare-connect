# GitHub Actions Setup for AWS Labs Deployment

This guide walks you through setting up GitHub Actions with **OIDC authentication** (no long-lived credentials!) to automatically deploy to your AWS Fargate labs environment.

**Time required:** ~20 minutes

---

## Prerequisites

- ✅ AWS Fargate environment already deployed (labs-jj-\* resources)
- ✅ AWS CLI configured with admin access (`labs` profile)
- ✅ GitHub repository: `jjackson/commcare-connect`

---

## Step 1: Create OIDC Identity Provider in AWS

This is a **one-time setup** that allows GitHub Actions to authenticate with AWS.

### 1.1 Check if Provider Already Exists

```bash
aws iam list-open-id-connect-providers --profile labs
```

If you see `token.actions.githubusercontent.com` in the output, **skip to Step 2**.

### 1.2 Create the OIDC Provider

```bash
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1 \
  --profile labs
```

**Output:** You'll get an ARN like:

```
arn:aws:iam::858923557655:oidc-provider/token.actions.githubusercontent.com
```

Save this ARN - you'll need it in the next step!

---

## Step 2: Create IAM Role for GitHub Actions

### 2.1 Create Trust Policy File

Create a file called `github-actions-trust-policy.json`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::858923557655:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
          "token.actions.githubusercontent.com:sub": "repo:jjackson/commcare-connect:ref:refs/heads/main"
        }
      }
    }
  ]
}
```

**Important:** Replace `jjackson` with your actual GitHub username if different.

**What this does:** Only allows GitHub Actions running from your `main` branch to assume this role.

### 2.2 Create the IAM Role

```bash
aws iam create-role \
  --role-name github-actions-labs-deploy \
  --assume-role-policy-document file://github-actions-trust-policy.json \
  --description "Role for GitHub Actions to deploy to labs environment" \
  --profile labs
```

**Output:** Save the Role ARN (looks like: `arn:aws:iam::858923557655:role/github-actions-labs-deploy`)

### 2.3 Create Permission Policy File

Create a file called `github-actions-permissions-policy.json`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ECRAccess",
      "Effect": "Allow",
      "Action": [
        "ecr:GetAuthorizationToken",
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage",
        "ecr:PutImage",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload"
      ],
      "Resource": "*"
    },
    {
      "Sid": "ECSAccess",
      "Effect": "Allow",
      "Action": [
        "ecs:UpdateService",
        "ecs:DescribeServices",
        "ecs:DescribeTaskDefinition",
        "ecs:DescribeTasks",
        "ecs:ListTasks",
        "ecs:RunTask"
      ],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "aws:RequestedRegion": "us-east-1"
        }
      }
    },
    {
      "Sid": "EC2NetworkAccess",
      "Effect": "Allow",
      "Action": ["ec2:DescribeNetworkInterfaces"],
      "Resource": "*"
    },
    {
      "Sid": "PassRoleToECS",
      "Effect": "Allow",
      "Action": "iam:PassRole",
      "Resource": [
        "arn:aws:iam::858923557655:role/labs-jj-ecs-task-execution-role",
        "arn:aws:iam::858923557655:role/labs-jj-ecs-task-role"
      ]
    }
  ]
}
```

### 2.4 Attach Permission Policy to Role

```bash
aws iam put-role-policy \
  --role-name github-actions-labs-deploy \
  --policy-name GitHubActionsLabsDeployPolicy \
  --policy-document file://github-actions-permissions-policy.json \
  --profile labs
```

### 2.5 Verify Role Creation

```bash
aws iam get-role \
  --role-name github-actions-labs-deploy \
  --profile labs \
  --query 'Role.Arn' \
  --output text
```

Copy this ARN - you'll add it to GitHub in the next step!

---

## Step 3: Add Secrets to GitHub Repository

### 3.1 Navigate to Repository Settings

1. Go to: `https://github.com/jjackson/commcare-connect/settings/secrets/actions`
2. Click **"New repository secret"**

### 3.2 Add AWS_ROLE_ARN Secret

- **Name:** `AWS_ROLE_ARN`
- **Value:** `arn:aws:iam::858923557655:role/github-actions-labs-deploy`
  (Use the ARN from Step 2.5)
- Click **"Add secret"**

### 3.3 Add AWS_REGION Secret

- **Name:** `AWS_REGION`
- **Value:** `us-east-1`
- Click **"Add secret"**

**That's it for secrets!** With OIDC, you don't need to store any AWS credentials.

---

## Step 4: Test the Workflow

### 4.1 Commit and Push the Workflow File

The workflow file has already been created at `.github/workflows/deploy-labs.yml`.

```bash
git add .github/workflows/deploy-labs.yml
git commit -m "Add GitHub Actions deployment workflow"
git push origin main
```

### 4.2 Trigger Manual Deployment

1. Go to: `https://github.com/jjackson/commcare-connect/actions`
2. Click on **"Deploy to AWS Labs"** in the left sidebar
3. Click the **"Run workflow"** dropdown button
4. Select branch: **main**
5. Check **"Run database migrations"** if needed
6. Click green **"Run workflow"** button

### 4.3 Watch the Deployment

- You'll see a workflow run start immediately
- Click on it to see live logs
- Each step shows progress with checkmarks
- Total time: ~3-5 minutes

### 4.4 Verify Success

At the end of the workflow, you'll see:

```
✅ Deployment Complete!
🌐 Application URL: http://X.X.X.X:8000/
```

Visit that URL to confirm it's working!

---

## Step 5: Clean Up Temporary Files

```bash
rm github-actions-trust-policy.json
rm github-actions-permissions-policy.json
```

---

## Usage Going Forward

### Deploy with One Click

1. Go to: `https://github.com/jjackson/commcare-connect/actions`
2. Select **"Deploy to AWS Labs"**
3. Click **"Run workflow"**
4. Choose whether to run migrations
5. Click **"Run workflow"**

### Enable Auto-Deploy (Optional)

To automatically deploy when you push to `main`:

Edit `.github/workflows/deploy-labs.yml` and uncomment these lines:

```yaml
# push:
#   branches:
#     - main
```

Change to:

```yaml
push:
  branches:
    - main
```

Now every push to `main` will automatically deploy!

---

## Adding More Repositories (Future)

To allow deployments from additional repos (e.g., `dimagi/commcare-connect`):

### Update the Trust Policy

```bash
aws iam get-role \
  --role-name github-actions-labs-deploy \
  --profile labs \
  --query 'Role.AssumeRolePolicyDocument' > current-trust-policy.json
```

Edit `current-trust-policy.json` and add the new repo to the condition:

```json
"Condition": {
  "StringEquals": {
    "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
    "token.actions.githubusercontent.com:sub": [
      "repo:jjackson/commcare-connect:ref:refs/heads/main",
      "repo:dimagi/commcare-connect:ref:refs/heads/labs"
    ]
  }
}
```

Update the role:

```bash
aws iam update-assume-role-policy \
  --role-name github-actions-labs-deploy \
  --policy-document file://current-trust-policy.json \
  --profile labs
```

Then add the same secrets (`AWS_ROLE_ARN` and `AWS_REGION`) to the new repository.

---

## Troubleshooting

### Error: "AssumeRoleWithWebIdentity failed"

**Cause:** Trust policy doesn't match your repository or branch.

**Fix:** Verify the trust policy:

```bash
aws iam get-role \
  --role-name github-actions-labs-deploy \
  --profile labs \
  --query 'Role.AssumeRolePolicyDocument'
```

Make sure it matches: `repo:YOUR-USERNAME/commcare-connect:ref:refs/heads/main`

### Error: "User: arn:aws:sts::858923557655:assumed-role/github-actions-labs-deploy is not authorized to perform: ecs:UpdateService"

**Cause:** Permission policy is missing or incorrect.

**Fix:** Re-run Step 2.4 to attach the permission policy.

### Workflow runs but doesn't deploy

**Check:**

1. Secrets are set correctly in GitHub
2. Role ARN is correct (no typos)
3. Region is `us-east-1`

View detailed logs in the Actions tab for the specific error.

### Migration task fails

**Check CloudWatch Logs:**

```bash
aws logs tail /ecs/labs-jj-web --follow --profile labs
```

Common issues:

- Database connection error (check security group)
- Migration conflict (run migrations manually first)
- Task definition outdated (pull latest image)

---

## Security Best Practices

✅ **What we've implemented:**

- No long-lived AWS credentials in GitHub
- Temporary credentials per workflow run (expire in 1 hour)
- Least-privilege permissions (only what's needed for deployment)
- Repository-specific trust relationship
- Branch-specific trust (only `main` can deploy)

✅ **Additional security (optional):**

- Require pull request reviews before merging to `main`
- Use GitHub Environments with required reviewers
- Add branch protection rules
- Enable "Require approval for deployments to protected environments"

---

## Monitoring and Notifications

### View Deployment History

1. Go to: `https://github.com/jjackson/commcare-connect/actions`
2. Filter by **"Deploy to AWS Labs"**
3. See all past deployments with status and timing

### Get Email Notifications

1. Go to: `https://github.com/settings/notifications`
2. Under "Actions", enable **"Send notifications for failed workflows only"**

Or set up Slack/Discord notifications (requires additional configuration).

---

## Cost Impact

**GitHub Actions minutes:**

- Deployment workflow: ~4-6 minutes per run
- GitHub Free: 2,000 minutes/month
- **Estimated usage:** ~20 deployments/month = 100 minutes
- **Cost:** $0 (well within free tier)

**AWS costs:** No additional costs - same infrastructure is used.

---

## Comparison: GitHub Actions vs Local Script

| Feature                | Local `deploy.sh`    | GitHub Actions               |
| ---------------------- | -------------------- | ---------------------------- |
| **Ease of use**        | Run one command      | Click one button             |
| **From anywhere**      | ❌ Need local clone  | ✅ Any device with browser   |
| **Audit trail**        | ❌ No logs           | ✅ Full history in GitHub    |
| **Team deployment**    | ❌ Need AWS access   | ✅ Anyone with repo access   |
| **Secrets management** | ❌ Local credentials | ✅ Stored securely in GitHub |
| **CI/CD integration**  | ❌ Manual only       | ✅ Can auto-deploy on merge  |
| **Setup time**         | 0 min (ready now)    | 20 min (one time)            |

**Recommendation:** Keep both!

- Use **local script** for quick iterations during development
- Use **GitHub Actions** for official deployments and team access

---

## Quick Reference Commands

```bash
# View workflow runs
gh run list --workflow=deploy-labs.yml

# Trigger deployment from CLI (requires GitHub CLI)
gh workflow run deploy-labs.yml --ref main -f run_migrations=false

# View logs of latest run
gh run view --log

# Get role ARN
aws iam get-role --role-name github-actions-labs-deploy --profile labs --query 'Role.Arn' --output text

# View CloudWatch logs
aws logs tail /ecs/labs-jj-web --follow --profile labs
```

---

## Next Steps

**You're all set!** Try running a deployment now:

1. Go to Actions tab: `https://github.com/jjackson/commcare-connect/actions`
2. Click **"Deploy to AWS Labs"** → **"Run workflow"**
3. Watch it deploy! 🚀

**Optional enhancements:**

- Add deployment status badge to README
- Set up Slack notifications
- Add smoke tests after deployment
- Configure deployment environments
- Add rollback workflow

---

**Questions or issues?** Check the troubleshooting section or review the workflow logs in GitHub Actions.

**Last updated:** November 7, 2025
