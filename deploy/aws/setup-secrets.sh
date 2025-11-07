#!/bin/bash

# CommCare Connect - AWS Secrets Setup Script
# This script creates all necessary secrets in AWS Secrets Manager

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

# Load infrastructure config if available
if [ -f "/tmp/aws-infra-config.sh" ]; then
    source /tmp/aws-infra-config.sh
    echo_info "Loaded infrastructure configuration"
fi

AWS_REGION=${AWS_REGION:-us-east-1}

echo_info "Setting up secrets in AWS Secrets Manager"
echo_info "Region: $AWS_REGION"
echo ""

# Function to create or update secret
create_or_update_secret() {
    local secret_name=$1
    local secret_value=$2

    if aws secretsmanager describe-secret --secret-id $secret_name --region $AWS_REGION &>/dev/null; then
        echo_warn "Secret '$secret_name' exists, updating..."
        aws secretsmanager update-secret \
            --secret-id $secret_name \
            --secret-string "$secret_value" \
            --region $AWS_REGION &>/dev/null
    else
        echo_info "Creating secret '$secret_name'..."
        aws secretsmanager create-secret \
            --name $secret_name \
            --description "CommCare Connect Labs - ${secret_name##*/}" \
            --secret-string "$secret_value" \
            --region $AWS_REGION &>/dev/null
    fi
}

# Django secret key
echo_info "Generating Django secret key..."
DJANGO_SECRET=$(openssl rand -base64 64)
create_or_update_secret "/commcare-connect/labs/django-secret-key" "$DJANGO_SECRET"

# Database credentials
if [ -n "$DB_ENDPOINT" ] && [ -n "$DB_PASSWORD" ]; then
    echo_info "Storing database credentials..."
    DB_SECRET=$(cat <<EOF
{
  "username": "connectadmin",
  "password": "$DB_PASSWORD",
  "engine": "postgres",
  "host": "$DB_ENDPOINT",
  "port": 5432,
  "dbname": "commcare_connect"
}
EOF
)
    create_or_update_secret "/commcare-connect/labs/database" "$DB_SECRET"
else
    echo_warn "DB_ENDPOINT or DB_PASSWORD not set, skipping database secret"
fi

# Redis connection
if [ -n "$REDIS_ENDPOINT" ] && [ -n "$REDIS_PORT" ]; then
    echo_info "Storing Redis connection..."
    REDIS_SECRET=$(cat <<EOF
{
  "host": "$REDIS_ENDPOINT",
  "port": $REDIS_PORT
}
EOF
)
    create_or_update_secret "/commcare-connect/labs/redis" "$REDIS_SECRET"
else
    echo_warn "REDIS_ENDPOINT or REDIS_PORT not set, skipping Redis secret"
fi

# Prompt for application secrets
echo ""
echo_info "=========================================="
echo_info "Configure application secrets"
echo_info "=========================================="
echo ""
echo_warn "Press Enter to skip optional secrets"

# Twilio
echo ""
read -p "Enter Twilio Account SID (optional): " TWILIO_SID
read -p "Enter Twilio Auth Token (optional): " TWILIO_TOKEN
read -p "Enter Twilio Messaging Service SID (optional): " TWILIO_SERVICE

if [ -n "$TWILIO_SID" ]; then
    TWILIO_SECRET=$(cat <<EOF
{
  "sid": "$TWILIO_SID",
  "token": "$TWILIO_TOKEN",
  "messaging_service": "$TWILIO_SERVICE"
}
EOF
)
    create_or_update_secret "/commcare-connect/labs/twilio" "$TWILIO_SECRET"
fi

# Mapbox
echo ""
read -p "Enter Mapbox Token (optional): " MAPBOX_TOKEN
if [ -n "$MAPBOX_TOKEN" ]; then
    create_or_update_secret "/commcare-connect/labs/mapbox-token" "$MAPBOX_TOKEN"
fi

# ConnectID
echo ""
read -p "Enter ConnectID Client ID: " CONNECTID_CLIENT_ID
read -p "Enter ConnectID Client Secret: " CONNECTID_CLIENT_SECRET
if [ -n "$CONNECTID_CLIENT_ID" ]; then
    CONNECTID_SECRET=$(cat <<EOF
{
  "client_id": "$CONNECTID_CLIENT_ID",
  "client_secret": "$CONNECTID_CLIENT_SECRET"
}
EOF
)
    create_or_update_secret "/commcare-connect/labs/connectid" "$CONNECTID_SECRET"
fi

# Connect Production OAuth
echo ""
read -p "Enter Connect Production OAuth Client ID: " CONNECT_CLIENT_ID
read -p "Enter Connect Production OAuth Client Secret: " CONNECT_CLIENT_SECRET
if [ -n "$CONNECT_CLIENT_ID" ]; then
    CONNECT_SECRET=$(cat <<EOF
{
  "client_id": "$CONNECT_CLIENT_ID",
  "client_secret": "$CONNECT_CLIENT_SECRET"
}
EOF
)
    create_or_update_secret "/commcare-connect/labs/connect-oauth" "$CONNECT_SECRET"
fi

echo ""
echo_info "=========================================="
echo_info "Secrets setup complete!"
echo_info "=========================================="
echo ""
echo_info "Next steps:"
echo "1. Run setup-eb.sh to create Elastic Beanstalk environment"
echo "2. Deploy your application"
echo ""
