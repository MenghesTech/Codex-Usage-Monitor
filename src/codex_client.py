from __future__ import annotations

import json
import logging
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from .codex_locator import find_codex
from .usage_model import Usage, parse_usage


logger = logging.getLogger(__name__)


class CodexProtocolError(RuntimeError):
    pass


@dataclass
class _PendingResponse:
    generation: int
    event: threading.Event = field(default_factory=threading.Event)
    response: dict[str, Any] | None = None
    error: BaseException | None = None


NotificationHandler = Callable[[dict[str, Any]], None]
ServerRequestHandler = Callable[[dict[str, Any]], Any]


class CodexClient:
    """JSON-lines client with one-shot dispatch for every stdout message."""

    def __init__(
        self,
        notification_handler: NotificationHandler | None = None,
        server_request_handler: ServerRequestHandler | None = None,
    ):
        self.proc: subprocess.Popen[str] | None = None
        self.next_id = 1
        self._generation = 0
        self._pending: dict[Any, _PendingResponse] = {}
        self._state_lock = threading.RLock()
        self._start_lock = threading.RLock()
        self._write_lock = threading.Lock()
        self._notification_handler = notification_handler
        self._server_request_handler = server_request_handler

    @property
    def pending_count(self) -> int:
        with self._state_lock:
            return len(self._pending)

    def start(self) -> None:
        with self._start_lock:
            if self.proc is not None and self.proc.poll() is None:
                return

            exe = find_codex()
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            proc = subprocess.Popen(
                [str(exe), "app-server", "--stdio"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=flags,
            )
            with self._state_lock:
                self._generation += 1
                generation = self._generation
                self.proc = proc

            threading.Thread(
                target=self._reader,
                args=(proc, generation),
                name=f"codex-reader-{generation}",
                daemon=True,
            ).start()
            threading.Thread(
                target=self._stderr_reader,
                args=(proc, generation),
                name=f"codex-stderr-{generation}",
                daemon=True,
            ).start()

            try:
                self._request_raw(
                    "initialize",
                    {
                        "clientInfo": {
                            "name": "codex-usage-monitor",
                            "title": "Codex Usage Monitor",
                            "version": "1.0.0",
                        },
                        "capabilities": {"experimentalApi": False},
                    },
                    timeout=10,
                )
            except Exception:
                self._stop_process(proc, generation)
                raise

    def _reader(self, proc: subprocess.Popen[str], generation: int) -> None:
        assert proc.stdout is not None
        try:
            for line_number, line in enumerate(proc.stdout, 1):
                try:
                    message = json.loads(line)
                except (json.JSONDecodeError, TypeError) as exc:
                    logger.warning(
                        "Codex app-server produced invalid JSON on line %d (%s)",
                        line_number,
                        type(exc).__name__,
                    )
                    continue
                if not isinstance(message, dict):
                    logger.warning(
                        "Codex app-server produced a non-object message on line %d",
                        line_number,
                    )
                    continue
                self._dispatch(message, generation)
        finally:
            code = proc.poll()
            self._fail_generation(
                generation,
                ConnectionError(
                    "Codex app-server cerró la salida"
                    + (f" (código {code})" if code is not None else "")
                ),
                proc,
            )

    def _stderr_reader(self, proc: subprocess.Popen[str], generation: int) -> None:
        assert proc.stderr is not None
        # Drain stderr without echoing content that may include local paths.
        count = sum(1 for _line in proc.stderr)
        if count:
            logger.debug(
                "Codex app-server generation %d emitted %d diagnostic lines",
                generation,
                count,
            )

    def _dispatch(self, message: dict[str, Any], generation: int) -> None:
        has_id = "id" in message
        has_method = "method" in message
        if has_method and has_id:
            self._handle_server_request(message, generation)
        elif has_method:
            self._handle_notification(message)
        elif has_id:
            self._handle_response(message, generation)
        else:
            logger.warning("Ignored unclassifiable Codex app-server message")

    def _handle_response(self, message: dict[str, Any], generation: int) -> None:
        request_id = message.get("id")
        try:
            with self._state_lock:
                pending = self._pending.get(request_id)
                if pending is None or pending.generation != generation:
                    logger.debug("Ignored late or stale Codex response")
                    return
                del self._pending[request_id]
                pending.response = message
        except TypeError:
            logger.warning("Ignored Codex response with an invalid id")
            return
        pending.event.set()

    def _handle_notification(self, message: dict[str, Any]) -> None:
        if self._notification_handler is None:
            logger.debug("Unhandled Codex notification: %s", message.get("method"))
            return
        try:
            self._notification_handler(message)
        except Exception:
            logger.exception("Codex notification handler failed")

    def _handle_server_request(
        self, message: dict[str, Any], generation: int
    ) -> None:
        request_id = message.get("id")
        if self._server_request_handler is None:
            reply = {
                "id": request_id,
                "error": {"code": -32601, "message": "Client method not supported"},
            }
        else:
            try:
                result = self._server_request_handler(message)
                reply = {"id": request_id, "result": result or {}}
            except Exception as exc:
                logger.exception("Codex server-request handler failed")
                reply = {
                    "id": request_id,
                    "error": {"code": -32603, "message": type(exc).__name__},
                }
        try:
            self._write_message(reply, generation)
        except Exception:
            logger.exception("Could not reply to Codex server request")

    def _write_message(self, message: dict[str, Any], generation: int) -> None:
        with self._write_lock:
            with self._state_lock:
                proc = self.proc
                if generation != self._generation or proc is None or proc.poll() is not None:
                    raise ConnectionError("Codex app-server no está disponible")
                stdin = proc.stdin
            if stdin is None:
                raise ConnectionError("Codex app-server no tiene entrada estándar")
            stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
            stdin.flush()

    def _request_raw(
        self, method: str, params: dict[str, Any], timeout: float = 15
    ) -> dict[str, Any]:
        with self._state_lock:
            proc = self.proc
            if proc is None or proc.poll() is not None:
                raise ConnectionError("Codex app-server no está disponible")
            generation = self._generation
            request_id = self.next_id
            self.next_id += 1
            pending = _PendingResponse(generation)
            self._pending[request_id] = pending

        try:
            self._write_message(
                {"id": request_id, "method": method, "params": params},
                generation,
            )
        except Exception:
            with self._state_lock:
                if self._pending.get(request_id) is pending:
                    del self._pending[request_id]
            raise

        deadline = time.monotonic() + timeout
        while not pending.event.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not pending.event.wait(remaining):
                with self._state_lock:
                    if self._pending.get(request_id) is pending:
                        del self._pending[request_id]
                raise TimeoutError(f"Sin respuesta de Codex para {method}")

        if pending.error is not None:
            raise pending.error
        response = pending.response or {}
        if response.get("error"):
            raise RuntimeError(str(response["error"]))
        result = response.get("result")
        if not isinstance(result, dict):
            raise CodexProtocolError("Codex returned an invalid result")
        return result

    def _request(
        self, method: str, params: dict[str, Any], timeout: float = 15
    ) -> dict[str, Any]:
        self.start()
        return self._request_raw(method, params, timeout)

    def usage(self) -> Usage:
        result = self._request(
            "account/rateLimits/read",
            {"skipRateLimitResetCreditsDetail": True},
        )
        if not any(
            key in result
            for key in ("ordinaryUsageAllowed", "rateLimits", "rateLimitsByLimitId")
        ):
            raise CodexProtocolError("Codex returned invalid rate limits")
        return parse_usage(result)

    def _fail_generation(
        self,
        generation: int,
        error: BaseException,
        proc: subprocess.Popen[str] | None = None,
    ) -> None:
        failed: list[_PendingResponse] = []
        with self._state_lock:
            for request_id, pending in list(self._pending.items()):
                if pending.generation == generation:
                    del self._pending[request_id]
                    pending.error = error
                    failed.append(pending)
            if generation == self._generation and (proc is None or self.proc is proc):
                self.proc = None
        for pending in failed:
            pending.event.set()

    def _stop_process(
        self, proc: subprocess.Popen[str], generation: int
    ) -> None:
        if proc.poll() is None:
            try:
                proc.terminate()
            except OSError:
                logger.debug("Could not terminate Codex app-server", exc_info=True)
        self._fail_generation(
            generation,
            ConnectionError("Codex app-server se detuvo"),
            proc,
        )

    def close(self) -> None:
        with self._start_lock:
            with self._state_lock:
                proc = self.proc
                generation = self._generation
            if proc is not None:
                self._stop_process(proc, generation)
