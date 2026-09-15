"""RBAC policy — the security-critical access rules."""

from __future__ import annotations

from app.rbac.policy import (
    Department,
    Role,
    allowed_department_values,
    can_access,
)
from app.rag.retriever import build_rbac_filter


def test_c_level_sees_everything():
    for dept in Department:
        assert can_access(Role.C_LEVEL, dept)


def test_finance_cannot_read_hr_or_engineering():
    assert can_access(Role.FINANCE, Department.FINANCE)
    assert can_access(Role.FINANCE, Department.GENERAL)
    assert not can_access(Role.FINANCE, Department.HR)
    assert not can_access(Role.FINANCE, Department.ENGINEERING)
    assert not can_access(Role.FINANCE, Department.MARKETING)


def test_employee_only_sees_general():
    assert allowed_department_values(Role.EMPLOYEE) == ["general"]
    assert not can_access(Role.EMPLOYEE, Department.FINANCE)
    assert not can_access(Role.EMPLOYEE, Department.HR)


def test_every_role_can_read_general():
    for role in Role:
        assert can_access(role, Department.GENERAL)


def test_filter_expression_lists_only_allowed_departments():
    expr = build_rbac_filter(Role.MARKETING)
    assert expr == 'department in ["general", "marketing"]'
    # A forbidden department must never appear in the pushdown filter.
    assert "finance" not in expr
    assert "hr" not in expr
