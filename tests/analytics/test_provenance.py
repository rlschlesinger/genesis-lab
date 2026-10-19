"""Tests for provenance: git and environment records never crash a run."""

import subprocess

import pytest

from genesis.analytics import provenance


def test_git_info_has_the_expected_shape():
    info = provenance.git_info()
    assert set(info) == {"commit", "dirty"}
    # Inside a checkout: a 40-hex commit and a yes/no. Installed elsewhere: both None.
    if info["commit"] is not None:
        assert len(info["commit"]) == 40 and isinstance(info["dirty"], bool)
    else:
        assert info["dirty"] is None


@pytest.mark.parametrize(
    "error",
    [OSError("git not installed"), subprocess.CalledProcessError(128, "git")],
    ids=["no-git", "not-a-repo"],
)
def test_git_info_falls_back_to_none_when_git_is_unavailable(monkeypatch, error):
    def failing_git(*args):
        raise error

    monkeypatch.setattr(provenance, "_git", failing_git)
    assert provenance.git_info() == {"commit": None, "dirty": None}


def test_environment_records_python_and_every_tracked_package():
    env = provenance.environment()
    assert set(env) == {"python", "platform", "machine", "packages"}
    assert set(env["packages"]) == set(provenance.PACKAGES)
    assert env["packages"]["numpy"]  # installed, so a version string
