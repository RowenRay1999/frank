"""
Frank 人脸质量门控

对每帧检测到的人脸进行质量评估，低质量帧的 embedding 不参与身份匹配
（但仍可用于跟踪器的运动/外观匹配）
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger('frank.quality_gate')


@dataclass
class FaceQualityResult:
    """人脸质量评估结果"""
    passed: bool = True
    # 各项指标
    det_score: float = 0.0
    face_size_ratio: float = 0.0        # bbox 面积 / 帧面积
    yaw_deg: float = 0.0                # 偏航角
    pitch_deg: float = 0.0              # 俯仰角
    roll_deg: float = 0.0               # 翻滚角
    blur_score: float = 0.0             # Laplacian 方差
    occlusion_ratio: float = 0.0        # 遮挡比例 (0-1)
    visible_landmarks: int = 0           # 可见 landmarks 数
    total_landmarks: int = 68            # 总 landmarks 数
    # 失败原因
    failure_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            'passed': self.passed,
            'det_score': round(self.det_score, 3),
            'face_size_ratio': round(self.face_size_ratio, 3),
            'yaw_deg': round(self.yaw_deg, 1),
            'pitch_deg': round(self.pitch_deg, 1),
            'blur_score': round(self.blur_score, 1),
            'occlusion_ratio': round(self.occlusion_ratio, 2),
            'failure_reasons': self.failure_reasons,
        }


class QualityGate:
    """人脸质量门控

    评估维度：
    1. 检测置信度 (det_score)
    2. 人脸大小 (bbox 面积占比)
    3. 人脸角度 (pitch/yaw/roll from landmarks)
    4. 模糊度 (Laplacian 方差)
    5. 遮挡比例 (landmarks 可见率)
    """

    # 阈值
    MIN_DET_SCORE = 0.5
    MIN_FACE_SIZE_RATIO = 0.05      # 人脸占帧面积至少 5%
    MAX_YAW_DEG = 45.0
    MAX_PITCH_DEG = 30.0
    MAX_ROLL_DEG = 45.0
    MIN_BLUR_SCORE = 100.0          # Laplacian 方差
    MIN_LANDMARK_RATIO = 0.7         # 至少 70% landmarks 可见

    def __init__(self):
        pass

    def evaluate(self,
                 face_info: dict,
                 frame: np.ndarray | None = None,
                 frame_width: int = 640,
                 frame_height: int = 480) -> FaceQualityResult:
        """评估单个人脸的质量

        Args:
            face_info: 来自 camera_pipeline 的 face dict
                {bbox, confidence, embedding, landmarks}
            frame: 原始帧（用于计算模糊度），可选
            frame_width: 帧宽度
            frame_height: 帧高度

        Returns:
            FaceQualityResult
        """
        result = FaceQualityResult()

        bbox = face_info.get('bbox', {})
        det_score = face_info.get('confidence', 0.0)
        landmarks = face_info.get('landmarks', [])

        # 1. 检测置信度
        result.det_score = det_score
        if det_score < self.MIN_DET_SCORE:
            result.passed = False
            result.failure_reasons.append(f'det_score_low({det_score:.2f}<{self.MIN_DET_SCORE})')

        # 2. 人脸大小
        face_w = bbox.get('width', 0) * frame_width
        face_h = bbox.get('height', 0) * frame_height
        face_area = face_w * face_h
        frame_area = frame_width * frame_height
        result.face_size_ratio = face_area / frame_area if frame_area > 0 else 0
        if result.face_size_ratio < self.MIN_FACE_SIZE_RATIO:
            result.passed = False
            result.failure_reasons.append(f'face_too_small({result.face_size_ratio:.3f}<{self.MIN_FACE_SIZE_RATIO})')

        # 3. 人脸角度（从 landmarks 估算）
        if landmarks and len(landmarks) >= 5:
            yaw, pitch, roll = self._estimate_head_pose(landmarks, frame_width, frame_height)
            result.yaw_deg = yaw
            result.pitch_deg = pitch
            result.roll_deg = roll
            if abs(yaw) > self.MAX_YAW_DEG:
                result.passed = False
                result.failure_reasons.append(f'yaw_too_large({yaw:.1f}>{self.MAX_YAW_DEG})')
            if abs(pitch) > self.MAX_PITCH_DEG:
                result.passed = False
                result.failure_reasons.append(f'pitch_too_large({pitch:.1f}>{self.MAX_PITCH_DEG})')

        # 4. 模糊度（从人脸 ROI 计算 Laplacian 方差）
        if frame is not None:
            blur = self._compute_blur(frame, bbox, frame_width, frame_height)
            result.blur_score = blur
            if blur < self.MIN_BLUR_SCORE:
                result.passed = False
                result.failure_reasons.append(f'blurry({blur:.1f}<{self.MIN_BLUR_SCORE})')

        # 5. 遮挡比例（从 landmarks 数量判断）
        result.total_landmarks = 68
        result.visible_landmarks = len(landmarks) if landmarks else 0
        if landmarks:
            result.occlusion_ratio = 1.0 - (len(landmarks) / result.total_landmarks)
            if result.occlusion_ratio > (1.0 - self.MIN_LANDMARK_RATIO):
                result.passed = False
                result.failure_reasons.append(
                    f'occluded({result.occlusion_ratio:.2f}>{(1.0 - self.MIN_LANDMARK_RATIO):.2f})'
                )

        return result

    def _estimate_head_pose(self, landmarks: list, width: int, height: int) -> tuple[float, float, float]:
        """从 2D landmarks 估算头部姿态角 (yaw, pitch, roll) in degrees"""
        if len(landmarks) < 5:
            return 0.0, 0.0, 0.0

        try:
            pts = []
            for lm in landmarks:
                if isinstance(lm, dict):
                    pts.append([lm.get('x', 0) * width, lm.get('y', 0) * height])
                elif hasattr(lm, 'x'):
                    pts.append([lm.x * width, lm.y * height])
                else:
                    pts.append([lm[0] * width, lm[1] * height])
            pts = np.array(pts, dtype=np.float64)

            n_pts = len(pts)
            left_eye = pts[min(33, n_pts - 1)]
            right_eye = pts[min(87, n_pts - 1)]
            nose_tip = pts[min(51, n_pts - 1)]
            left_mouth = pts[min(57, n_pts - 1)]
            right_mouth = pts[min(93, n_pts - 1)]

            # Roll: 两眼连线与水平线的夹角
            eye_diff = right_eye - left_eye
            roll = np.degrees(np.arctan2(eye_diff[1], eye_diff[0]))

            # Yaw: 鼻尖偏离两眼中心的程度
            eye_center = (left_eye + right_eye) / 2
            mouth_center = (left_mouth + right_mouth) / 2
            nose_offset = nose_tip[0] - eye_center[0]
            face_width_est = np.linalg.norm(right_eye - left_eye)
            yaw = np.degrees(np.arctan2(nose_offset, face_width_est * 1.5)) * 2

            # Pitch: 鼻尖与嘴中心的垂直偏移
            vertical_offset = nose_tip[1] - mouth_center[1]
            pitch = np.degrees(np.arctan2(vertical_offset, face_width_est)) * 2

            return float(yaw), float(pitch), float(roll)
        except Exception as e:
            logger.debug(f'Head pose estimation error: {e}')
            return 0.0, 0.0, 0.0

    def _compute_blur(self, frame: np.ndarray, bbox: dict,
                      frame_width: int, frame_height: int) -> float:
        """计算人脸 ROI 的 Laplacian 方差（模糊度指标）"""
        try:
            x = int(max(0, bbox.get('x', 0) * frame_width))
            y = int(max(0, bbox.get('y', 0) * frame_height))
            w = int(min(frame_width - x, bbox.get('width', 0) * frame_width))
            h = int(min(frame_height - y, bbox.get('height', 0) * frame_height))
            if w <= 10 or h <= 10:
                return 0.0
            roi = frame[y:y+h, x:x+w]
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
            return float(laplacian_var)
        except Exception as e:
            logger.debug(f'Blur computation error: {e}')
            return 0.0
