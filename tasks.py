"""Useful tasks for use when developing CommCare Connect.

This uses the `Invoke` library."""
from pathlib import Path

from invoke import Context, Exit, call, task

PROJECT_DIR = Path(__file__).parent


@task
def docker(c: Context, command):
    """Run docker compose"""
    if command == "up":
        c.run("docker compose -f docker-compose.yml up -d")
    elif command == "down":
        c.run("docker compose -f docker-compose.yml down")
    else:
        raise Exit(f"Unknown docker command: {command}", -1)


@task(pre=[call(docker, command="up")])
def up(c: Context):
    """Run docker compose [up]"""
    pass


@task(pre=[call(docker, command="down")])
def down(c: Context):
    """Run docker compose [down]"""
    pass


@task
def requirements(c: Context, upgrade=False):
    """Re-compile the pip requirements files"""
    args = " -U" if upgrade else ""
    cmd_base = "pip-compile -q --resolver=backtracking"
    env = {"CUSTOM_COMPILE_COMMAND": "inv requirements"}
    c.run(f"{cmd_base} requirements/base.in{args}", env=env)
    c.run(f"{cmd_base} requirements/dev.in{args}", env=env)
    # can't use backtracking resolver for now: https://github.com/pypa/pip/issues/8713
    c.run(f"{cmd_base} requirements/production.in{args}", env=env)


@task
def translations(c: Context):
    """Make Django translations"""
    c.run("python manage.py makemessages --all --ignore node_modules --ignore venv")
    c.run("python manage.py makemessages -d djangojs --all --ignore node_modules --ignore venv")
    c.run("python manage.py compilemessages")


@task
def build_js(c: Context, watch=False, prod=False):
    """Build the JavaScript and CSS assets"""
    if prod:
        if watch:
            print("[warn] Prod build can't be watched")
        c.run("npm run build")
    else:
        extra = "-watch" if watch else ""
        c.run(f"npm run dev{extra}")


@task
def setup_ec2(c: Context, verbose=False, diff=False):
    run_ansible(c, verbose=verbose, diff=diff)

    kamal_cmd = "kamal env push"
    if verbose:
        kamal_cmd += " -v"
    with c.cd(PROJECT_DIR / "deploy"):
        c.run(kamal_cmd)


@task
def django_settings(c: Context, verbose=False, diff=False):
    """Update the Django settings file on prod servers"""
    run_ansible(c, tags="django_settings", verbose=verbose, diff=diff)
    print("\nSettings updated. A re-deploy is required to have the services use the new settings.")
    val = input("Do you want to re-deploy the Django services? [y/N] ")
    if val.lower() == "y":
        deploy(c)


@task
def restart_django(c: Context, verbose=False, diff=False):
    """Restart the Django server on prod servers"""
    run_ansible(c, play="utils.yml", tags="restart", verbose=verbose, diff=diff)


def run_ansible(c: Context, play="play.yml", tags=None, verbose=False, diff=False):
    ansible_cmd = f"ansible-playbook {play} -i inventory.yml"
    if tags:
        ansible_cmd += f" --tags {tags}"
    if verbose:
        ansible_cmd += " -v"
    if diff:
        ansible_cmd += " -D"

    with c.cd(PROJECT_DIR / "deploy"):
        c.run(ansible_cmd)


@task
def deploy(c: Context):
    """Deploy the app to prod servers"""
    with c.cd(PROJECT_DIR / "deploy"):
        c.run("kamal deploy")
