"""The runner never raises its own privileges, and a shell wrapper is not a way around it.

Every case here asks for the refusal with process execution stubbed out. The refusal is supposed
to fire before `subprocess.run`, so reaching it at all is the failure — and reaching it with a
real escalator is worse than a failed assertion, because `pkexec` and `su` prompt on the terminal
and the run stops rather than reporting.
"""

from __future__ import annotations

import pytest

from scripts import torque_session as session

# The escalators reachable on a Linux operator host. Written out here rather than read off
# `PRIVILEGE_TOKENS`: a case list taken from the thing under test shrinks together with it, so a
# token list narrowed to `sudo` alone would generate one case and report green.
ESCALATORS = ("sudo", "pkexec", "doas", "su")


def test_every_escalator_is_in_the_refusal_list() -> None:
    assert set(ESCALATORS) <= set(session.PRIVILEGE_TOKENS)


@pytest.mark.usefixtures("no_process_execution")
@pytest.mark.parametrize("token", ESCALATORS)
def test_every_escalator_is_refused_as_a_bare_argument(token: str) -> None:
    with pytest.raises(session.SessionRefusedError, match=token):
        session.run_command([token, "true"])


@pytest.mark.usefixtures("no_process_execution")
@pytest.mark.parametrize("token", ESCALATORS)
def test_every_escalator_is_refused_by_absolute_path(token: str) -> None:
    with pytest.raises(session.SessionRefusedError, match=token):
        session.run_command([f"/usr/bin/{token}", "true"])


@pytest.mark.usefixtures("no_process_execution")
@pytest.mark.parametrize("token", ESCALATORS)
def test_every_escalator_is_refused_behind_a_shell_operator(token: str) -> None:
    """`sudo` is the one anybody writes a test for, and it is not the only one on the host."""
    script = f"ip link show can0;{token} ip link set can0 up"
    with pytest.raises(session.SessionRefusedError, match=token):
        session.run_command(["sh", "-c", script])


@pytest.mark.usefixtures("no_process_execution")
def test_a_bare_sudo_argument_is_refused() -> None:
    with pytest.raises(session.SessionRefusedError, match="sudo"):
        session.run_command(["sudo", "true"])


@pytest.mark.usefixtures("no_process_execution")
def test_an_absolute_path_to_sudo_is_refused() -> None:
    with pytest.raises(session.SessionRefusedError, match="sudo"):
        session.run_command(["/usr/bin/sudo", "true"])


@pytest.mark.usefixtures("no_process_execution")
def test_sudo_wrapped_in_a_shell_string_is_refused() -> None:
    with pytest.raises(session.SessionRefusedError, match="sudo"):
        session.run_command(["bash", "-c", "sudo true"])


@pytest.mark.usefixtures("no_process_execution")
def test_sudo_after_a_pipe_inside_one_argument_is_refused() -> None:
    with pytest.raises(session.SessionRefusedError, match="sudo"):
        session.run_command(["sh", "-c", "ip link show can0 && sudo ip link set can0 up"])


@pytest.mark.usefixtures("no_process_execution")
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
    """The one case that reaches a real process, and the process it reaches raises nothing."""
    completed = session.run_command(["printf", "%s", "ok"])
    assert completed.returncode == 0
    assert completed.stdout == "ok"
