"""Bounded asynchronous subprocess validation; never parse PDFs in the server."""
import asyncio
import json
import os
from pathlib import Path
import sys
import threading
from fastapi import HTTPException

WALL_SECONDS = 8
MAX_WORKERS = 1  # one 128 MiB child leaves room in the 512 MiB API container
_slots = threading.BoundedSemaphore(MAX_WORKERS)
WORKER = Path(__file__).with_name('corporate_pdf_worker.py')


async def validate_pdf(content):
    if not _slots.acquire(blocking=False):
        raise HTTPException(503, 'PDF validation is busy; please try again shortly')
    process = None
    spawn = None
    try:
        # No app environment, credentials, PYTHONPATH, HOME or working-dir
        # imports. Windows needs SystemRoot for the Python runtime itself.
        environment = {key: os.environ[key] for key in ('SystemRoot', 'WINDIR') if key in os.environ}
        spawn = asyncio.create_task(asyncio.create_subprocess_exec(
            sys.executable, '-I', str(WORKER), stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            env=environment, cwd=str(WORKER.parent), close_fds=True))
        async def run():
            nonlocal process
            process = await asyncio.shield(spawn)
            output, _ = await process.communicate(content)
            return output
        try:
            output = await asyncio.wait_for(run(), WALL_SECONDS)
        except asyncio.TimeoutError:
            raise HTTPException(400, 'PDF validation took too long; please use a smaller or simpler PDF') from None
        if len(output) > 128:
            raise ValueError('invalid worker result')
        result = json.loads(output)
        if not result.get('isolation'):
            raise HTTPException(503, 'Secure PDF validation is unavailable; please try again later')
        if process.returncode != 0 or result.get('ok') is not True:
            raise ValueError('invalid PDF')
    except HTTPException:
        raise
    except (OSError, NotImplementedError):
        raise HTTPException(503, 'Secure PDF validation is unavailable; please try again later') from None
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(400, 'PDF must be readable, valid, unencrypted and within processing limits') from None
    finally:
        # Shield cleanup even on request cancellation; a cancelled spawn must
        # still be awaited so its child cannot escape ownership.
        async def cleanup():
            child = process
            if child is None and spawn is not None:
                try:
                    child = await spawn
                except Exception:
                    pass
            if child is not None and child.returncode is None:
                try:
                    child.kill()
                except ProcessLookupError:
                    pass
                await child.communicate()
        task = asyncio.create_task(cleanup())
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            await task
            raise
        finally:
            _slots.release()
