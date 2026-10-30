"""Lazy CUDA12 event adapter; constructing it is GPU work and requires queue release.

Uses the installed NVIDIA CUDA Runtime under its proprietary CUDA Toolkit EULA.
No wheel/library is installed, copied or redistributed. ABI source: installed
nvidia/cuda_runtime/include/{cuda_runtime_api.h,driver_types.h}.
"""
import ctypes
from pathlib import Path


class CudaEvents:
    def __init__(self, library, *, device=0):
        self.device = device
        self.library_path = str(Path(library).resolve())
        self.lib = ctypes.CDLL(self.library_path)
        ptr = ctypes.c_void_p
        signatures = {
            'cudaSetDevice': [ctypes.c_int],
            'cudaRuntimeGetVersion': [ctypes.POINTER(ctypes.c_int)],
            'cudaDeviceGetAttribute': [ctypes.POINTER(ctypes.c_int), ctypes.c_int, ctypes.c_int],
            'cudaStreamCreateWithFlags': [ctypes.POINTER(ptr), ctypes.c_uint],
            'cudaStreamSynchronize': [ptr], 'cudaStreamDestroy': [ptr],
            'cudaEventCreate': [ctypes.POINTER(ptr)], 'cudaEventDestroy': [ptr],
            'cudaEventRecord': [ptr, ptr], 'cudaEventSynchronize': [ptr],
            'cudaEventElapsedTime': [ctypes.POINTER(ctypes.c_float), ptr, ptr],
        }
        for name, arguments in signatures.items():
            function = getattr(self.lib, name)
            function.argtypes, function.restype = arguments, ctypes.c_int
        self.stream = ptr()
        self.events = {'start': ptr(), 'end': ptr()}
        try:
            self.call('cudaSetDevice', device)
            version = ctypes.c_int()
            self.call('cudaRuntimeGetVersion', ctypes.byref(version))
            capability = []
            for attribute in (75, 76):
                value = ctypes.c_int()
                self.call('cudaDeviceGetAttribute', ctypes.byref(value), attribute, device)
                capability.append(value.value)
            if version.value // 1000 != 12 or capability != [6, 1]:
                raise RuntimeError('Q2 measurement requires CUDA12 and Pascal compute capability6.1')
            self.runtime_version = version.value
            self.capability = capability
            self.call('cudaStreamCreateWithFlags', ctypes.byref(self.stream), 1)
            for event in self.events.values():
                self.call('cudaEventCreate', ctypes.byref(event))
        except BaseException:
            self.close()
            raise

    def call(self, name, *args):
        code = getattr(self.lib, name)(*args)
        if code:
            raise RuntimeError(f'{name} failed with CUDA status {code}')

    def prepare(self):
        self.call('cudaSetDevice', self.device)
        self.call('cudaStreamSynchronize', self.stream)

    def record(self, name):
        self.call('cudaEventRecord', self.events[name], self.stream)

    def wait(self):
        self.call('cudaEventSynchronize', self.events['end'])

    def elapsed_ms(self):
        elapsed = ctypes.c_float()
        self.call('cudaEventElapsedTime', ctypes.byref(elapsed), self.events['start'], self.events['end'])
        return float(elapsed.value)

    def close(self):
        errors = []
        for value in [*self.events.values(), self.stream]:
            if value.value is None:
                continue
            function = 'cudaStreamDestroy' if value is self.stream else 'cudaEventDestroy'
            try:
                if value is self.stream:
                    self.call('cudaStreamSynchronize', value)
                self.call(function, value)
                value.value = None
            except Exception as error:
                errors.append(error)
        if errors:
            raise ExceptionGroup('CUDA event/stream cleanup failed', errors)
