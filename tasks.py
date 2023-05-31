from invoke import task, Context, Exit, call


@task
def docker(c: Context, command):
    if command == 'up':
        c.run("docker-compose -f docker-compose-dev.yml up -d")
    elif command == 'down':
        c.run("docker-compose -f docker-compose-dev.yml down")
    else:
        raise Exit(f"Unknown docker command: {command}", -1)


@task(pre=[call(docker, command='up')])
def up(c: Context):
    pass


@task(pre=[call(docker, command='down')])
def down(c: Context):
    pass


@task
def requirements(c: Context, upgrade=False):
    args = " -U" if upgrade else ""
    cmd_base = "pip-compile -q"
    env = {"CUSTOM_COMPILE_COMMAND": "inv requirements"}
    c.run(f"{cmd_base} --resolver=backtracking requirements/base.in{args}", env=env)
    c.run(f"{cmd_base} --resolver=backtracking requirements/dev.in{args}", env=env)
    # can't use backtracking resolver for now: https://github.com/pypa/pip/issues/8713
    c.run(f"{cmd_base} requirements/production.in{args}", env=env)


@task
def translations(c: Context):
    c.run("python manage.py makemessages --all --ignore node_modules --ignore venv")
    c.run("python manage.py makemessages -d djangojs --all --ignore node_modules --ignore venv")
    c.run("python manage.py compilemessages")


@task
def api_schema(c: Context):
    c.run('python manage.py spectacular --file api_schema.yaml')


@task
def build_js(c: Context, watch=False, prod=False):
    if prod:
        if watch:
            print("[warn] Prod build can't be watched")
        c.run("npm run build")
    else:
        extra = "-watch" if watch else ""
        c.run(f"npm run dev{extra}")
