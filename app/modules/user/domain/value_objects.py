import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Email:
    """Value Object: Ensures email is always valid."""

    value: str

    def __post_init__(self) -> None:
        if not re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", self.value):
            raise ValueError(f"Invalid email format: {self.value}")


@dataclass(frozen=True)
class HashedPassword:
    """Value Object: Explicitly marks a string as hashed so we never accidentally use plain text."""

    value: str


@dataclass(frozen=True)
class PlainPassword:
    """Value Object: Ensures plain-text password meets strength requirements."""

    value: str

    def __post_init__(self) -> None:
        """enforces the same rules regardless of how the use case is invoked (HTTP, CLI, background jobs)"""

        if len(self.value) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        if not re.search(r"[A-Z]", self.value):
            raise ValueError("Password must contain at least one uppercase letter.")
        if not re.search(r"[^a-zA-Z0-9]", self.value):
            raise ValueError("Password must contain at least one special character.")


@dataclass(frozen=True)
class PhoneNumber:
    """Value Object: Ensures phone number is in valid E.164 format."""

    value: str

    def __post_init__(self) -> None:
        """enforces the same rules regardless of how the use case is invoked (HTTP, CLI, background jobs)"""

        if not re.match(r"^\+[1-9]\d{1,14}$", self.value):
            raise ValueError(f"Invalid phone number format: {self.value}")
