"""Independent BlazeFace family. Never reused as the production detector."""
import cv2
import numpy as np
from shield.faces.detector import model_path
from shield.faces.policy import Face


class BlazeFaceJudge:
    family = 'BlazeFace'
    backend = 'mediapipe-tflite-cpu'

    def __init__(self, model=None):
        import mediapipe as mp
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision
        self.mp = mp
        options = vision.FaceDetectorOptions(
            base_options=python.BaseOptions(model_asset_path=str(model or model_path('blazeface-short-range-float16-1')),
                                            delegate=python.BaseOptions.Delegate.CPU),
            running_mode=vision.RunningMode.IMAGE,
            min_detection_confidence=0.5, min_suppression_threshold=0.3)
        self.detector = vision.FaceDetector.create_from_options(options)

    def detect(self, frame_bgr):
        image = self.mp.Image(image_format=self.mp.ImageFormat.SRGB,
                              data=np.ascontiguousarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)))
        result = self.detector.detect(image)
        faces = []
        h, w = frame_bgr.shape[:2]
        for detection in result.detections:
            b = detection.bounding_box
            box = (max(0., float(b.origin_x)), max(0., float(b.origin_y)),
                   min(float(w), float(b.origin_x + b.width)), min(float(h), float(b.origin_y + b.height)))
            faces.append(Face(box, float(detection.categories[0].score)))
        return tuple(faces)

    def close(self):
        self.detector.close()
