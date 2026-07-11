"""Hard process-boundary worker execution with timeout enforcement."""

from __future__ import annotations

import multiprocessing as mp
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class WorkerResult:
    status: str
    payload: dict[str, Any] | None = None
    error: str | None = None
    worker_process_exit_completed: bool = False
    worker_exit_code: int | None = None


def _worker_entry(
    target: Callable[..., dict[str, Any]],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    queue: mp.Queue,
) -> None:
    try:
        result = target(*args, **kwargs)
        queue.put({"status": "success", "payload": result})
    except Exception as exc:  # noqa: BLE001 - worker boundary must capture all failures
        queue.put({"status": "error", "error": f"{type(exc).__name__}: {exc}"})


def run_worker_with_timeout(
    target: Callable[..., dict[str, Any]],
    *,
    args: tuple[Any, ...] = (),
    kwargs: dict[str, Any] | None = None,
    timeout_s: float,
) -> WorkerResult:
    if timeout_s <= 0:
        raise ValueError("timeout_s must be positive")

    ctx = mp.get_context("spawn")
    queue: mp.Queue = ctx.Queue()
    process = ctx.Process(
        target=_worker_entry,
        args=(target, args, kwargs or {}, queue),
    )
    process.start()
    process.join(timeout=timeout_s)

    if process.is_alive():
        process.terminate()
        process.join(timeout=5)
        if process.is_alive():
            process.kill()
            process.join(timeout=5)
        return WorkerResult(status="timeout", worker_process_exit_completed=process.exitcode is not None)

    exit_code = process.exitcode
    exit_completed = exit_code is not None and exit_code == 0

    if queue.empty():
        return WorkerResult(
            status="error",
            error=f"worker exited without result (exitcode={exit_code})",
            worker_process_exit_completed=exit_completed,
            worker_exit_code=exit_code,
        )

    message = queue.get_nowait()
    status = message.get("status")
    if status == "success":
        payload = message.get("payload")
        if not isinstance(payload, dict):
            return WorkerResult(
                status="error",
                error="worker payload must be a dict",
                worker_process_exit_completed=exit_completed,
                worker_exit_code=exit_code,
            )
        return WorkerResult(
            status="success",
            payload=payload,
            worker_process_exit_completed=exit_completed,
            worker_exit_code=exit_code,
        )
    return WorkerResult(
        status="error",
        error=str(message.get("error", "unknown worker error")),
        worker_process_exit_completed=exit_completed,
        worker_exit_code=exit_code,
    )
