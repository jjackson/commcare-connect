from django.core.management.base import BaseCommand, CommandError
from django.db import connection

# Define tables that the role should NOT have SELECT access to.
# Customize this list based on your application's needs.
PROTECTED_TABLES = [
    "auth_user",
    "django_session",
    "account_emailaddress",
    "account_emailconfirmation",
    "socialaccount_socialaccount",
    "socialaccount_socialapp",
    "socialaccount_socialtoken",
    # Add other sensitive table names here
]


class Command(BaseCommand):
    help = "Creates or updates a PostgreSQL role, grants connect, and grants select on non-protected tables."

    def add_arguments(self, parser):
        parser.add_argument("username", type=str, help="The username for the PostgreSQL role.")
        parser.add_argument("password", type=str, help="The password for the PostgreSQL role.")

    def handle(self, *args, **options):
        username = options["username"]
        password = options["password"]

        if not username or not password:
            raise CommandError("Username and password are required.")

        # Basic validation for username to prevent trivial SQL injection via unquoted identifiers
        # PostgreSQL identifiers are complex, this is a simplistic check.
        # Quoting identifiers (e.g., f'"{username}"') is the primary defense here.
        if not username.isalnum() and "_" not in username:
            self.stdout.write(
                self.style.WARNING(
                    f"Username '{username}' contains potentially unsafe characters. Proceeding with caution using quoted identifiers."  # noqa: E501
                )
            )

        role_exists = False  # Initialize before try block
        try:
            with connection.cursor() as cursor:
                # Check if role exists
                cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s;", [username])
                role_exists = cursor.fetchone()

                if role_exists:
                    self.stdout.write(f"Role '{username}' already exists. Updating password...")
                    # Use f-string with quotes for identifiers, and placeholders for values like password
                    cursor.execute(f'ALTER ROLE "{username}" WITH LOGIN PASSWORD %s;', [password])
                else:
                    self.stdout.write(f"Creating role '{username}'...")
                    cursor.execute(f'CREATE ROLE "{username}" WITH LOGIN PASSWORD %s;', [password])

                db_name = connection.settings_dict["NAME"]
                self.stdout.write(f"Granting CONNECT permission on database '{db_name}' to role '{username}'...")
                cursor.execute(f'GRANT CONNECT ON DATABASE "{db_name}" TO "{username}";')

                self.stdout.write(f"Granting SELECT on non-protected tables to role '{username}'...")
                # Get all tables in the public schema
                cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public';")
                all_tables = [row[0] for row in cursor.fetchall()]

                granted_tables_count = 0
                skipped_tables_count = 0

                for table_name in all_tables:
                    if table_name in PROTECTED_TABLES:
                        self.stdout.write(f"  Skipping SELECT on protected table: {table_name}")
                        # Optionally, ensure no SELECT rights if the role might inherit them elsewhere
                        # cursor.execute(f'REVOKE SELECT ON TABLE "{table_name}" FROM "{username}";')
                        # Not strictly needed for new roles
                        skipped_tables_count += 1
                    else:
                        self.stdout.write(f"  Granting SELECT on table: {table_name}")
                        cursor.execute(f'GRANT SELECT ON TABLE "{table_name}" TO "{username}";')
                        granted_tables_count += 1

                self.stdout.write(
                    f"Granted SELECT on {granted_tables_count} table(s), skipped {skipped_tables_count} protected table(s)."  # noqa: E501
                )

            if role_exists:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Successfully updated role '{username}', ensured connect permission, and updated table permissions."  # noqa: E501
                    )
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Successfully created role '{username}', granted connect permission, and set table permissions."  # noqa: E501
                    )
                )

        except Exception as e:
            error_action = "update" if role_exists else "create"
            raise CommandError(f"Failed to {error_action} role '{username}' or set permissions: {e}")
