"""Pydantic schemas for admin and role management (Phase 3 remainder)."""

from pydantic import BaseModel, ConfigDict, Field

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
USERNAME_PATTERN = r"^\S+$"


class PermissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    description: str | None = None


class RoleBrief(BaseModel):
    """Role as embedded in AdminOut — name/description only, no permission fan-out."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None


class RoleOut(RoleBrief):
    permissions: list[PermissionOut] = Field(default_factory=list)


class AdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str
    is_active: bool
    roles: list[RoleBrief] = Field(default_factory=list)


class AdminCreate(BaseModel):
    username: str = Field(min_length=1, max_length=64, pattern=USERNAME_PATTERN)
    email: str = Field(min_length=3, max_length=255, pattern=EMAIL_PATTERN)
    password: str = Field(min_length=8, max_length=128)
    is_active: bool = True
    role_ids: list[int] = Field(default_factory=list)


class AdminUpdate(BaseModel):
    username: str | None = Field(
        default=None, min_length=1, max_length=64, pattern=USERNAME_PATTERN
    )
    email: str | None = Field(default=None, min_length=3, max_length=255, pattern=EMAIL_PATTERN)
    password: str | None = Field(default=None, min_length=8, max_length=128)
    is_active: bool | None = None


class AdminRolesUpdate(BaseModel):
    role_ids: list[int]


class RoleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64, pattern=USERNAME_PATTERN)
    description: str | None = Field(default=None, max_length=255)
    permission_codes: list[str] = Field(default_factory=list)


class RoleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64, pattern=USERNAME_PATTERN)
    description: str | None = Field(default=None, max_length=255)


class RolePermissionsUpdate(BaseModel):
    permission_codes: list[str]
