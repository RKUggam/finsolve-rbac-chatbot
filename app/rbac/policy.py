"""Role-Based Access Control (RBAC) policy.

This module is the single source of truth for *which department documents a role
may retrieve*. Both the retriever (pre-filter at the vector store) and the API layer
depend on it, so access rules can never drift between enforcement points.

Departments map 1:1 to the sub-folders under `data/` and to the `department`
metadata stored on every vector. Adding a new role or department is a one-line
change here — nothing else needs to know the rules.
"""

from __future__ import annotations

from enum import Enum


class Department(str, Enum):
    """Data domains. Each corresponds to a `data/<department>/` folder."""

    FINANCE = "finance"
    MARKETING = "marketing"
    HR = "hr"
    ENGINEERING = "engineering"
    GENERAL = "general"


class Role(str, Enum):
    """User roles recognised by the system."""

    FINANCE = "finance"
    MARKETING = "marketing"
    HR = "hr"
    ENGINEERING = "engineering"
    C_LEVEL = "c_level"
    EMPLOYEE = "employee"


# Every role can always read GENERAL (company-wide policies, handbook, FAQs).
# C-level executives get the full corpus.
_ALL_DEPARTMENTS: frozenset[Department] = frozenset(Department)

ROLE_DEPARTMENTS: dict[Role, frozenset[Department]] = {
    Role.FINANCE: frozenset({Department.FINANCE, Department.GENERAL}),
    Role.MARKETING: frozenset({Department.MARKETING, Department.GENERAL}),
    Role.HR: frozenset({Department.HR, Department.GENERAL}),
    Role.ENGINEERING: frozenset({Department.ENGINEERING, Department.GENERAL}),
    Role.C_LEVEL: _ALL_DEPARTMENTS,
    Role.EMPLOYEE: frozenset({Department.GENERAL}),
}


def allowed_departments(role: Role) -> frozenset[Department]:
    """Return the set of departments a role is permitted to read."""
    return ROLE_DEPARTMENTS.get(role, frozenset({Department.GENERAL}))


def allowed_department_values(role: Role) -> list[str]:
    """Return allowed departments as plain strings (for vector-store filters)."""
    return sorted(d.value for d in allowed_departments(role))


def can_access(role: Role, department: Department) -> bool:
    """Return True if `role` may read documents from `department`."""
    return department in allowed_departments(role)
