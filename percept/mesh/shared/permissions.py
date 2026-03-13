"""RBAC: admin, member, readonly roles."""
from enum import Enum


class Role(str, Enum):
    ADMIN = "admin"         # Full control: create/delete team, manage members, read/write
    MEMBER = "member"       # Read/write shared graph
    READONLY = "readonly"   # Read only

    def can_write(self) -> bool:
        return self in (Role.ADMIN, Role.MEMBER)

    def can_admin(self) -> bool:
        return self == Role.ADMIN

    def can_read(self) -> bool:
        return True  # All roles can read


# Permission checks
def require_write(role: Role) -> bool:
    if not role.can_write():
        raise PermissionError(f"Role '{role.value}' cannot write to the team graph")
    return True


def require_admin(role: Role) -> bool:
    if not role.can_admin():
        raise PermissionError(f"Role '{role.value}' requires admin privileges")
    return True
