from app.api.tasks import _append_follow_up_instructions


def test_append_follow_up_instructions_to_existing_description():
    result = _append_follow_up_instructions("Original task", "Fix the failing API call")

    assert result == (
        "Original task\n\nFollow-up instructions:\nFix the failing API call"
    )


def test_append_follow_up_instructions_ignores_blank_comment():
    result = _append_follow_up_instructions("Original task", "   ")

    assert result == "Original task"


def test_append_follow_up_instructions_builds_description_when_empty():
    result = _append_follow_up_instructions("", "Retry with a smaller patch")

    assert result == "Follow-up instructions:\nRetry with a smaller patch"
