#!/bin/bash
# This script is used by Ansible to retrieve the Ansible Vault password from 1Password.
# Use it by passing `--vault-password-file=vault_password.sh` to Ansible.

VAULT_ID="CommCare Connect"
VAULT_ANSIBLE_NAME="Ansible Vault"
op item get --vault="$VAULT_ID" "$VAULT_ANSIBLE_NAME" --fields password
