"""Utility to generate a bcrypt hash for a password (for a real user store).

Usage:
    python -m scripts.hash_password "MyStrongPassw0rd!"
"""

from __future__ import annotations

import sys

from app.auth.security import hash_password


def main() -> int:
    if len(sys.argv) != 2:
        print('Usage: python -m scripts.hash_password "<password>"', file=sys.stderr)
        return 1
    print(hash_password(sys.argv[1]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
