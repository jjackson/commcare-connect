#!/bin/bash
set -e

# AWS Fargate Labs Deployment Script
# Usage: ./deploy/aws/deploy.sh [--with-migrations]

CLUSTER="labs-jj-cluster"
WEB_SERVICE="labs-jj-web"
WORKER_SERVICE="labs-jj-worker"
WEB_TASK_DEF="labs-jj-web"
ECR_REGISTRY="858923557655.dkr.ecr.us-east-1.amazonaws.com"
ECR_REPO="labs-jj-commcare-connect"
AWS_REGION="us-east-1"
AWS_PROFILE="labs"
SUBNET_ID="subnet-06646effb09be2f42"
SECURITY_GROUP="sg-0666a5ed512c97d9d"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  CommCare Connect Labs Deployment${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check if --with-migrations flag is provided
RUN_MIGRATIONS=false
if [ "$1" == "--with-migrations" ]; then
    RUN_MIGRATIONS=true
    echo -e "${YELLOW}⚠️  Migrations will be run before deployment${NC}"
    echo ""
fi

# Step 1: Authenticate with ECR
echo -e "${BLUE}[1/6]${NC} Authenticating with ECR..."
aws ecr get-login-password --region $AWS_REGION --profile $AWS_PROFILE | \
    docker login --username AWS --password-stdin $ECR_REGISTRY
echo -e "${GREEN}✓ Authenticated${NC}"
echo ""

# Step 2: Build Docker image
echo -e "${BLUE}[2/6]${NC} Building Docker image..."
docker build -t $ECR_REPO:latest .
echo -e "${GREEN}✓ Image built${NC}"
echo ""

# Step 3: Tag image for ECR
echo -e "${BLUE}[3/6]${NC} Tagging image..."
docker tag $ECR_REPO:latest $ECR_REGISTRY/$ECR_REPO:latest
echo -e "${GREEN}✓ Image tagged${NC}"
echo ""

# Step 4: Push to ECR
echo -e "${BLUE}[4/6]${NC} Pushing image to ECR..."
docker push $ECR_REGISTRY/$ECR_REPO:latest
echo -e "${GREEN}✓ Image pushed${NC}"
echo ""

# Step 5: Run migrations if requested
if [ "$RUN_MIGRATIONS" = true ]; then
    echo -e "${BLUE}[5/6]${NC} Running database migrations..."

    # Get the latest task definition revision
    TASK_DEF_ARN=$(aws ecs describe-task-definition \
        --task-definition $WEB_TASK_DEF \
        --profile $AWS_PROFILE \
        --query 'taskDefinition.taskDefinitionArn' \
        --output text)

    # Run migration task
    TASK_ARN=$(aws ecs run-task \
        --cluster $CLUSTER \
        --task-definition $TASK_DEF_ARN \
        --launch-type FARGATE \
        --network-configuration "awsvpcConfiguration={subnets=[$SUBNET_ID],securityGroups=[$SECURITY_GROUP],assignPublicIp=ENABLED}" \
        --overrides '{"containerOverrides":[{"name":"web","command":["/start_migrate"]}]}' \
        --profile $AWS_PROFILE \
        --query 'tasks[0].taskArn' \
        --output text)

    echo "Migration task started: $TASK_ARN"
    echo "Waiting for migration to complete..."

    # Wait for task to stop (migrations complete)
    aws ecs wait tasks-stopped \
        --cluster $CLUSTER \
        --tasks $TASK_ARN \
        --profile $AWS_PROFILE

    # Check exit code
    EXIT_CODE=$(aws ecs describe-tasks \
        --cluster $CLUSTER \
        --tasks $TASK_ARN \
        --profile $AWS_PROFILE \
        --query 'tasks[0].containers[0].exitCode' \
        --output text)

    if [ "$EXIT_CODE" == "0" ]; then
        echo -e "${GREEN}✓ Migrations completed successfully${NC}"
    else
        echo -e "${RED}✗ Migrations failed with exit code: $EXIT_CODE${NC}"
        echo "Check CloudWatch Logs for details: /ecs/$WEB_SERVICE"
        exit 1
    fi
    echo ""
else
    echo -e "${BLUE}[5/6]${NC} Skipping migrations (use --with-migrations to run)"
    echo ""
fi

# Step 6: Deploy services
echo -e "${BLUE}[6/6]${NC} Deploying services..."

# Update web service
aws ecs update-service \
    --cluster $CLUSTER \
    --service $WEB_SERVICE \
    --force-new-deployment \
    --profile $AWS_PROFILE \
    --query 'service.serviceName' \
    --output text > /dev/null
echo -e "${GREEN}✓ Web service deployment started${NC}"

# Update worker service
aws ecs update-service \
    --cluster $CLUSTER \
    --service $WORKER_SERVICE \
    --force-new-deployment \
    --profile $AWS_PROFILE \
    --query 'service.serviceName' \
    --output text > /dev/null
echo -e "${GREEN}✓ Worker service deployment started${NC}"
echo ""

# Wait for services to stabilize
echo -e "${YELLOW}⏳ Waiting for services to reach steady state (this may take 2-3 minutes)...${NC}"
aws ecs wait services-stable \
    --cluster $CLUSTER \
    --services $WEB_SERVICE $WORKER_SERVICE \
    --profile $AWS_PROFILE

echo -e "${GREEN}✓ Services deployed and stable${NC}"
echo ""

# Get new public IP
echo -e "${BLUE}Getting new public IP...${NC}"
TASK_ARN=$(aws ecs list-tasks \
    --cluster $CLUSTER \
    --service-name $WEB_SERVICE \
    --profile $AWS_PROFILE \
    --query 'taskArns[0]' \
    --output text)

ENI_ID=$(aws ecs describe-tasks \
    --cluster $CLUSTER \
    --tasks $TASK_ARN \
    --profile $AWS_PROFILE \
    --query 'tasks[0].attachments[0].details[?name==`networkInterfaceId`].value' \
    --output text)

PUBLIC_IP=$(aws ec2 describe-network-interfaces \
    --network-interface-ids $ENI_ID \
    --profile $AWS_PROFILE \
    --query 'NetworkInterfaces[0].Association.PublicIp' \
    --output text)

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Deployment Complete! 🎉${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${BLUE}Application URL:${NC} http://$PUBLIC_IP:8000/"
echo -e "${BLUE}Login URL:${NC}      http://$PUBLIC_IP:8000/accounts/login/"
echo ""
echo -e "${YELLOW}Note: Save this IP address. It will change if tasks restart.${NC}"
echo ""
