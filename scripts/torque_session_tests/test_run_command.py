"""The runner never raises its own privileges, and a shell wrapper is not a way around it."""

from __future__ import annotations

import pytest

from scripts import torque_session as session


def test_a_bare_sudo_argument_is_refused() -> None:
    with pytest.raises(session.SessionRefusedError, match="sudo"):
        session.run_command(["sudo", "true"])


def test_an_absolute_path_to_sudo_is_refused() -> None:
    with pytest.raises(session.SessionRefusedError, match="sudo"):
        session.run_command(["/usr/bin/sudo", "true"])


def test_sudo_wrapped_in_a_shell_string_is_refused() -> None:
    with pytest.raises(session.SessionRefusedError, match="sudo"):
        session.run_command(["bash", "-c", "sudo true"])


def test_sudo_after_a_pipe_inside_one_argument_is_refused() -> None:
    with pytest.raises(session.SessionRefusedError, match="sudo"):
        session.run_command(["sh", "-c", "ip link show can0 && sudo ip link set can0 up"])


@pytest.mark.parametrize(
    "script",
    [
        "ip link show can0;sudo ip link set can0 up",
        "ip link show can0&&sudo ip link set can0 up",
        "true|sudo tee /sys/class/net/can0/x",
        "$(sudo id)",
        "true\nsudo ip link set can0 up",
    ],
)
def test_a_shell_operator_is_a_word_boundary_like_a_space(script: str) -> None:
    with pytest.raises(session.SessionRefusedError, match="sudo"):
        session.run_command(["sh", "-c", script])


def test_a_command_that_escalates_nothing_runs() -> None:
    completed = session.run_command(["printf", "%s", "ok"])
    assert completed.returncode == 0
    assert completed.stdout == "ok"
