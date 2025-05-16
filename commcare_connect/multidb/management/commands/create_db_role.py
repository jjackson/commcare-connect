from django.core.management.base import BaseCommand, CommandError
from django.db import connection

class Command(BaseCommand):
    help = "Creates a new PostgreSQL role with the specified username and password."

    def add_arguments(self, parser):
        parser.add_argument("username", type=str, help="The username for the new PostgreSQL role.")
        parser.add_argument("password", type=str, help="The password for the new PostgreSQL role.")

    def handle(self, *args, **options):
        username = options["username"]
        password = options["password"]

        if not username or not password:
            raise CommandError("Username and password are required.")

        try:
            with connection.cursor() as cursor:
                # Check if role exists
                cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s;", [username])
                role_exists = cursor.fetchone()

                if role_exists:
                    self.stdout.write(f"Role '{username}' already exists. Updating password...")
                    cursor.execute(f"ALTER ROLE {username} WITH LOGIN PASSWORD %s;", [password])
                else:
                    self.stdout.write(f"Creating role '{username}'...")
                    cursor.execute(f"CREATE ROLE {username} WITH LOGIN PASSWORD %s;", [password])

                # Grant connect permission to the current database
                # Django's connection.settings_dict['NAME'] gives the database name
                db_name = connection.settings_dict['NAME']
                self.stdout.write(f"Granting CONNECT permission on database '{db_name}' to role '{username}'...")
                cursor.execute(f"GRANT CONNECT ON DATABASE {db_name} TO {username};")

            if role_exists:
                self.stdout.write(self.style.SUCCESS(f"Successfully updated role '{username}' and ensured connect permission."))
            else:
                self.stdout.write(self.style.SUCCESS(f"Successfully created role '{username}' and granted connect permission."))
        except Exception as e:
            if role_exists:
                raise CommandError(f"Failed to update role '{username}': {e}")
            else:
                raise CommandError(f"Failed to create role '{username}': {e}")
