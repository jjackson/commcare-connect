---
name: aws-env-update
description: Add or update environment variables in the AWS ECS Fargate deployment. Use when the user wants to add env vars, secrets, or update task definitions for the labs environment.
---

# AWS Environment Variable Updates

## Labs Environment Details

- **AWS Profile**: `labs`
- **Cluster**: `labs-jj-cluster`
- **Services**: `labs-jj-web`, `labs-jj-worker` (update both)
- **Secret naming**: `labs-jj-<name>` (e.g., `labs-jj-scale-validation-api-key`)

## Critical: JSON Encoding Issue

PowerShell's JSON output breaks AWS CLI. **Always write task definitions to a local file** using the Write tool, then delete after registering.

## Workflow

1. Login: `aws sso login --profile labs`
2. Fetch current task definition
3. Write updated JSON to local file (remove `taskDefinitionArn`, `revision`, `status`, `requiresAttributes`, `compatibilities`, `registeredAt`, `registeredBy`)
4. Register with `aws ecs register-task-definition --cli-input-json file://filename.json --profile labs`
5. Update both services with `--force-new-deployment`
6. **Delete the local JSON file**
