"""Durable deletion retries for files held open by Windows playback/decoders."""
import logging
from pathlib import Path
import shutil
from uuid import UUID

logger = logging.getLogger(__name__)


def pending_file(data_dir: Path, cid: str):
    if str(UUID(cid)) != cid:
        raise ValueError("Invalid conversation identifier")
    return data_dir / "cleanup-pending" / cid


def delete_uploads(data_dir: Path, cid: str):
    marker = pending_file(data_dir, cid)
    marker.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    already_pending = marker.exists()
    marker.touch(mode=0o600, exist_ok=True)
    try:
        shutil.rmtree(data_dir / "uploads" / cid)
    except FileNotFoundError:
        pass
    except OSError:
        # Keep a durable marker outside the locked folder. Never log media or
        # silently claim physical deletion; the independent watchdog retries.
        if not already_pending:
            logger.warning("Audio cleanup pending; a file may still be open")
        return False
    marker.unlink(missing_ok=True)
    return True


def retry_deletions(data_dir, locks):
    for marker in (data_dir / "cleanup-pending").glob("*"):
        try:
            pending_file(data_dir, marker.name)
        except ValueError:
            continue
        with locks[marker.name]:
            delete_uploads(data_dir, marker.name)
