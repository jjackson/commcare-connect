# AWS Elastic Beanstalk Deployment Scripts

This directory contains helper scripts for deploying CommCare Connect to AWS Elastic Beanstalk.

## Prerequisites

1. Install AWS CLI v2:

```bash
# Download from: https://aws.amazon.com/cli/
aws --version  # Should be 2.x
```

2. Install EB CLI:

```bash
pip install awsebcli
eb --version
```

3. Configure AWS credentials:

```bash
aws configure
# Enter: Access Key ID, Secret Key, Region (us-east-1), Output (json)
```

4. Set environment variables:

```bash
export APP_NAME="commcare-connect-labs"
export ENV_NAME="labs"
export AWS_REGION="us-east-1"
```

## Quick Start

### Complete Setup (30-40 minutes)

```bash
cd deploy/aws

# Make scripts executable
chmod +x *.sh

# 1. Setup infrastructure (~20 mins)
bash setup-infrastructure.sh

# 2. Configure secrets (~2 mins)
bash setup-secrets.sh

# 3. Create EB environment (~10 mins)
bash setup-eb.sh
```

## Individual Scripts

### `setup-infrastructure.sh`

Creates AWS infrastructure:

- VPC (optional, uses default if not specified)
- Security Groups (web, RDS, Redis)
- RDS PostgreSQL instance
- ElastiCache Redis cluster

**Usage:**

```bash
export APP_NAME="commcare-connect-labs"
export AWS_REGION="us-east-1"
export USE_CUSTOM_VPC="false"  # Set to "true" for custom VPC
bash setup-infrastructure.sh
```

**Time**: ~20 minutes (RDS and Redis creation are slow)

### `setup-secrets.sh`

Creates secrets in AWS Secrets Manager:

- Django SECRET_KEY
- Database credentials
- Redis connection
- Twilio credentials (optional)
- Mapbox token (optional)
- OAuth credentials

**Usage:**

```bash
# Load infrastructure config
source /tmp/aws-infra-config.sh

bash setup-secrets.sh
```

**Time**: ~2 minutes (interactive)

### `setup-eb.sh`

Creates Elastic Beanstalk application and environment:

- Initializes EB application
- Creates environment with Docker platform
- Configures environment variables
- Sets up VPC and security groups

**Usage:**

```bash
export APP_NAME="commcare-connect-labs"
export ENV_NAME="labs"
bash setup-eb.sh
```

**Time**: ~10 minutes

## Configuration Files

The deployment also requires these configuration files in your project root:

### `.elasticbeanstalk/config.yml`

Created automatically by `eb init`. Example:

```yaml
branch-defaults:
  labs-aws:
    environment: labs
global:
  application_name: commcare-connect-labs
  default_platform: Docker
  default_region: us-east-1
  instance_profile: connect-eb-ec2-role
```

### `.ebextensions/` Directory

Configuration files for EB environment:

- `01_packages.config` - System packages
- `02_environment.config` - Environment settings
- `03_container_commands.config` - Deployment commands (migrations, etc.)
- `04_celery.config` - Celery worker setup

### `.platform/hooks/` Directory

Lifecycle hooks for fetching secrets and other pre-deploy tasks.

## Common Tasks

### Deploy New Version

```bash
cd /path/to/project
eb deploy labs
```

### View Logs

```bash
# Recent logs
eb logs labs

# Stream logs in real-time
eb logs labs --stream

# Download all logs
eb logs labs --all
```

### SSH to Instance

```bash
eb ssh labs

# Then run Django commands
cd /var/app/current
source /var/app/venv/*/bin/activate
python manage.py createsuperuser
```

### Update Environment Variables

```bash
eb setenv VAR_NAME=value ANOTHER_VAR=value
```

### Scale Instances

```bash
# Scale to 2 instances
eb scale 2 labs

# Or update in .ebextensions/02_environment.config:
# aws:autoscaling:asg:
#   MinSize: 2
#   MaxSize: 4
```

### Environment Status

```bash
eb status labs
eb health labs
```

## Troubleshooting

### Script fails with "permission denied"

```bash
chmod +x setup-infrastructure.sh setup-secrets.sh setup-eb.sh
```

### "DB instance already exists" error

This is normal - scripts are idempotent. They skip existing resources.

### Environment health is "Red"

```bash
# Check logs
eb logs labs | grep ERROR

# Common issues:
# - Database connection fails → check security groups
# - Secret access denied → verify IAM role permissions
# - Application won't start → check Dockerfile and logs
```

### Can't connect to RDS from application

```bash
# Verify security group allows connection
aws ec2 describe-security-groups --group-ids $SG_RDS

# Ensure EB instance is in same VPC
eb config labs  # Check VPCId matches RDS VPC
```

## Manual Deployment Steps

If you prefer not to use scripts:

### 1. Create Infrastructure

```bash
# See Phase 2 in AWS-deploy-test.md
```

### 2. Initialize EB

```bash
eb init -p docker commcare-connect-labs --region us-east-1
```

### 3. Create Environment

```bash
eb create labs --instance-type t3.small
```

### 4. Deploy

```bash
eb deploy labs
```

## Cost Estimates

**Standard Configuration (~$75/month)**:

- EC2 t3.small (1 instance): ~$15
- Application Load Balancer: ~$18
- RDS db.t3.small: ~$25
- ElastiCache t3.micro: ~$12
- Data Transfer & Storage: ~$5

**Budget Configuration (~$35/month)**:

- EC2 t3.micro (single instance): ~$7
- No Load Balancer: $0
- RDS db.t3.micro: ~$15
- Redis on EC2: $0
- Data Transfer & Storage: ~$3

## CI/CD with GitHub Actions

See `.github/workflows/deploy-labs-aws.yml` for automated deployment.

Required GitHub Secrets:

- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_REGION`
- `AWS_ACCOUNT_ID`
- `EB_APPLICATION_NAME`
- `EB_ENVIRONMENT_NAME`

## Clean Up

**WARNING**: This deletes ALL resources and data!

```bash
# Delete EB environment
eb terminate labs --force

# Delete RDS
aws rds delete-db-instance \
  --db-instance-identifier connect-postgres \
  --skip-final-snapshot

# Delete Redis
aws elasticache delete-cache-cluster \
  --cache-cluster-id connect-redis

# Delete security groups, VPC, etc.
# (See AWS-deploy-test.md Phase 10 for complete cleanup)
```

## Support

For detailed documentation, see `../../AWS-deploy-test.md`.
