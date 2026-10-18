"""Smoke test: the package installs and imports."""

import genesis


def test_package_exposes_version():
    assert genesis.__version__ == "0.1.0"
