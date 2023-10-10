import dataclasses


@dataclasses.dataclass
class ConnectIdUser:
    name: str
    username: str
    phone_number: str

    def __str__(self) -> str:
        return f"{self.name} ({self.username})"
