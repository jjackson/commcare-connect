# AWS Fargate Labs - Quick Start Guide

## Deploy Updates

You have **two options** for deploying:

### Option 1: Local Script (Fastest to start)

For most code changes (no database migrations):

```bash
# From project root
./deploy/aws/deploy.sh
```

That's it! The script will:

1. ✅ Authenticate with AWS ECR
2. ✅ Build your Docker image
3. ✅ Push to container registry
4. ✅ Deploy web and worker services
5. ✅ Wait for deployment to complete
6. ✅ Show you the new public IP

**Time**: ~3-5 minutes

### Option 2: GitHub Actions (One-click from browser)

Deploy from anywhere without local setup:

1. Go to: `https://github.com/YOUR-USERNAME/commcare-connect/actions`
2. Click **"Deploy to AWS Labs"** → **"Run workflow"**
3. Select branch and migration option
4. Click **"Run workflow"**

**Setup required**: See [GITHUB-ACTIONS-SETUP.md](./GITHUB-ACTIONS-SETUP.md) (~20 min one-time setup)

**Time**: ~4-6 minutes after setup

---

### Deployment with Migrations

**Local script:**

```bash
./deploy/aws/deploy.sh --with-migrations
```

**GitHub Actions:** Check the "Run database migrations" box when running the workflow.

**Time**: ~4-6 minutes

---

## First Time Setup

### For Local Script

#### 1. Make script executable (one-time only)

```bash
chmod +x deploy/aws/deploy.sh
```

#### 2. Verify AWS CLI is configured

```bash
aws sts get-caller-identity --profile labs
```

Should show your AWS account info. If not, run:

```bash
aws sso login --profile labs
```

### For GitHub Actions

Follow the setup guide: [GITHUB-ACTIONS-SETUP.md](./GITHUB-ACTIONS-SETUP.md)

**Time:** ~20 minutes (one-time setup)

---

## Access Your Application

After deployment completes, you'll see:

```
Application URL: http://X.X.X.X:8000/
Login URL:      http://X.X.X.X:8000/accounts/login/
```

**Admin Credentials:**

- Email: `admin@dimagi.com`
- Password: `admin123`

---

## Common Tasks

### Check if services are running

```bash
aws ecs describe-services \
  --cluster labs-jj-cluster \
  --services labs-jj-web labs-jj-worker \
  --profile labs \
  --query 'services[*].[serviceName,runningCount]' \
  --output table
```

### Get current public IP

```bash
TASK_ARN=$(aws ecs list-tasks --cluster labs-jj-cluster --service-name labs-jj-web --profile labs --query 'taskArns[0]' --output text)
ENI_ID=$(aws ecs describe-tasks --cluster labs-jj-cluster --tasks $TASK_ARN --profile labs --query 'tasks[0].attachments[0].details[?name==`networkInterfaceId`].value' --output text)
aws ec2 describe-network-interfaces --network-interface-ids $ENI_ID --profile labs --query 'NetworkInterfaces[0].Association.PublicIp' --output text
```

Or just run the deploy script - it shows the IP at the end!

### View logs

```bash
# Web service logs (follow mode)
aws logs tail /ecs/labs-jj-web --follow --profile labs

# Worker service logs
aws logs tail /ecs/labs-jj-worker --follow --profile labs
```

### Run Django management command

```bash
aws ecs run-task \
  --cluster labs-jj-cluster \
  --task-definition labs-jj-web:5 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-06646effb09be2f42],securityGroups=[sg-0666a5ed512c97d9d],assignPublicIp=ENABLED}" \
  --overrides '{"containerOverrides":[{"name":"web","command":["python","/app/manage.py","YOUR_COMMAND_HERE"]}]}' \
  --profile labs
```

---

## Troubleshooting

### Deployment script fails at authentication

```bash
# Re-authenticate with AWS
aws sso login --profile labs
```

### Can't connect to application after deployment

1. Make sure you're using the new IP address (shown after deployment)
2. Check services are running: `aws ecs describe-services ...` (see above)
3. Check logs: `aws logs tail /ecs/labs-jj-web --profile labs`

### Migrations fail

Check the migration logs:

```bash
aws logs tail /ecs/labs-jj-web --profile labs | grep -A 50 "Django migrate"
```

### Need to rollback?

Re-run the deploy script with a previous version of your code:

```bash
git checkout <previous-commit>
./deploy/aws/deploy.sh
git checkout main  # or your current branch
```

---

## Cost Saving Tips

When not actively using the labs environment, you can stop services to save money:

### Stop services (saves ~$22/month)

```bash
aws ecs update-service --cluster labs-jj-cluster --service labs-jj-web --desired-count 0 --profile labs
aws ecs update-service --cluster labs-jj-cluster --service labs-jj-worker --desired-count 0 --profile labs
```

### Restart services

```bash
aws ecs update-service --cluster labs-jj-cluster --service labs-jj-web --desired-count 1 --profile labs
aws ecs update-service --cluster labs-jj-cluster --service labs-jj-worker --desired-count 1 --profile labs
```

Database and Redis will continue running (always-on services). To stop those too, see [IMPLEMENTATION.md](./IMPLEMENTATION.md) for details.

---

## More Information

- **Complete documentation**: See [IMPLEMENTATION.md](./IMPLEMENTATION.md)
- **Infrastructure details**: See [README.md](./README.md)
- **AWS Console**:
  - [ECS Cluster](https://us-east-1.console.aws.amazon.com/ecs/v2/clusters/labs-jj-cluster)
  - [CloudWatch Logs](https://us-east-1.console.aws.amazon.com/cloudwatch/home?region=us-east-1#logsV2:log-groups)

---

## Summary

**99% of the time, just run:**

```bash
./deploy/aws/deploy.sh
```

**If you have migrations:**

```bash
./deploy/aws/deploy.sh --with-migrations
```

That's it! 🚀
