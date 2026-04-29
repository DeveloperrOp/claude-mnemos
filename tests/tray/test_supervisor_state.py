from __future__ import annotations

import pytest

from claude_mnemos.tray.supervisor import SupervisorState, valid_transition


def test_state_enum_values() -> None:
    expected = {"starting", "running", "restarting", "stopping", "stopped", "crashed"}
    actual = {s.value for s in SupervisorState}
    assert actual == expected


def test_initial_states_allowed() -> None:
    # Any → Starting is allowed (initial transition from None)
    assert valid_transition(None, SupervisorState.STARTING) is True


@pytest.mark.parametrize("from_, to_, ok", [
    (SupervisorState.STARTING, SupervisorState.RUNNING, True),
    (SupervisorState.STARTING, SupervisorState.CRASHED, True),  # spawn failed
    (SupervisorState.STARTING, SupervisorState.STOPPED, False),  # weird, must Stop first
    (SupervisorState.RUNNING, SupervisorState.RESTARTING, True),
    (SupervisorState.RUNNING, SupervisorState.STOPPING, True),
    (SupervisorState.RUNNING, SupervisorState.CRASHED, True),
    (SupervisorState.RUNNING, SupervisorState.STARTING, False),
    (SupervisorState.RESTARTING, SupervisorState.RUNNING, True),
    (SupervisorState.RESTARTING, SupervisorState.CRASHED, True),
    (SupervisorState.STOPPING, SupervisorState.STOPPED, True),
    (SupervisorState.STOPPING, SupervisorState.RUNNING, False),
    (SupervisorState.STOPPED, SupervisorState.STARTING, True),  # manual restart
    (SupervisorState.STOPPED, SupervisorState.RUNNING, False),
    (SupervisorState.CRASHED, SupervisorState.STARTING, True),  # manual restart from menu
    (SupervisorState.CRASHED, SupervisorState.RUNNING, False),
])
def test_valid_transitions(from_: SupervisorState, to_: SupervisorState, ok: bool) -> None:
    assert valid_transition(from_, to_) is ok
