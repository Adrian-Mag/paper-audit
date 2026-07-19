from pathlib import Path

import pytest

from paper_audit.guard import (
    METERED_ENV_VARS,
    MeteredBillingError,
    check_billing_guard,
    enforce_billing_guard,
)


def test_clean_environment_has_no_violations(tmp_path: Path) -> None:
    assert check_billing_guard(environ={}, claude_dir=tmp_path / "nonexistent") == []


def test_enforce_passes_on_clean_environment(tmp_path: Path) -> None:
    enforce_billing_guard(environ={}, claude_dir=tmp_path / "nonexistent")


def test_api_key_env_var_triggers_violation(tmp_path: Path) -> None:
    violations = check_billing_guard(
        environ={"ANTHROPIC_API_KEY": "sk-ant-fake"}, claude_dir=tmp_path / "nonexistent"
    )
    assert len(violations) == 1
    assert "ANTHROPIC_API_KEY" in str(violations[0])


def test_enforce_raises_on_api_key(tmp_path: Path) -> None:
    with pytest.raises(MeteredBillingError, match="ANTHROPIC_API_KEY"):
        enforce_billing_guard(environ={"ANTHROPIC_API_KEY": "sk-ant-fake"}, claude_dir=tmp_path / "nonexistent")


@pytest.mark.parametrize("var_name", METERED_ENV_VARS)
def test_each_metered_env_var_triggers_violation(var_name: str, tmp_path: Path) -> None:
    violations = check_billing_guard(environ={var_name: "1"}, claude_dir=tmp_path / "nonexistent")
    assert len(violations) == 1
    assert var_name in str(violations[0])


def test_empty_string_env_var_does_not_trigger(tmp_path: Path) -> None:
    violations = check_billing_guard(environ={"ANTHROPIC_API_KEY": ""}, claude_dir=tmp_path / "nonexistent")
    assert violations == []


def test_api_key_helper_in_settings_triggers_violation(tmp_path: Path) -> None:
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    (claude_dir / "settings.json").write_text('{"apiKeyHelper": "some-script.sh"}')
    violations = check_billing_guard(environ={}, claude_dir=claude_dir)
    assert len(violations) == 1
    assert "apiKeyHelper" in str(violations[0])


def test_settings_local_json_also_checked(tmp_path: Path) -> None:
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    (claude_dir / "settings.local.json").write_text('{"apiKeyHelper": "x"}')
    violations = check_billing_guard(environ={}, claude_dir=claude_dir)
    assert len(violations) == 1


def test_settings_without_api_key_helper_is_clean(tmp_path: Path) -> None:
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    (claude_dir / "settings.json").write_text('{"theme": "dark"}')
    violations = check_billing_guard(environ={}, claude_dir=claude_dir)
    assert violations == []


def test_malformed_settings_json_does_not_crash(tmp_path: Path) -> None:
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    (claude_dir / "settings.json").write_text("{not valid json")
    violations = check_billing_guard(environ={}, claude_dir=claude_dir)
    assert violations == []


def test_multiple_violations_all_reported(tmp_path: Path) -> None:
    violations = check_billing_guard(
        environ={"ANTHROPIC_API_KEY": "x", "CLAUDE_CODE_USE_BEDROCK": "1"},
        claude_dir=tmp_path / "nonexistent",
    )
    assert len(violations) == 2


def test_enforce_lists_every_violation_in_message(tmp_path: Path) -> None:
    with pytest.raises(MeteredBillingError) as exc_info:
        enforce_billing_guard(
            environ={"ANTHROPIC_API_KEY": "x", "CLAUDE_CODE_USE_BEDROCK": "1"},
            claude_dir=tmp_path / "nonexistent",
        )
    message = str(exc_info.value)
    assert "ANTHROPIC_API_KEY" in message
    assert "CLAUDE_CODE_USE_BEDROCK" in message
