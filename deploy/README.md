# CommCare Connect Deployment

This folder contains the configuration and scripts for deploying CommCare Connect.

## Overview

CommCare Connect is deployed to AWS using Docker containers. The deployment is managed using [Kamal](https://kamal-deploy.org/), a Ruby-based deployment tool.
See https://semaphoreci.com/blog/mrsk.

Deploying commcare-connect uses the following tools:

- [Ansible](https://www.ansible.com/)

  - Setup of EC2 instances

- [Kamal](https://kamal-deploy.org/)

  - Deployment of Docker containers
  - Management of Docker env files

- [1Password CLI](https://developer.1password.com/docs/cli/get-started/)

  - Store secrets and SSH Keys (retrieved using the 1Password CLI and Ansible module)

- [AWS CLI](https://aws.amazon.com/cli/)
  - Used to manage AWS resources, specifically the Container Registry

## Setup

### Kamal

(requires Ruby)

```bash
gem install kamal -v '~> 1.0.0'
```

### Ansible

This is only required if you need to set up a new EC2 instance.

```bash
python3 -m pip install --user pipx
pipx install ansible
```

### 1Password CLI

See https://developer.1password.com/docs/cli/get-started/

Note: Do not use Flatpack or snap to install 1password CLI as these do not work with the SSH agent.

You will also need to update the 1Password configuration to allow it to access the SSH key:

_~/.config/1Password/ssh/agent.toml_

```toml
[[ssh-keys]]
vault = "Commcare Connect"
```

See https://developer.1password.com/docs/ssh/agent for more details.

To test that this is working you can run:

```bash
ssh connect@3.90.216.194
```

#### AWS CLI

```bash
aws configure sso --profile commcare-connect
aws sso login --profile commcare-connect
```

Note: If you used a different profile name you will need to set the `AWS_PROFILE` environment variable to the profile name.

## Django Settings

The Django settings (environment variables) are configured using in `config/deploy.yml` (see the `env` section).
That file defines all the settings that are required. The values for the 'secret' settings are stored in 1Password
and are extracted and added to the env file by Kamal when running `inv django-settings` (or `kamal envify`).

Kamal uses a Ruby template (`.env.erb`) to extract the settings from 1Pasword.

Secrets are stored in the 1Password under the `Connect Secrets` entry.

To update the Django settings:

```bash
inv django-settings
```

### Adding new settings

1. Add the setting to the `config/deploy.yml` file.
2. If it is a 'secret', edit the `Connect Secrets` entry in 1Password and add a 'text' or 'password' field with
   the name of the setting and it's value.
3. Run `inv django-settings` to deploy the settings to the server.
4. Deploy the app to have it pick up the new settings.

## Deploy

Ideally deploy should be done via GitHub actions however it can be run locally as follows:

```bash
inv deploy
```

## Accessing logs

The logs from the Docker containers are shipped to CloudWatch. To access them you will need to use the AWS console.

You can also view them using Kamal:

```bash
kamal app logs
```

See `kamal app logs --help` for more details.
