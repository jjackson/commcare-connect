Deploy SSH key stored in 1password

- Update 1password config to allow ssh access to the key
  - https://developer.1password.com/docs/ssh/agent/config

_./config/1password/ssh_

```python
[[ssh-keys]]
vault = "Commcare Connect"
```

aws sso login --profile connect-staging
