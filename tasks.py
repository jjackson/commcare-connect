"""Useful tasks for use when developing CommCare Connect.

This uses the `Invoke` library."""
from invoke import Context, Exit, call, task


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
    c.run(f"{cmd_base} --resolver=backtracking requirements/base.in{args}", env=env)
    c.run(f"{cmd_base} --resolver=backtracking requirements/dev.in{args}", env=env)
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
