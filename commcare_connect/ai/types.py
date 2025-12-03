from dataclasses import dataclass

from django.http import HttpRequest

from commcare_connect.users.models import User


@dataclass
class UserDependencies:
    user: User
    program_id: int | None = None
    request: HttpRequest | None = None
