#!/bin/bash
# Helper script to get the password for the ECR registry
# This is used by Kamal during deploy. See ./deploy/config/deploy.yml

REGION=us-east-1
PROFILE_ARG=""
if [ -z "$CI" ]; then
  # if not in github actions, specify the profile
  PROFILE_ARG=" --profile ${AWS_PROFILE:-commcare-connect}"
fi

aws ecr get-login-password --region=$REGION $PROFILE_ARG
