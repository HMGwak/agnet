import pytest

from app.schemas import RepoCreate


def make_profile():
    return {
        "language": "Python",
        "frameworks": ["FastAPI"],
        "package_manager": "uv",
        "dev_commands": ["uv sync --extra dev"],
        "test_commands": ["uv run pytest"],
        "deploy_considerations": "Local development first.",
    }


def test_repo_create_strips_wrapping_double_quotes():
    repo = RepoCreate(
        name="dashboard",
        path='  "D:\\Python\\agent\\dashboard"  ',
        default_branch="main",
        profile=make_profile(),
    )

    assert repo.path == r"D:\Python\agent\dashboard"


def test_repo_create_rejects_empty_path_after_normalization():
    with pytest.raises(ValueError):
        RepoCreate(
            name="dashboard",
            path='   ""   ',
            default_branch="main",
            profile=make_profile(),
        )


def test_repo_create_requires_profile_fields():
    with pytest.raises(ValueError, match="Missing repo profile fields"):
        RepoCreate(
            name="dashboard",
            path=r"D:\Python\agent\dashboard",
            default_branch="main",
            profile={"language": "Python"},
        )
