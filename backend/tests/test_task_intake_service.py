from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.core.repo_profile import write_repo_profile
from app.core.project_policy import ProjectPolicy
from app.core.task_intake import TaskIntakeService
from app.models import TaskStatus, WorkspaceKind
from app.schemas import RepoProfileDraft
from app.schemas import TaskIntakeRequest, TaskIntakeTurn


class FakeStore:
    def __init__(self, repo_path: str = "D:/repos/tetris_test"):
        self.repo = SimpleNamespace(
            id=3,
            name="tetris_test",
            path=repo_path,
            default_branch="main",
        )
        self.workspaces = [
            SimpleNamespace(
                id=10,
                name="Main",
                kind=WorkspaceKind.MAIN,
                branch_name="workspace/main/3",
                task_count=1,
                workspace_path=None,
            ),
            SimpleNamespace(
                id=11,
                name="feature/score",
                kind=WorkspaceKind.FEATURE,
                branch_name="workspace/11/feature-score",
                task_count=2,
                workspace_path="D:/workspaces/repo-3/workspace-11-feature-score",
            ),
        ]
        self.tasks = [
            SimpleNamespace(
                id=7,
                title="Fix score rendering",
                status=TaskStatus.NEEDS_ATTENTION,
                workspace_id=11,
                workspace_name="feature/score",
                scheduled_for=None,
            )
        ]

    async def get_repo(self, db, repo_id: int):
        return self.repo if repo_id == self.repo.id else None

    async def list_workspaces(self, db, repo_id: int):
        assert repo_id == self.repo.id
        return self.workspaces

    async def list_tasks(self, db, status=None, repo_id=None):
        assert repo_id == self.repo.id
        return self.tasks


class FakeCodex:
    def __init__(self, payload, error: Exception | None = None):
        self.payload = payload
        self.error = error
        self.calls = []

    async def run_intake(self, prompt: str, cwd, output_schema):
        self.calls.append((prompt, str(cwd)))
        if self.error is not None:
            raise self.error
        return self.payload


def make_policy():
    return ProjectPolicy(
        plan_required=True,
        critique_required=True,
        critique_max_rounds=2,
        test_fix_loops=2,
        review_required=True,
        merge_human_approval=True,
        allow_user_override=False,
        allow_repo_override=False,
        main_allow_feature_work=False,
        main_allow_hotfix=True,
        main_allow_plan_review=True,
        auto_fork_feature_workspace_from_main=True,
        hotfix_keywords=("fix", "bug"),
        plan_review_keywords=("plan", "review"),
    )


def make_profile() -> RepoProfileDraft:
    return RepoProfileDraft(
        language="Python",
        frameworks=["FastAPI"],
        package_manager="uv",
        dev_commands=["uv sync --extra dev"],
        test_commands=["uv run pytest"],
        deploy_considerations="Local development first.",
        main_branch_protection="protected",
        deployment_sensitivity="medium",
    )


@pytest.mark.asyncio
async def test_analyze_uses_repo_scoped_context(tmp_path):
    write_repo_profile(tmp_path, make_profile())
    codex = FakeCodex(
        {
            "draft": {
                "workspace_mode": "existing",
                "workspace_id": 11,
                "new_workspace_name": None,
                "title": "Fix score rendering",
                "description": "Continue the score rendering fix in the existing feature workspace.",
                "blocked_by_task_id": None,
                "scheduled_for": None,
            },
            "questions": [],
            "needs_confirmation": True,
            "notes": ["Continuing the existing score workspace."],
        }
    )
    service = TaskIntakeService(FakeStore(repo_path=str(tmp_path)), codex, make_policy())

    response = await service.analyze(
        None,
        TaskIntakeRequest(repo_id=3, user_request="기존 점수 작업 이어서 수정해줘."),
    )

    assert response.draft.workspace_mode == "existing"
    assert response.draft.workspace_id == 11
    prompt, cwd = codex.calls[0]
    assert Path(cwd) == tmp_path
    assert '"id": 11' in prompt
    assert "feature/score" in prompt
    assert "Fix score rendering" in prompt
    assert "기존 점수 작업 이어서 수정해줘." in prompt
    assert "main workspace is protected" in prompt
    assert "must be written in Korean" in prompt
    assert '"package_manager": "uv"' in prompt
    assert response.repo_profile is not None
    assert response.repo_profile.language == "Python"


def test_parse_response_accepts_fenced_json():
    service = TaskIntakeService(FakeStore(), FakeCodex({}), make_policy())

    response = service._parse_response(
        """
        ```json
        {
          "draft": {
            "workspace_mode": "new",
            "workspace_id": null,
            "new_workspace_name": "feature/tetris",
            "title": "Build Tetris",
            "description": "Create a standalone Tetris game implementation.",
            "blocked_by_task_id": null,
            "scheduled_for": null
          },
          "questions": ["Should this start from the main workspace or stay isolated?"],
          "needs_confirmation": false,
          "notes": ["A new feature workspace seems safer."]
        }
        ```
        """
    )

    assert response.draft.new_workspace_name == "feature/tetris"
    assert response.questions == ["Should this start from the main workspace or stay isolated?"]


def test_parse_response_rejects_invalid_json():
    service = TaskIntakeService(FakeStore(), FakeCodex({}), make_policy())

    with pytest.raises(ValueError, match="유효한 JSON"):
        service._parse_response("not json")


@pytest.mark.asyncio
async def test_analyze_includes_conversation_and_current_draft(tmp_path):
    write_repo_profile(tmp_path, make_profile())
    codex = FakeCodex(
        {
            "draft": {
                "workspace_mode": "unspecified",
                "workspace_id": None,
                "new_workspace_name": None,
                "title": "Build Tetris",
                "description": "Implement the Tetris game.",
                "blocked_by_task_id": None,
                "scheduled_for": None,
            },
            "questions": ["Use the main workspace or create a new one?"],
            "needs_confirmation": False,
            "notes": [],
        }
    )
    service = TaskIntakeService(FakeStore(repo_path=str(tmp_path)), codex, make_policy())

    await service.analyze(
        None,
        TaskIntakeRequest(
            repo_id=3,
            user_request="테트리스 구현",
            conversation=[
                TaskIntakeTurn(role="assistant", message="Use the main workspace or create a new one?"),
                TaskIntakeTurn(role="user", message="새 워크스페이스로 해줘."),
            ],
            draft={
                "workspace_mode": "unspecified",
                "title": "Build Tetris",
            },
        ),
    )

    prompt = codex.calls[0][0]
    assert "새 워크스페이스로 해줘." in prompt
    assert '"workspace_mode": "unspecified"' in prompt


@pytest.mark.asyncio
async def test_analyze_falls_back_when_codex_output_is_not_json(tmp_path):
    write_repo_profile(tmp_path, make_profile())
    service = TaskIntakeService(
        FakeStore(repo_path=str(tmp_path)),
        FakeCodex({}, error=httpx.ConnectError("down")),
        make_policy(),
    )

    response = await service.analyze(
        None,
        TaskIntakeRequest(repo_id=3, user_request="테트리스 게임을 구현해줘."),
    )

    assert response.draft.title == "테트리스 게임을 구현해줘"
    assert response.draft.workspace_mode == "new"
    assert response.draft.new_workspace_name is not None
    assert response.draft.new_workspace_name == "테트리스 게임을 구현해줘"
    assert "실제로 사용할 수 있는 결과물" in response.draft.description
    assert response.needs_confirmation is True
    assert "요청을 바탕으로 초안을 생성했습니다" in response.notes[0]


@pytest.mark.asyncio
async def test_analyze_surfaces_structured_contract_errors(tmp_path):
    write_repo_profile(tmp_path, make_profile())
    service = TaskIntakeService(
        FakeStore(repo_path=str(tmp_path)),
        FakeCodex({}, error=ValueError("bad response")),
        make_policy(),
    )

    with pytest.raises(ValueError, match="bad response"):
        await service.analyze(
            None,
            TaskIntakeRequest(repo_id=3, user_request="테트리스 게임을 구현해줘."),
        )


@pytest.mark.asyncio
async def test_analyze_requests_repo_profile_when_agents_file_is_missing(tmp_path):
    codex = FakeCodex(
        {
            "draft": {
                "workspace_mode": "new",
                "workspace_id": None,
                "new_workspace_name": "analysis-repro",
                "title": "분석 재현 초안 만들기",
                "description": "새 저장소 초기 인테이크 문제를 재현하기 위한 초안이다.",
                "blocked_by_task_id": None,
                "scheduled_for": None,
            },
            "questions": [],
            "needs_confirmation": True,
            "notes": ["초안을 생성했습니다."],
        }
    )
    service = TaskIntakeService(FakeStore(repo_path=str(tmp_path)), codex, make_policy())

    response = await service.analyze(
        None,
        TaskIntakeRequest(repo_id=3, user_request="테트리스 게임을 구현해줘."),
    )

    assert response.repo_profile is not None
    assert response.repo_profile_missing_fields == [
        "language",
        "package_manager",
        "dev_commands",
        "test_commands",
        "deploy_considerations",
    ]
    assert response.draft.title == "분석 재현 초안 만들기"
    assert response.needs_confirmation is True
    assert any("AGENTS.md" in note for note in response.notes)
    assert any("초안 생성은 계속 진행했습니다" in note for note in response.notes)
    assert response.questions[0].startswith("이 저장소는 작업 초안을 만들기 전에")
    assert codex.calls


@pytest.mark.asyncio
async def test_analyze_persists_repo_profile_updates_from_request(tmp_path):
    service = TaskIntakeService(FakeStore(repo_path=str(tmp_path)), FakeCodex(
        {
            "draft": {
                "workspace_mode": "new",
                "workspace_id": None,
                "new_workspace_name": "feature/tetris",
                "title": "Build Tetris",
                "description": "Create a standalone Tetris game implementation.",
                "blocked_by_task_id": None,
                "scheduled_for": None,
            },
            "questions": [],
            "needs_confirmation": True,
            "notes": ["New isolated workspace suggested."],
        }
    ), make_policy())

    response = await service.analyze(
        None,
        TaskIntakeRequest(
            repo_id=3,
            user_request="테트리스 게임을 구현해줘.",
            repo_profile=make_profile(),
        ),
    )

    agents_path = tmp_path / "AGENTS.md"
    assert agents_path.exists()
    assert 'package_manager = "uv"' in agents_path.read_text(encoding="utf-8")
    assert response.repo_profile_missing_fields == []


@pytest.mark.asyncio
async def test_analyze_without_repo_profile_input_does_not_rewrite_agents_file(tmp_path):
    agents_path = tmp_path / "AGENTS.md"
    agents_path.write_text(
        """## Repo Profile
```toml
language = "Python"
frameworks = ["FastAPI"]
package_manager = "uv"
dev_commands = ["uv sync --extra dev"]
test_commands = ["uv run pytest"]
build_commands = []
lint_commands = []
deploy_considerations = "Local only."
main_branch_protection = "protected"
deployment_sensitivity = "medium"
environment_notes = []
safety_rules = []
```
""",
        encoding="utf-8",
    )
    original = agents_path.read_text(encoding="utf-8")
    service = TaskIntakeService(
        FakeStore(repo_path=str(tmp_path)),
        FakeCodex(
            {
                "draft": {
                    "workspace_mode": "new",
                    "workspace_id": None,
                    "new_workspace_name": "feature/tetris",
                    "title": "Build Tetris",
                    "description": "Create a standalone Tetris game implementation.",
                    "blocked_by_task_id": None,
                    "scheduled_for": None,
                },
                "questions": [],
                "needs_confirmation": True,
                "notes": [],
            }
        ),
        make_policy(),
    )

    await service.analyze(
        None,
        TaskIntakeRequest(repo_id=3, user_request="테트리스 게임을 구현해줘."),
    )

    assert agents_path.read_text(encoding="utf-8") == original
