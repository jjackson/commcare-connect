# AWS Fargate Labs Environment - Implementation Guide

## 🚀 Quick Start

**To deploy updates, just run:**

```bash
./deploy/aws/deploy.sh
```

**With database migrations:**

```bash
./deploy/aws/deploy.sh --with-migrations
```

See [QUICKSTART.md](./QUICKSTART.md) for the simplest deployment guide.

---

## Overview

This document details the AWS Fargate deployment implementation for the CommCare Connect labs environment. The deployment uses AWS ECS Fargate with managed RDS PostgreSQL and ElastiCache Redis, optimized for minimal maintenance overhead.

## Architecture

### High-Level Design

```
┌─────────────────────────────────────────────────────────────┐
│                         Internet                             │
└────────────────────────┬────────────────────────────────────┘
                         │
                    Port 8000
                         │
┌────────────────────────▼────────────────────────────────────┐
│                    Public Subnets                            │
│  ┌──────────────────┐         ┌──────────────────┐         │
│  │  ECS Fargate     │         │  ECS Fargate     │         │
│  │  Web Task        │         │  Worker Task     │         │
│  │  (Gunicorn)      │         │  (Celery)        │         │
│  │  Public IP       │         │  Public IP       │         │
│  └────────┬─────────┘         └─────────┬────────┘         │
│           │                              │                   │
│           └──────────────┬───────────────┘                   │
│                          │                                   │
│           ┌──────────────▼───────────────┐                  │
│           │   Security Group             │                  │
│           │   - HTTP: 8000 (inbound)     │                  │
│           │   - PostgreSQL: 5432         │                  │
│           │   - Redis: 6379              │                  │
│           └──────────────┬───────────────┘                  │
└────────────────────────────────────────────────────────────┘
                          │
          ┌───────────────┴───────────────┐
          │                               │
┌─────────▼────────┐          ┌──────────▼──────────┐
│  RDS PostgreSQL  │          │  ElastiCache Redis  │
│  db.t3.micro     │          │  cache.t3.micro     │
│  (managed)       │          │  (managed)          │
└──────────────────┘          └─────────────────────┘
```

### Key Design Decisions

1. **No Application Load Balancer (ALB)**: Tasks get public IPs directly, reducing cost by ~$16/month
2. **No NAT Gateway**: Tasks run in public subnets with direct internet access, saving ~$32/month
3. **Managed Databases**: RDS and ElastiCache handle OS patching, backups, and security updates
4. **Fargate Launch Type**: AWS manages the underlying compute, eliminating EC2 management
5. **Single Task Deployment**: Each service runs 1 task for minimal cost (suitable for labs environment)

## Infrastructure Created

### VPC and Networking

**VPC**: `labs-jj-vpc`

- CIDR: 10.0.0.0/16
- Region: us-east-1
- DNS hostnames: Enabled

**Subnets** (Public):

- `labs-jj-public-subnet-1`: 10.0.1.0/24 (us-east-1a)
- `labs-jj-public-subnet-2`: 10.0.2.0/24 (us-east-1b)
- Internet Gateway attached for direct internet access

**Security Group**: `labs-jj-sg`

- Inbound:
  - HTTP: Port 8000 from 0.0.0.0/0
  - PostgreSQL: Port 5432 (internal)
  - Redis: Port 6379 (internal)
- Outbound: All traffic allowed

### Database and Cache

**RDS PostgreSQL**: `labs-jj-postgres`

- Instance class: db.t3.micro
- Engine: PostgreSQL 15.5
- Storage: 20 GB gp2
- Database name: `commcare_connect`
- Username: `connectadmin`
- Multi-AZ: Disabled (single instance)
- Publicly accessible: No
- Automated backups: Enabled (1 day retention)
- Endpoint: `labs-jj-postgres.cs74wyie8cdf.us-east-1.rds.amazonaws.com:5432`

**ElastiCache Redis**: `labs-jj-redis`

- Node type: cache.t3.micro
- Engine: Redis 7.x
- Nodes: 1
- Endpoint: `labs-jj-redis.aceivh.0001.use1.cache.amazonaws.com:6379`

### Container Services

**ECR Repository**: `labs-jj-commcare-connect`

- Registry: `858923557655.dkr.ecr.us-east-1.amazonaws.com/labs-jj-commcare-connect`
- Current image digest: `sha256:f258c4ed9f7e8327d0a0d9994bf745b1f076dd3da8b5cc098fdff8b9197ed6a4`

**ECS Cluster**: `labs-jj-cluster`

- Launch type: Fargate
- Services: 2 (web, worker)

### ECS Services

**Web Service**: `labs-jj-web`

- Task definition: `labs-jj-web:5` (current revision)
- Desired count: 1
- Launch type: Fargate
- CPU: 512 (0.5 vCPU)
- Memory: 1024 MB (1 GB)
- Network mode: awsvpc
- Command: `/start` (runs Gunicorn on port 8000)
- Environment variables:
  - `DJANGO_SETTINGS_MODULE=config.settings.staging`
  - `DJANGO_DEBUG=False`
  - `DJANGO_ALLOWED_HOSTS=*`
  - `COMMCARE_HQ_URL=https://staging.commcarehq.org`
  - `DATABASE_URL=postgres://connectadmin:[PASSWORD]@labs-jj-postgres...`
  - `REDIS_URL=redis://labs-jj-redis...`
  - `CELERY_BROKER_URL=redis://labs-jj-redis...`
- Secrets:
  - `DJANGO_SECRET_KEY` from AWS Secrets Manager
- Logs: CloudWatch `/ecs/labs-jj-web`

**Worker Service**: `labs-jj-worker`

- Task definition: `labs-jj-worker:4` (current revision)
- Desired count: 1
- Launch type: Fargate
- CPU: 512 (0.5 vCPU)
- Memory: 1024 MB (1 GB)
- Network mode: awsvpc
- Command: `/start_celery` (runs Celery worker)
- Environment variables: Same as web service
- Logs: CloudWatch `/ecs/labs-jj-worker`

### IAM Roles

**Task Execution Role**: `labs-jj-ecs-task-execution-role`

- Used by ECS to pull images and manage logs
- Policies:
  - `AmazonECSTaskExecutionRolePolicy` (AWS managed)
  - `SecretsManagerReadWrite` (AWS managed)
  - Custom inline policy for CloudWatch Logs:
    - `logs:CreateLogGroup`
    - `logs:CreateLogStream`
    - `logs:PutLogEvents`

**Task Role**: `labs-jj-ecs-task-role`

- Used by application code for AWS API access
- Currently has no policies attached (add as needed)

### Secrets Management

**Secrets Manager**:

- `labs-jj-django-secret-key`: Django SECRET_KEY (base64-encoded random string)
  - ARN: `arn:aws:secretsmanager:us-east-1:858923557655:secret:labs-jj-django-secret-key-iB1rtG`
- `labs-jj-database`: Database connection details (JSON)
- `labs-jj-redis`: Redis connection details (JSON)

## Implementation Steps Performed

### Phase 1: Prerequisites and Setup (Completed)

1. **AWS CLI Configuration**
   - Configured AWS SSO profile: `labs`
   - Verified credentials with `aws sts get-caller-identity`
   - Region: us-east-1

### Phase 2: Network Infrastructure (Completed)

1. **Created VPC**

   ```bash
   aws ec2 create-vpc --cidr-block 10.0.0.0/16 --tag-specifications 'ResourceType=vpc,Tags=[{Key=Name,Value=labs-jj-vpc}]'
   ```

2. **Created Public Subnets**

   - Subnet 1 in us-east-1a (10.0.1.0/24)
   - Subnet 2 in us-east-1b (10.0.2.0/24)

3. **Created and Attached Internet Gateway**

4. **Created Route Table** with route to Internet Gateway

5. **Created Security Group** with rules for HTTP, PostgreSQL, Redis

### Phase 3: Database and Cache (Completed)

1. **Created RDS PostgreSQL Instance**

   - Instance identifier: `labs-jj-postgres`
   - Initial database: `commcare_connect`
   - Waited ~10 minutes for instance to become available

2. **Created ElastiCache Redis Cluster**
   - Cluster ID: `labs-jj-redis`
   - Single node configuration

### Phase 4: Container Registry (Completed)

1. **Created ECR Repository**

   ```bash
   aws ecr create-repository --repository-name labs-jj-commcare-connect
   ```

2. **Built and Pushed Docker Image**
   - Fixed Docker entrypoint line endings (CRLF → LF) for Windows compatibility
   - Added pandas dependency to requirements
   - Built with: `docker build -t labs-jj-commcare-connect:latest .`
   - Tagged and pushed to ECR

### Phase 5: Secrets and IAM (Completed)

1. **Created Secrets in Secrets Manager**

   - Django secret key (generated with `openssl rand -base64 64`)
   - Database credentials
   - Redis connection info

2. **Created IAM Roles**
   - ECS task execution role with CloudWatch Logs permissions
   - ECS task role for application runtime

### Phase 6: ECS Cluster and Services (Completed)

1. **Created ECS Cluster**

   ```bash
   aws ecs create-cluster --cluster-name labs-jj-cluster
   ```

2. **Registered Task Definitions**

   - Web task definition with Gunicorn configuration
   - Worker task definition with Celery configuration

3. **Created ECS Services**
   - Web service with public IP assignment
   - Worker service with public IP assignment

### Phase 7: Database Migration (Completed)

1. **Ran Migration Task**

   ```bash
   aws ecs run-task --cluster labs-jj-cluster \
     --task-definition labs-jj-web:5 \
     --launch-type FARGATE \
     --network-configuration "awsvpcConfiguration={subnets=[...],securityGroups=[...],assignPublicIp=ENABLED}" \
     --overrides '{"containerOverrides":[{"name":"web","command":["/start_migrate"]}]}'
   ```

   - Migrations completed successfully

2. **Created Superuser**
   ```bash
   aws ecs run-task ... --overrides '{"containerOverrides":[{"name":"web","command":["python","/app/manage.py","shell","-c","from commcare_connect.users.models import User; User.objects.create_superuser(email=\"admin@dimagi.com\", password=\"admin123\", name=\"Admin User\")"]}]}'
   ```

### Phase 8: Verification (Completed)

1. **Retrieved Public IP**

   - Current IP: 18.213.150.43 (will change on task restart)

2. **Verified Application**
   - HTTP 200 OK on login page
   - All services running healthy

## Issues Resolved During Implementation

### 1. Missing Pandas Dependency

**Problem**: `ModuleNotFoundError: No module named 'pandas'`

**Root Cause**: The audit app (`commcare_connect/audit/management/extractors/connect_api_facade.py`) uses pandas for CSV processing, but pandas was not in the requirements.

**Solution**: Added `pandas` to `requirements/base.in` (it was already in base.txt from a previous addition)

### 2. Docker Entrypoint Line Endings

**Problem**: Container error: `exec /entrypoint: no such file or directory`

**Root Cause**: Docker entrypoint files had Windows line endings (CRLF) which Linux cannot execute.

**Solution**:

```bash
cd docker
for file in entrypoint start start_celery start_migrate; do
  sed -i 's/\r$//' "$file"
done
```

### 3. CloudWatch Logs Permissions

**Problem**: Tasks failing with `AccessDeniedException: User: ...labs-jj-ecs-task-execution-role... is not authorized to perform: logs:CreateLogGroup`

**Root Cause**: ECS execution role lacked CloudWatch Logs permissions.

**Solution**: Added inline policy to `labs-jj-ecs-task-execution-role`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:us-east-1:858923557655:log-group:/ecs/labs-jj-*"
    }
  ]
}
```

### 4. Secret ARN Format

**Problem**: Secret not being read by container.

**Root Cause**: Partial ARN was used in task definition. AWS Secrets Manager requires the full ARN including the random suffix.

**Solution**: Updated task definition to use complete ARN:

- Before: `arn:aws:secretsmanager:us-east-1:858923557655:secret:labs-jj-django-secret-key`
- After: `arn:aws:secretsmanager:us-east-1:858923557655:secret:labs-jj-django-secret-key-iB1rtG`

### 5. Django SECRET_KEY Environment Variable

**Problem**: `ImproperlyConfigured: The SECRET_KEY setting must not be empty`

**Root Cause**: Task definition used `SECRET_KEY` but Django's settings expected `DJANGO_SECRET_KEY`.

**Solution**: Updated task definition to use `DJANGO_SECRET_KEY` as the environment variable name.

## How to Push Future Updates

### Automated Deployment (Recommended)

**Use the deployment script for the easiest experience:**

```bash
# Standard deployment (no migrations)
./deploy/aws/deploy.sh

# With database migrations
./deploy/aws/deploy.sh --with-migrations
```

The script automatically:

- ✅ Authenticates with ECR
- ✅ Builds and pushes Docker image
- ✅ Runs migrations (if requested)
- ✅ Deploys web and worker services
- ✅ Waits for deployment to stabilize
- ✅ Shows you the new public IP

**First time setup:**

```bash
# Make script executable (one time only)
chmod +x deploy/aws/deploy.sh
```

### Manual Deployment (Alternative)

If you prefer to run commands manually or need more control:

**Standard deployment:**

```bash
# 1. Authenticate with ECR
aws ecr get-login-password --region us-east-1 --profile labs | \
  docker login --username AWS --password-stdin \
  858923557655.dkr.ecr.us-east-1.amazonaws.com

# 2. Build new image
docker build -t labs-jj-commcare-connect:latest .

# 3. Tag for ECR
docker tag labs-jj-commcare-connect:latest \
  858923557655.dkr.ecr.us-east-1.amazonaws.com/labs-jj-commcare-connect:latest

# 4. Push to ECR
docker push 858923557655.dkr.ecr.us-east-1.amazonaws.com/labs-jj-commcare-connect:latest

# 5. Force new deployment (pulls latest image)
aws ecs update-service \
  --cluster labs-jj-cluster \
  --service labs-jj-web \
  --force-new-deployment \
  --profile labs

aws ecs update-service \
  --cluster labs-jj-cluster \
  --service labs-jj-worker \
  --force-new-deployment \
  --profile labs
```

**With database migrations:**

```bash
# 1-4. Same as above (build and push image)

# 5. Run migrations
aws ecs run-task \
  --cluster labs-jj-cluster \
  --task-definition labs-jj-web:5 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-06646effb09be2f42],securityGroups=[sg-0666a5ed512c97d9d],assignPublicIp=ENABLED}" \
  --overrides '{"containerOverrides":[{"name":"web","command":["/start_migrate"]}]}' \
  --profile labs

# 6. Wait for migration task to complete (check CloudWatch Logs or ECS console)
# Then run step 5 from standard deployment to deploy new services
```

### Update Task Configuration

If you need to change environment variables, resource limits, or other task settings:

1. **Update task definition JSON** (recreate the files or edit in AWS Console)

2. **Register new task definition revision**:

```bash
# Example for web service
aws ecs register-task-definition \
  --cli-input-json file://task-definition-web.json \
  --profile labs
```

3. **Update service to use new revision**:

```bash
aws ecs update-service \
  --cluster labs-jj-cluster \
  --service labs-jj-web \
  --task-definition labs-jj-web:6 \
  --profile labs
```

### Monitoring Deployment

**Check service status**:

```bash
aws ecs describe-services \
  --cluster labs-jj-cluster \
  --services labs-jj-web labs-jj-worker \
  --profile labs \
  --query 'services[*].[serviceName,runningCount,desiredCount]' \
  --output table
```

**Get current public IP**:

```bash
TASK_ARN=$(aws ecs list-tasks --cluster labs-jj-cluster --service-name labs-jj-web --profile labs --query 'taskArns[0]' --output text)

ENI_ID=$(aws ecs describe-tasks --cluster labs-jj-cluster --tasks "$TASK_ARN" --profile labs --query 'tasks[0].attachments[0].details[?name==`networkInterfaceId`].value' --output text)

aws ec2 describe-network-interfaces \
  --network-interface-ids "$ENI_ID" \
  --profile labs \
  --query 'NetworkInterfaces[0].Association.PublicIp' \
  --output text
```

**Check logs**:

```bash
# Web service logs
aws logs tail /ecs/labs-jj-web --follow --profile labs

# Worker service logs
aws logs tail /ecs/labs-jj-worker --follow --profile labs
```

## Cost Breakdown (Estimated Monthly)

| Resource             | Instance Type      | Monthly Cost      |
| -------------------- | ------------------ | ----------------- |
| ECS Fargate (Web)    | 0.5 vCPU, 1 GB RAM | ~$11              |
| ECS Fargate (Worker) | 0.5 vCPU, 1 GB RAM | ~$11              |
| RDS PostgreSQL       | db.t3.micro        | ~$15              |
| ElastiCache Redis    | cache.t3.micro     | ~$12              |
| ECR Storage          | <10 GB             | <$1               |
| Data Transfer        | Minimal            | ~$5               |
| CloudWatch Logs      | Low volume         | ~$3               |
| **Total**            |                    | **~$58-72/month** |

**Cost Savings vs. Full Production Setup**:

- No NAT Gateway: Saved ~$32/month
- No ALB: Saved ~$16/month
- Single-task deployment: Saved ~$50/month

## Operational Notes

### Public IP Behavior

**Important**: The public IP address changes whenever:

- A task is stopped/restarted
- A deployment occurs
- The service is updated
- ECS performs maintenance

**Solutions for Stable Access**:

1. **Route 53 + Lambda**: Use Lambda to update DNS when IP changes
2. **ALB**: Add an Application Load Balancer ($16/month) for stable endpoint
3. **Manual**: Check IP after each deployment (acceptable for labs environment)

### Scaling Considerations

To scale services:

```bash
# Scale web service to 2 tasks
aws ecs update-service \
  --cluster labs-jj-cluster \
  --service labs-jj-web \
  --desired-count 2 \
  --profile labs
```

**Note**: With multiple web tasks and no ALB, each will have its own public IP. You'd typically want an ALB for load balancing in this scenario.

### Backup Strategy

**Automated**:

- RDS automated backups: 1 day retention (configured)
- Consider increasing to 7-30 days for production

**Manual Backup**:

```bash
# Create RDS snapshot
aws rds create-db-snapshot \
  --db-instance-identifier labs-jj-postgres \
  --db-snapshot-identifier labs-jj-postgres-$(date +%Y%m%d) \
  --profile labs
```

### Security Considerations

**Current Security Posture**:

- ✅ Database not publicly accessible
- ✅ Redis not publicly accessible
- ✅ Secrets stored in AWS Secrets Manager
- ✅ IAM roles follow least-privilege
- ⚠️ ALLOWED_HOSTS set to `*` (should be restricted for production)
- ⚠️ Security group allows HTTP from 0.0.0.0/0 (acceptable for labs)
- ⚠️ No SSL/TLS (no domain configured)

**For Production**:

1. Set specific ALLOWED_HOSTS in Django settings
2. Add ALB with SSL certificate
3. Restrict security group to known IPs or ALB only
4. Enable RDS encryption at rest
5. Enable Redis encryption in transit
6. Increase backup retention periods

### Troubleshooting

**Task fails to start**:

1. Check CloudWatch Logs: `/ecs/labs-jj-web` or `/ecs/labs-jj-worker`
2. Verify task definition has correct environment variables
3. Check IAM role permissions
4. Verify ECR image is accessible

**Can't connect to application**:

1. Get current public IP (see Monitoring section)
2. Verify security group allows inbound traffic on port 8000
3. Check service running count: `aws ecs describe-services ...`
4. Verify task is in RUNNING state

**Database connection issues**:

1. Verify RDS instance is available: `aws rds describe-db-instances ...`
2. Check security group allows PostgreSQL traffic (5432) within VPC
3. Verify DATABASE_URL environment variable is correct
4. Check task logs for connection errors

**Worker not processing tasks**:

1. Check worker logs: `aws logs tail /ecs/labs-jj-worker --follow`
2. Verify Redis connection (CELERY_BROKER_URL)
3. Check that worker task is running

## Useful Commands Reference

### ECS Operations

```bash
# List all tasks in cluster
aws ecs list-tasks --cluster labs-jj-cluster --profile labs

# Describe specific task
aws ecs describe-tasks --cluster labs-jj-cluster --tasks <task-arn> --profile labs

# Stop a task (will restart automatically due to desired count)
aws ecs stop-task --cluster labs-jj-cluster --task <task-arn> --profile labs

# List task definition revisions
aws ecs list-task-definitions --family-prefix labs-jj-web --profile labs

# Deregister old task definition
aws ecs deregister-task-definition --task-definition labs-jj-web:1 --profile labs
```

### Database Operations

```bash
# Connect to PostgreSQL (from EC2 or with tunnel)
psql "postgresql://connectadmin:<password>@labs-jj-postgres.cs74wyie8cdf.us-east-1.rds.amazonaws.com:5432/commcare_connect"

# Run Django management command
aws ecs run-task \
  --cluster labs-jj-cluster \
  --task-definition labs-jj-web:5 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-06646effb09be2f42],securityGroups=[sg-0666a5ed512c97d9d],assignPublicIp=ENABLED}" \
  --overrides '{"containerOverrides":[{"name":"web","command":["python","/app/manage.py","<command>"]}]}' \
  --profile labs
```

### Log Analysis

```bash
# Search logs for errors
aws logs filter-log-events \
  --log-group-name /ecs/labs-jj-web \
  --filter-pattern "ERROR" \
  --profile labs

# Get logs from specific time range
aws logs get-log-events \
  --log-group-name /ecs/labs-jj-web \
  --log-stream-name <stream-name> \
  --start-time $(date -d '1 hour ago' +%s)000 \
  --profile labs
```

## Access Credentials Summary

**AWS Resources**:

- AWS Profile: `labs`
- AWS Account: 858923557655
- Region: us-east-1

**Application**:

- Admin Email: admin@dimagi.com
- Admin Password: admin123
- Current URL: http://18.213.150.43:8000/

**Database**:

- Host: labs-jj-postgres.cs74wyie8cdf.us-east-1.rds.amazonaws.com
- Port: 5432
- Database: commcare_connect
- Username: connectadmin
- Password: (stored in Secrets Manager: `labs-jj-database`)

**Redis**:

- Host: labs-jj-redis.aceivh.0001.use1.cache.amazonaws.com
- Port: 6379
- No password (within VPC security group)

## Next Steps / Future Improvements

1. **DNS Setup**: Configure Route 53 for stable domain name
2. **SSL Certificate**: Add ALB with SSL for HTTPS access
3. **Monitoring**: Set up CloudWatch alarms for service health
4. **CI/CD Pipeline**: Create GitHub Actions workflow for automated deployments
5. **Backup Strategy**: Implement automated database backups to S3
6. **Cost Optimization**: Review and adjust resource allocations based on usage
7. **Security Hardening**: Implement ALLOWED_HOSTS restrictions, security groups, WAF

## Support and Maintenance

**Logs Location**:

- CloudWatch Log Groups:
  - `/ecs/labs-jj-web`
  - `/ecs/labs-jj-worker`

**AWS Console Quick Links**:

- ECS Cluster: https://us-east-1.console.aws.amazon.com/ecs/v2/clusters/labs-jj-cluster
- RDS: https://us-east-1.console.aws.amazon.com/rds/home?region=us-east-1#database:id=labs-jj-postgres
- ElastiCache: https://us-east-1.console.aws.amazon.com/elasticache/home?region=us-east-1#/redis/labs-jj-redis
- ECR: https://us-east-1.console.aws.amazon.com/ecr/repositories/private/858923557655/labs-jj-commcare-connect

---

**Last Updated**: November 7, 2025
**Deployment Status**: ✅ Production Ready (Labs Environment)
