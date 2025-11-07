#!/bin/bash

# CommCare Connect - Elastic Beanstalk Setup Script
# This script creates and configures the EB environment

set -e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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

echo_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

# Check required tools
if ! command -v eb &>/dev/null; then
    echo_error "EB CLI not found. Install with: pip install awsebcli"
    exit 1
fi

# Default values
APP_NAME=${APP_NAME:-commcare-connect-labs}
ENV_NAME=${ENV_NAME:-labs}
AWS_REGION=${AWS_REGION:-us-east-1}

# Load infrastructure config if available
if [ -f "/tmp/aws-infra-config.sh" ]; then
    source /tmp/aws-infra-config.sh
    echo_info "Loaded infrastructure configuration"
fi

echo_info "Setting up Elastic Beanstalk"
echo_info "Application: $APP_NAME"
echo_info "Environment: $ENV_NAME"
echo_info "Region: $AWS_REGION"
echo ""

# Navigate to project root (assuming script is in deploy/aws/)
cd "$(dirname "$0")/../.."

# Initialize EB if not already done
if [ ! -d ".elasticbeanstalk" ]; then
    echo_step "Initializing Elastic Beanstalk..."
    eb init -p docker $APP_NAME --region $AWS_REGION
else
    echo_info "Elastic Beanstalk already initialized"
fi

# Check if environment exists
if eb list | grep -q "$ENV_NAME"; then
    echo_warn "Environment '$ENV_NAME' already exists"
    read -p "Do you want to update it? (y/N): " UPDATE_ENV
    if [[ ! $UPDATE_ENV =~ ^[Yy]$ ]]; then
        echo_info "Skipping environment creation"
        exit 0
    fi
    echo_step "Updating environment..."
    eb deploy $ENV_NAME
else
    echo_step "Creating Elastic Beanstalk environment..."
    echo_info "This will take 5-10 minutes..."

    # Build environment create command
    EB_CREATE_CMD="eb create $ENV_NAME \
        --instance-type t3.small \
        --region $AWS_REGION \
        --envvars \
            DJANGO_SETTINGS_MODULE=config.settings.staging,\
            DJANGO_DEBUG=False,\
            DJANGO_ALLOWED_HOSTS=.elasticbeanstalk.com,\
            AWS_REGION=$AWS_REGION,\
            COMMCARE_HQ_URL=https://staging.commcarehq.org,\
            CONNECT_PRODUCTION_URL=https://connect.dimagi.com"

    # Add VPC configuration if available
    if [ -n "$VPC_ID" ]; then
        SUBNET_IDS=$(aws ec2 describe-subnets \
            --filters "Name=vpc-id,Values=$VPC_ID" \
            --query 'Subnets[*].SubnetId' \
            --output text | tr '\t' ',' | head -c -1)

        EB_CREATE_CMD="$EB_CREATE_CMD \
            --vpc.id $VPC_ID \
            --vpc.elbsubnets $SUBNET_IDS \
            --vpc.ec2subnets $SUBNET_IDS \
            --vpc.publicip"
    fi

    # Execute creation
    eval $EB_CREATE_CMD

    echo_info "Environment created successfully"
fi

# Get environment URL
ENV_URL=$(eb status $ENV_NAME | grep "CNAME" | awk '{print $2}')

echo ""
echo_info "=========================================="
echo_info "Elastic Beanstalk setup complete!"
echo_info "=========================================="
echo ""
echo_info "Environment URL: http://$ENV_URL"
echo ""
echo_info "Next steps:"
echo "1. Verify the deployment: eb open $ENV_NAME"
echo "2. Check logs: eb logs $ENV_NAME"
echo "3. Create superuser: eb ssh $ENV_NAME (then run createsuperuser)"
echo "4. Configure custom domain and SSL certificate"
echo ""
echo_info "Useful commands:"
echo "- Deploy updates: eb deploy $ENV_NAME"
echo "- View logs: eb logs $ENV_NAME --stream"
echo "- SSH to instance: eb ssh $ENV_NAME"
echo "- Environment status: eb status $ENV_NAME"
echo ""
