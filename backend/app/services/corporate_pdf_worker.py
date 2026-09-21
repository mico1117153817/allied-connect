"""One-shot, secret-free PDF validator. Run only as an isolated subprocess.

Limits are installed BEFORE importing pypdf or reading untrusted stdin. A limit
installation failure emits failure, never falls back to in-process validation.
"""
import sys
import os
import json

MEMORY_BYTES = 512 * 1024 * 1024
CPU_SECONDS = 5
MAX_INPUT = 20 * 1024 * 1024
MAX_PAGES = 250
MAX_PAGE_DECODED = 8 * 1024 * 1024
MAX_TOTAL_DECODED = 32 * 1024 * 1024
MAX_OBJECTS = 50000
_job = None


def install_limits():
    global _job
    if sys.platform == 'linux':
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (MEMORY_BYTES, MEMORY_BYTES))
        resource.setrlimit(resource.RLIMIT_CPU, (CPU_SECONDS, CPU_SECONDS))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    elif sys.platform == 'win32':
        # A self-assigned Job Object is effective before the input is read.
        # Nested jobs are supported by Windows 10; incompatible host jobs fail
        # closed. No pywin32 dependency or unbounded Windows fallback.
        import ctypes as c
        from ctypes import wintypes as w
        class Basic(c.Structure):
            _fields_ = [('process_time', c.c_int64), ('job_time', c.c_int64),
                        ('flags', w.DWORD), ('min_ws', c.c_size_t), ('max_ws', c.c_size_t),
                        ('active', w.DWORD), ('affinity', c.c_size_t), ('priority', w.DWORD), ('scheduling', w.DWORD)]
        class IO(c.Structure):
            _fields_ = [(name, c.c_uint64) for name in ('read_ops', 'write_ops', 'other_ops', 'read_bytes', 'write_bytes', 'other_bytes')]
        class Extended(c.Structure):
            _fields_ = [('basic', Basic), ('io', IO), ('process_memory', c.c_size_t),
                        ('job_memory', c.c_size_t), ('peak_process', c.c_size_t), ('peak_job', c.c_size_t)]
        kernel = c.WinDLL('kernel32', use_last_error=True)
        kernel.CreateJobObjectW.argtypes = [c.c_void_p, w.LPCWSTR]
        kernel.CreateJobObjectW.restype = w.HANDLE
        kernel.SetInformationJobObject.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD]
        kernel.SetInformationJobObject.restype = w.BOOL
        kernel.GetCurrentProcess.restype = w.HANDLE
        kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
        kernel.AssignProcessToJobObject.restype = w.BOOL
        _job = kernel.CreateJobObjectW(None, None)
        if not _job:
            raise OSError(c.get_last_error())
        limits = Extended()
        # PROCESS_TIME | ACTIVE_PROCESS | PROCESS_MEMORY | KILL_ON_JOB_CLOSE
        limits.basic.flags = 0x2 | 0x8 | 0x100 | 0x2000
        limits.basic.process_time = CPU_SECONDS * 10_000_000
        limits.basic.active = 1
        limits.process_memory = MEMORY_BYTES
        if not kernel.SetInformationJobObject(_job, 9, c.byref(limits), c.sizeof(limits)):
            raise OSError(c.get_last_error())
        if not kernel.AssignProcessToJobObject(_job, kernel.GetCurrentProcess()):
            raise OSError(c.get_last_error())
    else:
        raise RuntimeError('PDF isolation is supported only on Linux and Windows')


def validate(content):
    import io
    from pypdf import PdfReader
    from pypdf.generic import DictionaryObject, ArrayObject, StreamObject, IndirectObject
    if not content.startswith(b'%PDF-') or len(content) > MAX_INPUT:
        raise ValueError('input')
    reader = PdfReader(io.BytesIO(content), strict=True)
    if reader.is_encrypted or not 0 < len(reader.pages) <= MAX_PAGES:
        raise ValueError('pages')
    total = 0
    objects = 0
    for page in reader.pages:
        # Traverse page streams/resources (including scanned image XObjects),
        # not just text content. Count shared streams again per page to bound
        # work; avoid parent/page-tree cycles. OS limits cover any one decode
        # before Python can measure it, and malformed object graph traversal.
        decoded = 0
        seen = set()
        stack = [page]
        while stack:
            obj = stack.pop()
            if isinstance(obj, IndirectObject):
                key = ('ref', obj.idnum, obj.generation)
                if key in seen:
                    continue
                seen.add(key)
                obj = obj.get_object()
            key = ('obj', id(obj))
            if key in seen:
                continue
            seen.add(key)
            objects += 1
            if objects > MAX_OBJECTS:
                raise ValueError('complexity')
            if isinstance(obj, StreamObject):
                size = len(obj.get_data())
                decoded += size
                total += size
                if decoded > MAX_PAGE_DECODED or total > MAX_TOTAL_DECODED:
                    raise ValueError('decoded budget')
            if isinstance(obj, DictionaryObject):
                stack.extend(value for key, value in obj.items() if key not in ('/Parent', '/P'))
            elif isinstance(obj, ArrayObject):
                stack.extend(obj)
        page.get_object()
        contents = page.get_contents()
        if contents is not None:
            contents.get_data()


if __name__ == '__main__':
    try:
        install_limits()
    except Exception:
        print(json.dumps({'ok': False, 'isolation': False}))
        sys.exit(1)
    try:
        validate(sys.stdin.buffer.read(MAX_INPUT + 1))
    except Exception:
        print(json.dumps({'ok': False, 'isolation': True}))
        sys.exit(1)
    print(json.dumps({'ok': True, 'isolation': True}))
