from types import SimpleNamespace

from app.main import has_pending_interrupt


class FakeGraph:
    def __init__(self, tasks):
        self.tasks = tasks

    def get_state(self, config):
        return SimpleNamespace(tasks=self.tasks)


def make_request(tasks):
    graph = FakeGraph(tasks)

    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(graph=graph)
        )
    )


def test_has_pending_interrupt_returns_true() -> None:
    task = SimpleNamespace(
        interrupts=(SimpleNamespace(value={}),)
    )

    request = make_request([task])

    assert has_pending_interrupt(request, "thread-001") is True


def test_has_pending_interrupt_returns_false_without_interrupt() -> None:
    task = SimpleNamespace(interrupts=())

    request = make_request([task])

    assert has_pending_interrupt(request, "thread-001") is False