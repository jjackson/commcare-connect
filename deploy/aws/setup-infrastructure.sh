#!/bin/bash

# CommCare Connect - AWS Infrastructure Setup Script
# This script automates Phase 2 of the AWS deployment plan

set -e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

echo_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

echo_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if required environment variables are set
if [ -z "$APP_NAME" ]; then
    echo_error "APP_NAME environment variable is not set"
    echo "Usage: export APP_NAME=commcare-connect-labs && bash setup-infrastructure.sh"
    exit 1
fi

# Default values
AWS_REGION=${AWS_REGION:-us-east-1}
DB_INSTANCE_NAME=${DB_INSTANCE_NAME:-connect-postgres}
REDIS_CLUSTER_NAME=${REDIS_CLUSTER_NAME:-connect-redis}
USE_CUSTOM_VPC=${USE_CUSTOM_VPC:-false}

echo_info "Starting AWS infrastructure setup"
echo_info "Application: $APP_NAME"
echo_info "Region: $AWS_REGION"
echo ""

# Check AWS CLI is configured
if ! aws sts get-caller-identity &>/dev/null; then
    echo_error "AWS CLI is not configured. Run 'aws configure' first."
    exit 1
fi

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo_info "AWS Account ID: $ACCOUNT_ID"

# Phase 2.1: VPC Setup (Optional)
if [ "$USE_CUSTOM_VPC" = "true" ]; then
    echo_info "Creating custom VPC..."

    VPC_ID=$(aws ec2 create-vpc \
        --cidr-block 10.0.0.0/16 \
        --tag-specifications 'ResourceType=vpc,Tags=[{Key=Name,Value=commcare-connect-vpc}]' \
        --query 'Vpc.VpcId' \
        --output text 2>/dev/null || \
        aws ec2 describe-vpcs \
            --filters "Name=tag:Name,Values=commcare-connect-vpc" \
            --query 'Vpcs[0].VpcId' \
            --output text)

    if [ -z "$VPC_ID" ] || [ "$VPC_ID" = "None" ]; then
        echo_error "Failed to create or find VPC"
        exit 1
    fi

    echo_info "VPC ID: $VPC_ID"

    # Enable DNS hostnames
    aws ec2 modify-vpc-attribute --vpc-id $VPC_ID --enable-dns-hostnames

    # Create Internet Gateway
    IGW_ID=$(aws ec2 create-internet-gateway \
        --tag-specifications 'ResourceType=internet-gateway,Tags=[{Key=Name,Value=connect-igw}]' \
        --query 'InternetGateway.InternetGatewayId' \
        --output text 2>/dev/null || \
        aws ec2 describe-internet-gateways \
            --filters "Name=tag:Name,Values=connect-igw" \
            --query 'InternetGateways[0].InternetGatewayId' \
            --output text)

    aws ec2 attach-internet-gateway --vpc-id $VPC_ID --internet-gateway-id $IGW_ID 2>/dev/null || true

    echo_info "Created/attached Internet Gateway: $IGW_ID"
else
    echo_info "Using default VPC (recommended for labs)"
    VPC_ID=$(aws ec2 describe-vpcs \
        --filters "Name=isDefault,Values=true" \
        --query 'Vpcs[0].VpcId' \
        --output text)
    echo_info "Default VPC ID: $VPC_ID"
fi

# Get subnets
SUBNET_IDS=$(aws ec2 describe-subnets \
    --filters "Name=vpc-id,Values=$VPC_ID" \
    --query 'Subnets[*].SubnetId' \
    --output text | tr '\t' ',')

echo_info "Subnets: $SUBNET_IDS"

# Phase 2.2: Security Groups
echo_info "Creating security groups..."

# Web security group
SG_WEB=$(aws ec2 create-security-group \
    --group-name connect-web-sg \
    --description "Security group for Connect web tier" \
    --vpc-id $VPC_ID \
    --query 'GroupId' \
    --output text 2>/dev/null || \
    aws ec2 describe-security-groups \
        --filters "Name=group-name,Values=connect-web-sg" "Name=vpc-id,Values=$VPC_ID" \
        --query 'SecurityGroups[0].GroupId' \
        --output text)

# Allow HTTP/HTTPS
aws ec2 authorize-security-group-ingress \
    --group-id $SG_WEB \
    --protocol tcp --port 80 --cidr 0.0.0.0/0 2>/dev/null || true

aws ec2 authorize-security-group-ingress \
    --group-id $SG_WEB \
    --protocol tcp --port 443 --cidr 0.0.0.0/0 2>/dev/null || true

echo_info "Web Security Group: $SG_WEB"

# RDS security group
SG_RDS=$(aws ec2 create-security-group \
    --group-name connect-rds-sg \
    --description "Security group for Connect RDS" \
    --vpc-id $VPC_ID \
    --query 'GroupId' \
    --output text 2>/dev/null || \
    aws ec2 describe-security-groups \
        --filters "Name=group-name,Values=connect-rds-sg" "Name=vpc-id,Values=$VPC_ID" \
        --query 'SecurityGroups[0].GroupId' \
        --output text)

aws ec2 authorize-security-group-ingress \
    --group-id $SG_RDS \
    --protocol tcp --port 5432 --source-group $SG_WEB 2>/dev/null || true

echo_info "RDS Security Group: $SG_RDS"

# Redis security group
SG_REDIS=$(aws ec2 create-security-group \
    --group-name connect-redis-sg \
    --description "Security group for Connect Redis" \
    --vpc-id $VPC_ID \
    --query 'GroupId' \
    --output text 2>/dev/null || \
    aws ec2 describe-security-groups \
        --filters "Name=group-name,Values=connect-redis-sg" "Name=vpc-id,Values=$VPC_ID" \
        --query 'SecurityGroups[0].GroupId' \
        --output text)

aws ec2 authorize-security-group-ingress \
    --group-id $SG_REDIS \
    --protocol tcp --port 6379 --source-group $SG_WEB 2>/dev/null || true

echo_info "Redis Security Group: $SG_REDIS"

# Phase 2.3: RDS PostgreSQL
echo_info "Creating RDS PostgreSQL instance (this may take 10-15 minutes)..."

# Create DB subnet group
SUBNET_ARRAY=(${SUBNET_IDS//,/ })
aws rds create-db-subnet-group \
    --db-subnet-group-name connect-db-subnet \
    --db-subnet-group-description "Subnet group for Connect RDS" \
    --subnet-ids ${SUBNET_ARRAY[@]} \
    --tags Key=Name,Value=connect-db-subnet 2>/dev/null || \
    echo_warn "DB subnet group already exists"

# Generate password
DB_PASSWORD=$(openssl rand -base64 32)

# Check if RDS instance exists
if aws rds describe-db-instances --db-instance-identifier $DB_INSTANCE_NAME &>/dev/null; then
    echo_warn "RDS instance already exists, skipping creation"
    DB_ENDPOINT=$(aws rds describe-db-instances \
        --db-instance-identifier $DB_INSTANCE_NAME \
        --query 'DBInstances[0].Endpoint.Address' \
        --output text)
else
    aws rds create-db-instance \
        --db-instance-identifier $DB_INSTANCE_NAME \
        --db-instance-class db.t3.small \
        --engine postgres \
        --engine-version 15.4 \
        --master-username connectadmin \
        --master-user-password "$DB_PASSWORD" \
        --allocated-storage 20 \
        --storage-type gp3 \
        --storage-encrypted \
        --vpc-security-group-ids $SG_RDS \
        --db-subnet-group-name connect-db-subnet \
        --backup-retention-period 7 \
        --preferred-backup-window "03:00-04:00" \
        --preferred-maintenance-window "sun:04:00-sun:05:00" \
        --no-publicly-accessible \
        --db-name commcare_connect \
        --tags Key=Name,Value=connect-postgres

    echo_info "Waiting for RDS instance to become available..."
    aws rds wait db-instance-available --db-instance-identifier $DB_INSTANCE_NAME

    DB_ENDPOINT=$(aws rds describe-db-instances \
        --db-instance-identifier $DB_INSTANCE_NAME \
        --query 'DBInstances[0].Endpoint.Address' \
        --output text)

    echo_info "RDS instance created"
fi

echo_info "RDS Endpoint: $DB_ENDPOINT"

# Phase 2.4: ElastiCache Redis
echo_info "Creating ElastiCache Redis cluster (this may take 10-15 minutes)..."

# Create cache subnet group
aws elasticache create-cache-subnet-group \
    --cache-subnet-group-name connect-redis-subnet \
    --cache-subnet-group-description "Subnet group for Connect Redis" \
    --subnet-ids ${SUBNET_ARRAY[@]} 2>/dev/null || \
    echo_warn "Redis subnet group already exists"

# Check if Redis cluster exists
if aws elasticache describe-cache-clusters --cache-cluster-id $REDIS_CLUSTER_NAME &>/dev/null; then
    echo_warn "Redis cluster already exists, skipping creation"
    REDIS_ENDPOINT=$(aws elasticache describe-cache-clusters \
        --cache-cluster-id $REDIS_CLUSTER_NAME \
        --show-cache-node-info \
        --query 'CacheClusters[0].CacheNodes[0].Endpoint.Address' \
        --output text)
    REDIS_PORT=$(aws elasticache describe-cache-clusters \
        --cache-cluster-id $REDIS_CLUSTER_NAME \
        --show-cache-node-info \
        --query 'CacheClusters[0].CacheNodes[0].Endpoint.Port' \
        --output text)
else
    aws elasticache create-cache-cluster \
        --cache-cluster-id $REDIS_CLUSTER_NAME \
        --cache-node-type cache.t3.micro \
        --engine redis \
        --engine-version 7.0 \
        --num-cache-nodes 1 \
        --cache-subnet-group-name connect-redis-subnet \
        --security-group-ids $SG_REDIS \
        --preferred-maintenance-window "sun:05:00-sun:06:00" \
        --tags Key=Name,Value=connect-redis

    echo_info "Waiting for Redis cluster to become available..."
    aws elasticache wait cache-cluster-available --cache-cluster-id $REDIS_CLUSTER_NAME

    REDIS_ENDPOINT=$(aws elasticache describe-cache-clusters \
        --cache-cluster-id $REDIS_CLUSTER_NAME \
        --show-cache-node-info \
        --query 'CacheClusters[0].CacheNodes[0].Endpoint.Address' \
        --output text)

    REDIS_PORT=$(aws elasticache describe-cache-clusters \
        --cache-cluster-id $REDIS_CLUSTER_NAME \
        --show-cache-node-info \
        --query 'CacheClusters[0].CacheNodes[0].Endpoint.Port' \
        --output text)

    echo_info "Redis cluster created"
fi

echo_info "Redis Endpoint: $REDIS_ENDPOINT:$REDIS_PORT"

# Save configuration
echo ""
echo_info "=========================================="
echo_info "Infrastructure setup complete!"
echo_info "=========================================="
echo ""
echo_info "Configuration summary (save these values):"
echo ""
echo "export VPC_ID=$VPC_ID"
echo "export SG_WEB=$SG_WEB"
echo "export SG_RDS=$SG_RDS"
echo "export SG_REDIS=$SG_REDIS"
echo "export DB_ENDPOINT=$DB_ENDPOINT"
echo "export DB_PASSWORD='$DB_PASSWORD'"
echo "export REDIS_ENDPOINT=$REDIS_ENDPOINT"
echo "export REDIS_PORT=$REDIS_PORT"
echo ""
echo_info "Next steps:"
echo "1. Run setup-secrets.sh to store secrets in AWS Secrets Manager"
echo "2. Run setup-eb.sh to create Elastic Beanstalk environment"
echo "3. Deploy your application"
echo ""

# Save to file for later use
cat > /tmp/aws-infra-config.sh <<EOF
export VPC_ID=$VPC_ID
export SG_WEB=$SG_WEB
export SG_RDS=$SG_RDS
export SG_REDIS=$SG_REDIS
export DB_ENDPOINT=$DB_ENDPOINT
export DB_PASSWORD='$DB_PASSWORD'
export REDIS_ENDPOINT=$REDIS_ENDPOINT
export REDIS_PORT=$REDIS_PORT
export AWS_REGION=$AWS_REGION
export ACCOUNT_ID=$ACCOUNT_ID
EOF

echo_info "Configuration saved to /tmp/aws-infra-config.sh"
