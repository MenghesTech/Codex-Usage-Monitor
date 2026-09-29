from __future__ import annotations

import json
import threading
import time

import pytest

from src import codex_client
from src.codex_client import CodexClient, CodexProtocolError


class FakeStdin:
    def __init__(self):
        self.messages = []
        self.condition = threading.Condition()

    def write(self, value):
        with self.condition:
            self.messages.append(json.loads(value))
            self.condition.notify_all()

    def flush(self):
        pass

    def wait_for_messages(self, count, timeout=1):
        deadline = time.monotonic() + timeout
        with self.condition:
            while len(self.messages) < count:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise AssertionError("request was not written")
                self.condition.wait(remaining)


class FakeProcess:
    def __init__(self):
        self.stdin = FakeStdin()
        self._returncode = None

    def poll(self):
        return self._returncode

    def terminate(self):
        self._returncode = -15


def prepared_client(**kwargs):
    client = CodexClient(**kwargs)
    process = FakeProcess()
    client.proc = process
    client._generation = 1
    return client, process


def begin_request(client, process, timeout=1):
    outcome = {}

    def run():
        try:
            outcome["result"] = client._request_raw("test/read", {}, timeout)
        except BaseException as exc:
            outcome["error"] = exc

    thread = threading.Thread(target=run)
    thread.start()
    process.stdin.wait_for_messages(1)
    request_id = process.stdin.messages[0]["id"]
    return thread, outcome, request_id


def finish(thread):
    thread.join(1)
    assert not thread.is_alive()


def test_normal_response_resolves_only_its_pending_request():
    client, process = prepared_client()
    thread, outcome, request_id = begin_request(client, process)

    client._dispatch({"id": request_id, "result": {"ok": True}}, 1)

    finish(thread)
    assert outcome == {"result": {"ok": True}}
    assert client.pending_count == 0


def test_notification_interleaved_with_response_is_consumed_once():
    notifications = []
    client, process = prepared_client(notification_handler=notifications.append)
    thread, outcome, request_id = begin_request(client, process)
    message = {"method": "account/rateLimits/updated", "params": {"sparse": True}}

    client._dispatch(message, 1)
    client._dispatch({"id": request_id, "result": {"ok": True}}, 1)

    finish(thread)
    assert outcome["result"] == {"ok": True}
    assert notifications == [message]
    assert client.pending_count == 0


def test_consecutive_notifications_never_reappear_in_response_channel():
    notifications = []
    client, _ = prepared_client(notification_handler=notifications.append)
    messages = [
        {"method": "account/rateLimits/updated", "params": {"n": number}}
        for number in range(4)
    ]

    for message in messages:
        client._dispatch(message, 1)

    assert notifications == messages
    assert client.pending_count == 0
    assert not hasattr(client, "q")


def test_server_request_with_same_id_does_not_resolve_client_request():
    handled = []
    client, process = prepared_client(
        server_request_handler=lambda message: handled.append(message) or {"accepted": True}
    )
    thread, outcome, request_id = begin_request(client, process)

    client._dispatch({"id": request_id, "method": "server/question", "params": {}}, 1)
    assert client.pending_count == 1
    assert handled[0]["method"] == "server/question"
    assert process.stdin.messages[-1] == {
        "id": request_id,
        "result": {"accepted": True},
    }

    client._dispatch({"id": request_id, "result": {"answer": 42}}, 1)
    finish(thread)
    assert outcome["result"] == {"answer": 42}


def test_timeout_removes_pending_and_late_response_is_ignored():
    client, process = prepared_client()

    with pytest.raises(TimeoutError):
        client._request_raw("slow/read", {}, timeout=0.01)

    request_id = process.stdin.messages[0]["id"]
    assert client.pending_count == 0
    client._dispatch({"id": request_id, "result": {"late": True}}, 1)
    assert client.pending_count == 0


def test_eof_cleans_pending_and_old_generation_cannot_contaminate_restart():
    client, first_process = prepared_client()
    thread, outcome, old_id = begin_request(client, first_process)

    client._fail_generation(1, ConnectionError("EOF"), first_process)
    finish(thread)
    assert isinstance(outcome["error"], ConnectionError)
    assert client.pending_count == 0

    second_process = FakeProcess()
    client.proc = second_process
    client._generation = 2
    thread, outcome, new_id = begin_request(client, second_process)

    client._dispatch({"id": old_id, "result": {"stale": True}}, 1)
    assert thread.is_alive()
    client._dispatch({"id": new_id, "result": {"fresh": True}}, 2)
    finish(thread)
    assert outcome == {"result": {"fresh": True}}
    assert client.pending_count == 0


def test_non_object_result_is_a_real_protocol_error():
    client, process = prepared_client()
    thread, outcome, request_id = begin_request(client, process)

    client._dispatch({"id": request_id, "result": []}, 1)

    finish(thread)
    assert isinstance(outcome["error"], CodexProtocolError)


def test_located_codex_whose_app_server_cannot_launch_is_not_not_found(
    tmp_path, monkeypatch
):
    executable = tmp_path / "codex.exe"
    executable.write_bytes(b"placeholder")
    monkeypatch.setattr(codex_client, "find_codex", lambda: executable)

    def fail_launch(*_args, **_kwargs):
        raise OSError("simulated app-server launch failure")

    monkeypatch.setattr(codex_client.subprocess, "Popen", fail_launch)

    with pytest.raises(OSError, match="app-server launch failure"):
        CodexClient().start()
