"""Worker entrypoint — dispatches to the correct worker by WORKER_TYPE env var.

Usage (in docker-compose.yml):
  environment:
    - WORKER_TYPE=outbox     # runs outbox_publisher
    - WORKER_TYPE=lifecycle  # runs command_consumer
    - WORKER_TYPE=scheduler  # runs scheduler
"""

import asyncio
import os
import sys


WORKERS: dict[str, str] = {
    "outbox": "app.workers.outbox_publisher",
    "lifecycle": "app.workers.command_consumer",
    "scheduler": "app.workers.scheduler",
}


def main() -> None:
    worker_type = os.environ.get("WORKER_TYPE", "").strip().lower()
    if not worker_type:
        print(
            "ERROR: WORKER_TYPE environment variable is not set.\n"
            f"Valid values: {', '.join(WORKERS)}",
            file=sys.stderr,
        )
        sys.exit(1)

    if worker_type not in WORKERS:
        print(
            f"ERROR: Unknown WORKER_TYPE={worker_type!r}.\n"
            f"Valid values: {', '.join(WORKERS)}",
            file=sys.stderr,
        )
        sys.exit(1)

    module_path = WORKERS[worker_type]
    print(f"Starting worker: {worker_type} ({module_path})", flush=True)

    # Import and run the worker's async main()
    import importlib

    module = importlib.import_module(module_path)
    asyncio.run(module.main())


if __name__ == "__main__":
    main()
