from __future__ import annotations

from launcher import LaunchPlan, _build_launch_plan, _should_replace_existing_instance


def test_existing_instance_reuses_state_port_and_opens_browser_synchronously() -> None:
    plan = _build_launch_plan(
        lock_available=False,
        state_port=8501,
        preferred_port=8501,
        selected_port=8502,
    )

    assert plan == LaunchPlan(
        port=8501,
        reuse_existing=True,
        open_browser_in_background=False,
    )


def test_existing_instance_without_state_falls_back_to_preferred_port() -> None:
    plan = _build_launch_plan(
        lock_available=False,
        state_port=None,
        preferred_port=8501,
        selected_port=8502,
    )

    assert plan == LaunchPlan(
        port=8501,
        reuse_existing=True,
        open_browser_in_background=False,
    )


def test_new_instance_uses_selected_port_and_background_browser_open() -> None:
    plan = _build_launch_plan(
        lock_available=True,
        state_port=8501,
        preferred_port=8501,
        selected_port=8503,
    )

    assert plan == LaunchPlan(
        port=8503,
        reuse_existing=False,
        open_browser_in_background=True,
    )


def test_dead_existing_process_should_be_replaced() -> None:
    assert _should_replace_existing_instance(
        pid=123,
        pid_running=False,
        frozen=True,
        state_updated_at=100.0,
        current_executable_updated_at=100.0,
    )


def test_newer_packaged_executable_should_replace_existing_process() -> None:
    assert _should_replace_existing_instance(
        pid=123,
        pid_running=True,
        frozen=True,
        state_updated_at=100.0,
        current_executable_updated_at=102.5,
    )


def test_same_build_existing_process_should_not_be_replaced() -> None:
    assert not _should_replace_existing_instance(
        pid=123,
        pid_running=True,
        frozen=True,
        state_updated_at=100.0,
        current_executable_updated_at=100.5,
    )


def test_non_packaged_run_should_not_replace_alive_process_only_for_newer_files() -> None:
    assert not _should_replace_existing_instance(
        pid=123,
        pid_running=True,
        frozen=False,
        state_updated_at=100.0,
        current_executable_updated_at=200.0,
    )
