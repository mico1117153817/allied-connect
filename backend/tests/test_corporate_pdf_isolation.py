"""Real subprocess lifecycle/resource tests, with small benign fixtures."""
import asyncio
import io
import os
from pathlib import Path
import subprocess
import sys
import pytest
from fastapi import HTTPException
from app.services import corporate_pdf as service
from tests.test_corporate_documents import harness, upload, pdf


def sleeping_worker(tmp_path):
    path = tmp_path / 'slow_worker.py'
    path.write_text("import time, sys\nsys.stdin.buffer.read()\ntime.sleep(30)\nprint('{\"ok\": true, \"isolation\": true}')\n")
    return path


@pytest.mark.parametrize('cancel', [False, True])
def test_timeout_cancel_reaps_child_and_releases_slot(tmp_path, monkeypatch, cancel):
    monkeypatch.setattr(service, 'WORKER', sleeping_worker(tmp_path))
    monkeypatch.setattr(service, 'WALL_SECONDS', .3)
    children = []
    create = asyncio.create_subprocess_exec
    async def tracked(*args, **kwargs):
        process = await create(*args, **kwargs)
        children.append(process)
        return process
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', tracked)
    async def run():
        task = asyncio.create_task(service.validate_pdf(pdf()))
        ticks = 0
        while not children:
            await asyncio.sleep(.001)
        if cancel:
            task.cancel()
        while not task.done():
            ticks += 1
            await asyncio.sleep(.005)
        with pytest.raises(asyncio.CancelledError if cancel else HTTPException) as error:
            await task
        if not cancel:
            assert error.value.status_code == 400
            assert ticks > 5  # event loop responsive during child validation
        assert children[0].returncode is not None
    asyncio.run(run())
    acquired = [service._slots.acquire(blocking=False) for _ in range(service.MAX_WORKERS)]
    try:
        assert all(acquired)
    finally:
        for success in acquired:
            if success:
                service._slots.release()


def test_concurrency_fails_fast_without_spawning(monkeypatch):
    for _ in range(service.MAX_WORKERS):
        assert service._slots.acquire(blocking=False)
    try:
        async def run():
            with pytest.raises(HTTPException) as error:
                await service.validate_pdf(pdf())
            assert error.value.status_code == 503
        asyncio.run(run())
    finally:
        for _ in range(service.MAX_WORKERS):
            service._slots.release()


def test_worker_environment_is_minimal(tmp_path, monkeypatch):
    path = tmp_path / 'check_env.py'
    path.write_text("import os, sys\nsys.stdin.buffer.read()\nassert 'CORPORATE_TEST_SECRET' not in os.environ\nassert 'PYTHONPATH' not in os.environ\nassert sys.flags.isolated\nprint('{\"ok\": true, \"isolation\": true}')\n")
    monkeypatch.setenv('CORPORATE_TEST_SECRET', 'test-only')
    monkeypatch.setattr(service, 'WORKER', path)
    asyncio.run(service.validate_pdf(pdf()))


def test_worker_memory_limit_is_enforced(tmp_path):
    # 64 MiB attempted allocation under a 48 MiB cap: small and bounded.
    # Test the actual platform primitive, not a mocked resource API.
    script = tmp_path / 'memory_probe.py'
    worker = Path(service.__file__).with_name('corporate_pdf_worker.py')
    script.write_text(f"""import importlib.util
spec = importlib.util.spec_from_file_location('worker', {str(worker)!r})
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)
w.MEMORY_BYTES = 48 * 1024 * 1024
w.install_limits()
try:
    b = bytearray(64 * 1024 * 1024)
except MemoryError:
    print('memory limit enforced')
else:
    raise AssertionError('allocation was not bounded')
""")
    result = subprocess.run([sys.executable, '-I', str(script)], capture_output=True, timeout=8)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == b'memory limit enforced'


def test_isolation_unavailable_fails_closed(tmp_path, monkeypatch):
    path = tmp_path / 'unsupported.py'
    worker = Path(service.__file__).with_name('corporate_pdf_worker.py')
    path.write_text(f"import runpy, sys\nsys.platform = 'unsupported'\nrunpy.run_path({str(worker)!r}, run_name='__main__')\n")
    monkeypatch.setattr(service, 'WORKER', path)
    with pytest.raises(HTTPException) as error:
        asyncio.run(service.validate_pdf(pdf()))
    assert error.value.status_code == 503


def test_scanned_image_pdf_is_accepted(harness):
    from PIL import Image
    output = io.BytesIO()
    Image.new('RGB', (320, 240), 'white').save(output, format='PDF')
    client, _, _ = harness
    response = upload(client, content=output.getvalue())
    assert response.status_code == 201, response.text
    assert client.get(response.json()['document']['view_url']).content == output.getvalue()
