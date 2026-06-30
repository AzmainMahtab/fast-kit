class OwnerNotFoundError(Exception):
    """Owner with the given identifier was not found."""

    pass


class OwnerAlreadyExistsError(Exception):
    """Owner for the given user already exists."""

    pass
