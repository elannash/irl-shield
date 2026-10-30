"""Small ctypes adapter to installed LGPL GStreamer, GstApp and GIRepository.

No Python extension ABI or copied third-party implementation is required. Public
C record offsets come from installed typelibs, never guessed from pointer size.
Only these transport operations are wrapped; engine code has no dependency here.
"""
from dataclasses import dataclass
import ctypes as C
from ctypes.util import find_library
import threading
import os
import time
from pathlib import Path

import numpy as np

P, I, U, Q, S = C.c_void_p, C.c_int, C.c_uint, C.c_uint64, C.c_size_t
SECOND = 1_000_000_000
NONE = 2**64 - 1
HANDOFF = C.CFUNCTYPE(None, P, P, P)


class _Error(C.Structure):
    _fields_ = [('domain', U), ('code', I), ('message', C.c_char_p)]


class Runtime:
    def __init__(self):
        registry = Path(__file__).resolve().parents[1] / '.tmp/gst/registry.bin'
        registry.parent.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault('GST_REGISTRY', str(registry))
        self.libs = {}
        for key in ('gstreamer-1.0', 'gstapp-1.0', 'gstvideo-1.0', 'gobject-2.0', 'glib-2.0', 'girepository-1.0'):
            path = find_library(key)
            if not path:
                candidate = Path('/opt/homebrew/lib') / f'lib{key}.dylib'
                if candidate.exists():
                    path = str(candidate)
            if not path:
                raise RuntimeError(f'Missing {key}; see docs/GSTREAMER.md')
            self.libs[key] = C.CDLL(path)
        self._bind('gst_init', None, [P, P])(None, None)
        self._bind('gst_parse_launch', P, [C.c_char_p, C.POINTER(P)])
        self._bind('gst_element_set_state', I, [P, I])
        self._bind('gst_element_get_state', I, [P, C.POINTER(I), C.POINTER(I), Q])
        self._bind('gst_bin_get_by_name', P, [P, C.c_char_p])
        self._bind('gst_element_get_bus', P, [P])
        self._bind('gst_event_new_eos', P, [])
        self._bind('gst_element_send_event', I, [P, P])
        self._bind('gst_bus_pop_filtered', P, [P, I])
        self._bind('gst_bus_timed_pop_filtered', P, [P, Q, I])
        self._bind('gst_message_parse_error', None, [P, C.POINTER(P), C.POINTER(P)])
        self._bind('gst_mini_object_unref', None, [P])
        self._bind('gst_object_unref', None, [P])
        self._bind('gst_sample_get_buffer', P, [P])
        self._bind('gst_sample_get_caps', P, [P])
        self._bind('gst_caps_get_structure', P, [P, U])
        self._bind('gst_structure_get_int', I, [P, C.c_char_p, C.POINTER(I)])
        self._bind('gst_buffer_get_size', S, [P])
        self._bind('gst_buffer_extract', S, [P, S, P, S])
        self._bind('gst_buffer_new_allocate', P, [P, S, P])
        self._bind('gst_buffer_fill', S, [P, S, P, S])
        self._bind('gst_buffer_map', I, [P, P, I])
        self._bind('gst_buffer_unmap', None, [P, P])
        self._bind('gst_app_sink_try_pull_sample', P, [P, Q], 'gstapp-1.0')
        self._bind('gst_app_sink_is_eos', I, [P], 'gstapp-1.0')
        self._bind('gst_app_src_push_buffer', I, [P, P], 'gstapp-1.0')
        self._bind('gst_app_src_end_of_stream', I, [P], 'gstapp-1.0')
        self._bind('gst_video_info_new', P, [], 'gstvideo-1.0')
        self._bind('gst_video_info_from_caps', I, [P, P], 'gstvideo-1.0')
        self._bind('gst_video_info_free', None, [P], 'gstvideo-1.0')
        self._bind('gst_buffer_get_video_meta', P, [P], 'gstvideo-1.0')
        self._bind('g_signal_connect_data', C.c_ulong, [P, C.c_char_p, HANDOFF, P, P, I], 'gobject-2.0')
        self._bind('g_error_free', None, [P], 'glib-2.0')
        self._bind('g_free', None, [P], 'glib-2.0')
        self.layouts = {}
        for namespace, name in [('Gst', 'Buffer'), ('Gst', 'MapInfo'), ('Gst', 'Message'), ('GstVideo', 'VideoInfo'), ('GstVideo', 'VideoMeta')]:
            self.layouts[name] = self._layout(namespace, name)
        for record, fields in {'Buffer': ('pts', 'dts', 'duration'), 'MapInfo': ('data', 'size'),
                               'VideoInfo': ('stride', 'offset'), 'VideoMeta': ('stride', 'offset')}.items():
            if not all(field in self.layouts[record][1] for field in fields):
                raise RuntimeError(f'Installed typelib lacks required {record} fields')

    def _bind(self, name, result, arguments, library='gstreamer-1.0'):
        fn = getattr(self.libs[library], name)
        fn.restype, fn.argtypes = result, arguments
        setattr(self, name, fn)
        return fn

    def _layout(self, namespace, name):
        lib = 'girepository-1.0'
        default = self._bind('g_irepository_get_default', P, [], lib)
        require = self._bind('g_irepository_require', P, [P, C.c_char_p, C.c_char_p, I, C.POINTER(P)], lib)
        find = self._bind('g_irepository_find_by_name', P, [P, C.c_char_p, C.c_char_p], lib)
        size = self._bind('g_struct_info_get_size', S, [P], lib)
        count = self._bind('g_struct_info_get_n_fields', I, [P], lib)
        field = self._bind('g_struct_info_get_field', P, [P, I], lib)
        field_name = self._bind('g_base_info_get_name', C.c_char_p, [P], lib)
        offset = self._bind('g_field_info_get_offset', I, [P], lib)
        unref = self._bind('g_base_info_unref', None, [P], lib)
        error = P()
        if not require(default(), namespace.encode(), b'1.0', 0, C.byref(error)):
            raise RuntimeError(self.error(error))
        info = find(default(), namespace.encode(), name.encode())
        if not info:
            raise RuntimeError(f'Missing typelib record {namespace}.{name}')
        try:
            fields = {}
            for index in range(count(info)):
                item = field(info, index)
                try:
                    fields[field_name(item).decode()] = offset(item)
                finally:
                    unref(item)
            return size(info), fields
        finally:
            unref(info)

    def error(self, pointer):
        if not pointer:
            return 'GStreamer failed without a diagnostic'
        message = C.cast(pointer, C.POINTER(_Error)).contents.message.decode(errors='replace')
        self.g_error_free(pointer)
        return message

    def value(self, pointer, record, field, kind=Q):
        return kind.from_address(pointer + self.layouts[record][1][field])


_runtime = None
_runtime_lock = threading.Lock()


def runtime():
    global _runtime
    with _runtime_lock:
        if _runtime is None:
            _runtime = Runtime()
    return _runtime


@dataclass(frozen=True)
class Sample:
    pts_ns: int
    duration_ns: int
    pixels: np.ndarray | None = None
    data: bytes | None = None
    copy_seconds: float = 0.
    copy_cpu_seconds: float = 0.


class Pipeline:
    def __init__(self, description):
        self.api = runtime()
        self.description = description
        self.elements = {}
        self.callbacks = []
        self.callback_error = None
        self.state = 'NULL'
        error = P()
        self.pipeline = self.api.gst_parse_launch(description.encode(), C.byref(error))
        if error or not self.pipeline:
            if self.pipeline:
                self.api.gst_object_unref(self.pipeline)
            raise RuntimeError(self.api.error(error))
        self.bus = self.api.gst_element_get_bus(self.pipeline)

    def element(self, name):
        if name not in self.elements:
            pointer = self.api.gst_bin_get_by_name(self.pipeline, name.encode())
            if not pointer:
                raise ValueError(f'Pipeline has no element {name}')
            self.elements[name] = pointer
        return self.elements[name]

    def start(self):
        try:
            if self.api.gst_element_set_state(self.pipeline, 4) == 0:
                self.check()
                raise RuntimeError('GStreamer could not enter PLAYING')
            self.state = 'PLAYING'
            return self
        except BaseException:
            self.close()
            raise

    def check(self):
        if self.callback_error is not None:
            raise RuntimeError(f'GStreamer handoff failed: {self.callback_error}') from self.callback_error
        message = self.api.gst_bus_pop_filtered(self.bus, 2)  # GST_MESSAGE_ERROR
        if message:
            error, debug = P(), P()
            self.api.gst_message_parse_error(message, C.byref(error), C.byref(debug))
            try:
                message_text = self.api.error(error)
                details = C.cast(debug, C.c_char_p).value.decode(errors='replace') if debug else ''
                raise RuntimeError(f'{message_text}: {details}')
            finally:
                self.api.g_free(debug)
                self.api.gst_mini_object_unref(message)

    def pull(self, name, timeout=.1, *, video=True):
        self.check()
        sample = self.api.gst_app_sink_try_pull_sample(self.element(name), round(timeout * SECOND))
        if not sample:
            self.check()
            return None
        api = self.api
        try:
            buffer = api.gst_sample_get_buffer(sample)
            pts = api.value(buffer, 'Buffer', 'pts').value
            duration = api.value(buffer, 'Buffer', 'duration').value
            if pts == NONE:
                raise ValueError('GStreamer sample has no source PTS')
            if not video:
                size = api.gst_buffer_get_size(buffer)
                data = C.create_string_buffer(size)
                if api.gst_buffer_extract(buffer, 0, data, size) != size:
                    raise RuntimeError('Short audio buffer extraction')
                return Sample(pts, duration, data=data.raw)
            caps = api.gst_sample_get_caps(sample)
            structure = api.gst_caps_get_structure(caps, 0)
            width, height = I(), I()
            if not (api.gst_structure_get_int(structure, b'width', C.byref(width)) and
                    api.gst_structure_get_int(structure, b'height', C.byref(height))):
                raise ValueError('Video dimensions unavailable')
            info = api.gst_video_info_new()
            try:
                if not api.gst_video_info_from_caps(info, caps):
                    raise ValueError('Video caps unavailable')
                meta = api.gst_buffer_get_video_meta(buffer)
                layout, record = (meta, 'VideoMeta') if meta else (info, 'VideoInfo')
                stride = api.value(layout, record, 'stride', I).value
                offset = api.value(layout, record, 'offset', S).value
                mapping = C.create_string_buffer(api.layouts['MapInfo'][0])
                if not api.gst_buffer_map(buffer, mapping, 1):
                    raise RuntimeError('Cannot map video buffer for CPU engine')
                try:
                    address = C.addressof(mapping)
                    data = api.value(address, 'MapInfo', 'data', P).value
                    size = api.value(address, 'MapInfo', 'size', S).value
                    if stride < width.value * 3 or offset + (height.value - 1) * stride + width.value * 3 > size:
                        raise ValueError('Invalid BGR row stride or allocation')
                    memory = (C.c_ubyte * size).from_address(data)
                    began, cpu = time.monotonic(), time.thread_time()
                    pixels = np.ndarray((height.value, width.value, 3), np.uint8, memory,
                                        offset=offset, strides=(stride, 3, 1)).copy()
                    copied, copy_cpu = time.monotonic() - began, time.thread_time() - cpu
                finally:
                    api.gst_buffer_unmap(buffer, mapping)
                return Sample(pts, duration, pixels=pixels, copy_seconds=copied, copy_cpu_seconds=copy_cpu)
            finally:
                api.gst_video_info_free(info)
        finally:
            api.gst_mini_object_unref(sample)

    def eos(self, name):
        self.check()
        return bool(self.api.gst_app_sink_is_eos(self.element(name)))

    def push(self, name, data, pts_ns, duration_ns):
        self.check()
        array = np.ascontiguousarray(data) if isinstance(data, np.ndarray) else np.frombuffer(data, np.uint8)
        buffer = self.api.gst_buffer_new_allocate(None, array.nbytes, None)
        if not buffer:
            raise MemoryError('Cannot allocate appsrc buffer')
        if self.api.gst_buffer_fill(buffer, 0, array.ctypes.data, array.nbytes) != array.nbytes:
            self.api.gst_mini_object_unref(buffer)
            raise RuntimeError('Short appsrc buffer fill')
        for field, value in [('pts', pts_ns), ('dts', NONE), ('duration', duration_ns)]:
            self.api.value(buffer, 'Buffer', field).value = value
        # push_buffer takes ownership, including on a non-OK flow return.
        flow = self.api.gst_app_src_push_buffer(self.element(name), buffer)
        if flow != 0:
            self.check()
            raise RuntimeError(f'GStreamer appsrc {name} flow={flow}')

    def on_buffer(self, name, callback):
        def receive(element, buffer, user_data):
            try:
                callback(self.api.value(buffer, 'Buffer', 'pts').value)
            except Exception as error:
                self.callback_error = error
        wrapped = HANDOFF(receive)
        self.callbacks.append(wrapped)
        self.api.g_signal_connect_data(self.element(name), b'handoff', wrapped, None, None, 0)

    def signal_eos(self):
        self.check()
        if not self.api.gst_element_send_event(self.pipeline, self.api.gst_event_new_eos()):
            raise RuntimeError('GStreamer source refused end-of-stream')

    def end(self, names, timeout=20.):
        for name in names:
            if self.api.gst_app_src_end_of_stream(self.element(name)) != 0:
                self.check()
                raise RuntimeError(f'Could not end appsrc {name}')
        message = self.api.gst_bus_timed_pop_filtered(self.bus, round(timeout * SECOND), 1 | 2)
        if not message:
            raise TimeoutError('GStreamer egress did not drain')
        # Reuse the error parser; EOS has no GError. Check other queued errors too.
        error, debug = P(), P()
        # Message type is a public field, resolved from the installed typelib.
        kind = self.api.value(message, 'Message', 'type', I).value
        try:
            if kind == 2:
                self.api.gst_message_parse_error(message, C.byref(error), C.byref(debug))
                message_text = self.api.error(error)
                details = C.cast(debug, C.c_char_p).value.decode(errors='replace') if debug else ''
                raise RuntimeError(f'{message_text}: {details}')
        finally:
            self.api.g_free(debug)
            self.api.gst_mini_object_unref(message)
        self.check()

    def close(self):
        if not self.pipeline:
            return
        self.api.gst_element_set_state(self.pipeline, 1)
        current, pending = I(), I()
        result = self.api.gst_element_get_state(self.pipeline, C.byref(current), C.byref(pending), 5 * SECOND)
        if result == 0 or current.value != 1:
            raise RuntimeError('GStreamer pipeline did not stop in NULL')
        self.state = 'NULL'
        for element in self.elements.values():
            self.api.gst_object_unref(element)
        self.elements.clear()
        self.api.gst_object_unref(self.bus)
        self.api.gst_object_unref(self.pipeline)
        self.pipeline = None
        self.callbacks.clear()

    def __enter__(self):
        return self.start()

    def __exit__(self, *exception):
        self.close()
