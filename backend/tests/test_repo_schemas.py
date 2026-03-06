import pytest

from app.schemas import RepoCreate


def test_repo_create_strips_wrapping_double_quotes():
    repo = RepoCreate(
        name="dashboard",
        path='  "D:\\Python\\agent\\dashboard"  ',
        default_branch="main",
    )

    assert repo.path == r"D:\Python\agent\dashboard"


def test_repo_create_rejects_empty_path_after_normalization():
    with pytest.raises(ValueError):
        RepoCreate(name="dashboard", path='   ""   ', default_branch="main")
