"""Global camera motion; OpenCV operations are Apache-2.0 licensed.

OpenCV license: https://github.com/opencv/opencv/blob/4.11.0/LICENSE
"""
import cv2
import numpy as np
import threading
import time
import math
from collections import deque


class MotionWorker:
    def __init__(self,history,capacity=120,clock=time.monotonic):
        if capacity<1:
            raise ValueError('Motion queue must have positive capacity')
        self.history=history
        self.clock=clock
        self.capacity=capacity
        self.condition=threading.Condition()
        self.pending=deque()
        self.completed_at={}
        self.history_capacity=getattr(history,'max_frames',max(120,capacity))
        self.stopping=False
        self.completed=self.dropped=0
        self.errors=deque(maxlen=64)
        self.wall_seconds=deque(maxlen=4096)
        self.cpu_seconds=deque(maxlen=4096)
        self.thread=threading.Thread(target=self._run,name='shield-motion',daemon=True)
        self.thread.start()
    def add(self,index,pixels,*,generation=None):
        with self.condition:
            if self.stopping:
                raise RuntimeError('Motion worker is closed')
            if len(self.pending)>=self.capacity:
                self.pending.popleft()
                self.dropped+=1
            self.pending.append((index,pixels,generation))
            self.condition.notify()
    def _run(self):
        while True:
            with self.condition:
                while not self.stopping and not self.pending:
                    self.condition.wait()
                if self.stopping:
                    return
                index,pixels,generation=self.pending.popleft()
            wall,cpu=time.monotonic(),time.thread_time()
            try:
                if generation is None:
                    self.history.add(index,pixels)
                else:
                    self.history.add(index,pixels,generation=generation)
                with self.condition:
                    self.completed_at[index]=self.clock()
                    while len(self.completed_at)>self.history_capacity:
                        self.completed_at.pop(next(iter(self.completed_at)))
                    self.completed+=1
            except Exception as error:
                self.errors.append(f'{type(error).__name__}: {error}')
            self.wall_seconds.append(time.monotonic()-wall)
            self.cpu_seconds.append(time.thread_time()-cpu)
    def project(self,quad,source,target,deadline=None):
        projected=self.project_many([quad],source,target,deadline)
        return None if projected is None else projected[0]
    def project_many(self,quads,source,target,deadline=None):
        """Accept a receipt only if every motion frame finished by its deadline."""
        if deadline is not None:
            if not math.isfinite(deadline) or abs(source-target)>=self.history_capacity:
                return None
            with self.condition:
                for index in range(min(source,target),max(source,target)+1):
                    at=self.completed_at.get(index)
                    if at is None or not math.isfinite(at) or at>deadline:
                        return None
        return self.history.project_many(quads,source,target)
    def close(self):
        with self.condition:
            self.stopping=True
            self.pending.clear()
            self.condition.notify_all()
        self.thread.join(timeout=5)
        if self.thread.is_alive():
            raise RuntimeError('Motion worker did not stop')
    @property
    def stats(self):
        return {'completed':self.completed,'dropped':self.dropped,'errors':list(self.errors),
                'wall_seconds':list(self.wall_seconds),'thread_cpu_seconds':list(self.cpu_seconds),
                'running':self.thread.is_alive()}


class MotionHistory:
    """Project ordered quads between cached frames; one producer calls add.

    Frame indices increase strictly. Quads use each original frame's pixel
    coordinates; projections retain vertex order and may extend offscreen.
    Projection reads synchronize with short commits; feature/motion estimation
    does not hold the projection lock. Missing motion returns None.
    Only max_frames grayscale/feature records and their incoming transforms
    are retained. Confidence is a heuristic fit score, not a probability.
    """

    def __init__(self, max_frames=120, analysis_width=320, mode='orb', phase_min_response=.5,
                 max_projection_frames=None):
        if not isinstance(max_frames, int) or max_frames < 1:
            raise ValueError('max_frames must be a positive integer')
        if not isinstance(analysis_width, int) or analysis_width < 32:
            raise ValueError('analysis_width must be an integer at least32')
        if mode not in {'orb', 'phase', 'flow'}:
            raise ValueError("mode must be 'orb', 'phase' or 'flow'")
        if mode == 'flow' and (type(max_projection_frames) is not int or max_projection_frames < 0):
            raise ValueError('Optical flow requires a nonnegative integer projection horizon')
        if not math.isfinite(phase_min_response) or not 0 <= phase_min_response <= 1:
            raise ValueError('phase_min_response must be finite and between zero and one')
        self.phase_min_response = phase_min_response
        self.max_frames = max_frames
        self.analysis_width = analysis_width
        self.mode = mode
        self.max_projection_frames = max_projection_frames
        self._orb = cv2.ORB_create(nfeatures=600, nlevels=5, edgeThreshold=15, fastThreshold=10) if mode == 'orb' else None
        self._matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
        self._frames = {}
        self._transforms = {}
        self._diagnostics = {}
        self._projection_cache = {}
        self._state_lock=threading.RLock()
        self._generation = None

    def add(self, index, frame_bgr, *, generation=0):
        if self.mode == 'flow' and (type(generation) is not int or generation < 0):
            raise ValueError('Ingest generation must be a nonnegative integer')
        if not isinstance(index, int):
            raise ValueError('Frame index must be an integer')
        if self._frames and index <= next(reversed(self._frames)):
            raise ValueError('Frame indices must increase strictly')
        if not isinstance(frame_bgr, np.ndarray) or frame_bgr.dtype != np.uint8 or frame_bgr.ndim != 3 or frame_bgr.shape[2] != 3:
            raise ValueError('Expected an H×W×3 uint8 BGR frame')
        height, width = frame_bgr.shape[:2]
        if min(height, width) < 8:
            raise ValueError('Frame sides must be at least8 pixels')
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        small_width = min(width, self.analysis_width)
        small_height = max(2, round(height * small_width / width))
        if (small_height, small_width) != gray.shape:
            gray = cv2.resize(gray, (small_width, small_height), interpolation=cv2.INTER_AREA)
        scale = np.diag([small_width / width, small_height / height, 1.0])
        features = self._orb.detectAndCompute(gray, None) if self._orb is not None else ([], None)
        diagnostic = {'valid': False, 'confidence': 0.0, 'burst': False, 'reason': 'first-frame'}
        transform = None
        changed_generation = self.mode == 'flow' and self._generation != generation
        if self._frames and changed_generation:
            diagnostic = {'valid': False, 'confidence': 0.0, 'burst': True, 'reason': 'ingest-generation-change'}
        elif self._frames and index - 1 in self._frames:
            previous_gray, previous_scale, previous_features = self._frames[next(reversed(self._frames))]
            textured = min(float(previous_gray.std()), float(gray.std())) >= 3
            diagnostic = {'valid': False, 'confidence': 0.0, 'burst': textured, 'reason': 'unreliable-motion' if textured else 'low-texture'}
            analysis_transform, confidence, reason = None, 0.0, 'orb'
            if textured:
                if np.array_equal(previous_gray, gray):
                    analysis_transform, confidence, reason = np.eye(3), 1.0, 'stationary'
                else:
                    if self.mode == 'flow':
                        analysis_transform, confidence = self._flow(previous_gray, gray)
                        reason = 'flow'
                    else:
                        analysis_transform, confidence = self._homography(previous_features, features, previous_gray.shape)
                if self.mode != 'flow' and analysis_transform is None and previous_gray.shape == gray.shape:
                    window = cv2.createHanningWindow((small_width, small_height), cv2.CV_32F)
                    (dx, dy), response = cv2.phaseCorrelate(previous_gray.astype(np.float32), gray.astype(np.float32), window)
                    if response >= self.phase_min_response and np.hypot(dx, dy) <= min(gray.shape) * .25:
                        analysis_transform = np.array([[1, 0, dx], [0, 1, dy], [0, 0, 1]], dtype=float)
                        confidence = float(np.clip(response, 0, 1))
                        reason = 'phase'
            if analysis_transform is not None:
                error = self._alignment_error(previous_gray, gray, analysis_transform)
                if error <= .6:
                    transform = np.linalg.inv(scale) @ analysis_transform @ previous_scale
                    shift = np.linalg.norm(analysis_transform[:2, 2]) / max(gray.shape)
                    diagnostic = {'valid': True, 'confidence': confidence * max(0.0, 1 - error), 'burst': bool(shift > .08), 'reason': reason}
        elif self._frames:
            diagnostic = {'valid': False, 'confidence': 0.0, 'burst': True, 'reason': 'nonconsecutive-frame'}
        with self._state_lock:
            self._generation = generation
            self._frames[index] = gray, scale, features
            self._transforms[index] = transform
            self._diagnostics[index] = diagnostic
            self._projection_cache.clear()
            while len(self._frames) > self.max_frames:
                oldest = next(iter(self._frames))
                del self._frames[oldest]
                del self._transforms[oldest]
                del self._diagnostics[oldest]

    def _homography(self, previous, current, previous_shape):
        previous_points, previous_descriptors = previous
        current_points, current_descriptors = current
        if previous_descriptors is None or current_descriptors is None or len(current_descriptors) < 2:
            return None, 0.0
        pairs = self._matcher.knnMatch(previous_descriptors, current_descriptors, k=2)
        matches = [pair[0] for pair in pairs if len(pair) == 2 and pair[0].distance < .75 * pair[1].distance]
        if len(matches) < 12:
            return None, 0.0
        source = np.float32([previous_points[match.queryIdx].pt for match in matches])
        target = np.float32([current_points[match.trainIdx].pt for match in matches])
        matrix, mask = cv2.findHomography(source, target, cv2.RANSAC, 2.5, maxIters=1000, confidence=.995)
        if matrix is None or mask is None or int(mask.sum()) < 12 or float(mask.mean()) < .6:
            return None, 0.0
        inliers = source[mask.ravel().astype(bool)]
        if cv2.contourArea(cv2.convexHull(inliers)) < .03 * np.prod(previous_shape):
            return None, 0.0
        return matrix, float(mask.mean()) * min(1.0, int(mask.sum()) / 30)

    def _flow(self, previous, current):
        if previous.shape != current.shape:
            return None, 0.0
        source = cv2.goodFeaturesToTrack(previous, maxCorners=400, qualityLevel=.01,
                                        minDistance=6, blockSize=7)
        if source is None or len(source) < 12:
            return None, 0.0
        options = dict(winSize=(21, 21), maxLevel=3,
                       criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, .01))
        target, forward, _ = cv2.calcOpticalFlowPyrLK(previous, current, source, None, **options)
        if target is None or forward is None or not np.isfinite(target).all():
            return None, 0.0
        returned, backward, _ = cv2.calcOpticalFlowPyrLK(current, previous, target, None, **options)
        if returned is None or backward is None:
            return None, 0.0
        a, b, c = source[:, 0], target[:, 0], returned[:, 0]
        height, width = current.shape
        consistent = ((forward.ravel() == 1) & (backward.ravel() == 1)
                      & np.isfinite(c).all(axis=1) & (np.linalg.norm(c - a, axis=1) <= 1.)
                      & (b[:, 0] >= 0) & (b[:, 0] < width)
                      & (b[:, 1] >= 0) & (b[:, 1] < height))
        if int(consistent.sum()) < 12 or float(consistent.mean()) < .6:
            return None, 0.0
        a, b = a[consistent], b[consistent]
        matrix, mask = cv2.findHomography(a, b, cv2.RANSAC, 2., maxIters=1000, confidence=.995)
        if matrix is None or mask is None or int(mask.sum()) < 12 or float(mask.mean()) < .6:
            return None, 0.0
        inliers = mask.ravel().astype(bool)
        if any(cv2.contourArea(cv2.convexHull(points[inliers])) < .03 * previous.size for points in (a, b)):
            return None, 0.0
        return matrix, float(consistent.mean() * mask.mean())

    def _alignment_error(self, previous, current, matrix):
        if not np.isfinite(matrix).all() or abs(matrix[2, 2]) < 1e-8:
            return float('inf')
        height, width = previous.shape
        corners = np.float32([[[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]]])
        mapped = cv2.perspectiveTransform(corners, matrix)[0]
        area = cv2.contourArea(mapped, oriented=True)
        if not np.isfinite(mapped).all() or not cv2.isContourConvex(mapped) or not .4 * width * height <= area <= 2.5 * width * height:
            return float('inf')
        target_size = current.shape[1], current.shape[0]
        valid = cv2.warpPerspective(np.ones(previous.shape, np.uint8), matrix, target_size, flags=cv2.INTER_NEAREST) > 0
        if float(valid.mean()) < .4:
            return float('inf')
        warped = cv2.warpPerspective(previous, matrix, target_size)
        residual = np.abs(warped[valid].astype(np.float32) - current[valid]).mean()
        return float(residual / max(8.0, float(previous.std()), float(current.std())))

    def project(self, quad, source_index, target_index, deadline=None):
        projected = self.project_many([quad], source_index, target_index, deadline)
        return None if projected is None else projected[0]

    def project_many(self, quads, source_index, target_index, deadline=None):
        """Project one receipt atomically; empty receipts still require its motion path.

        Synchronous history uses source indices, ignoring wall-clock deadlines.
        Worker adapters enforce motion completion before calling this method.
        """
        points = np.asarray(list(quads), dtype=float)
        if ((len(points) and points.shape[1:] != (4, 2)) or not np.isfinite(points).all()):
            raise ValueError('Expected four finite quad vertices')
        with self._state_lock:
            if self.mode == 'flow' and abs(source_index - target_index) > self.max_projection_frames:
                return None
            if source_index not in self._frames or target_index not in self._frames:
                return None
            key = (source_index, target_index)
            if key not in self._projection_cache:
                self._projection_cache[key] = self._between(source_index, target_index)
            transform = self._projection_cache[key]
            if transform is None or not np.isfinite(transform).all():
                return None
            if not len(points):
                return []
            homogeneous = np.empty((*points.shape[:2], 3), dtype=float)
            homogeneous[:, :, :2] = points
            homogeneous[:, :, 2] = 1
            projected = homogeneous @ transform.T
            denominators = projected[:, :, 2]
            if np.any(np.abs(denominators) < 1e-8) or not np.isfinite(projected).all():
                return None
            if not (np.all(denominators > 0, axis=1) | np.all(denominators < 0, axis=1)).all():
                return None
            return (projected[:, :, :2] / denominators[:, :, None]).tolist()

    def _between(self,source_index,target_index):
        # All clues from one detection share this camera transform.
        transform = np.eye(3)
        for index in range(min(source_index, target_index) + 1, max(source_index, target_index) + 1):
            step = self._transforms.get(index)
            if step is None:
                return None
            transform = step @ transform
        if target_index < source_index:
            try:
                transform = np.linalg.inv(transform)
            except np.linalg.LinAlgError:
                return None
        return transform

    def diagnostics(self, index):
        """Return a copy of the incoming-motion verdict; the first frame has no estimate."""
        return dict(self._diagnostics.get(index, {'valid': False, 'confidence': 0.0, 'burst': False, 'reason': 'missing-frame'}))
