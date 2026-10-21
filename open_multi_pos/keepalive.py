"""A single foreground WSL client, launched in a hidden Windows window."""

import fcntl
import os
import signal
import sys
from pathlib import Path


def main():
    directory = Path.home() / ".local/share/openmultipos"
    directory.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(
        directory / ".keepalive.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600
    )
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0  # Reopening the launcher must not create another keeper.
        if "--check" in sys.argv:
            return 1  # Acquiring the lock means no keeper is currently running.
        while True:
            signal.pause()
    finally:
        os.close(descriptor)


if __name__ == "__main__":
    sys.exit(main())
