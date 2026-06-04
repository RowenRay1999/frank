"""
Frank 外观特征提取器（ReID）

轻量方案：HSV 颜色直方图（上身+下身分离）+ 可选 CNN（OSNet/MobileNet-ReID）
用于多人跟踪中的外观代价计算和离场重入恢复
"""

import logging
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger('frank.reid')

FEATURE_DIM = 128  # 外观特征维度


class ReIDExtractor:
    """外观特征提取器

    提取人物的衣着颜色/纹理特征，用于：
    1. 多人跟踪中区分外观不同的人（辅助运动匹配）
    2. 人物离场后重入的身份恢复（Re-ID）
    """

    def __init__(self, method: str = 'hsv_histogram'):
        """
        Args:
            method: 提取方法
                - 'hsv_histogram': HSV 颜色直方图（默认，快速，2-3ms）
                - 未来可扩展 'osnet' / 'mobilenet_reid' CNN 方案
        """
        self.method = method
        self._model = None
        if method == 'osnet':
            self._init_osnet()

    def _init_osnet(self):
        """延迟加载 OSNet（可选，需要 torch）"""
        try:
            import torch
            import torchreid
            self._model = torchreid.models.build_model(
                name='osnet_x0_25',
                num_classes=1000,
                pretrained=True,
            )
            self._model.eval()
            logger.info('OSNet ReID model loaded')
        except ImportError:
            logger.warning('torch/torchreid not available, falling back to HSV histogram')
            self.method = 'hsv_histogram'
        except Exception as e:
            logger.warning(f'OSNet init failed: {e}, falling back to HSV histogram')
            self.method = 'hsv_histogram'

    def extract(self, frame: np.ndarray, bbox: tuple[float, float, float, float]) -> Optional[np.ndarray]:
        """从帧中提取人物外观特征

        Args:
            frame: BGR 图像 (H, W, 3)
            bbox: (x, y, w, h) 归一化坐标 [0, 1]

        Returns:
            128-d normalized float32 feature vector, or None
        """
        if self.method == 'osnet' and self._model:
            return self._extract_osnet(frame, bbox)
        return self._extract_hsv_histogram(frame, bbox)

    def _extract_hsv_histogram(self, frame: np.ndarray, bbox: tuple[float, float, float, float]) -> Optional[np.ndarray]:
        """HSV 颜色直方图 + 空间分区

        策略：
        - 将人物区域分为上下两半（上半身/下半身）
        - 每半提取 HSV 直方图 (H:16 bins, S:8 bins)
        - 拼接得到 (16+8)*2 = 48 维 → pad/truncate 到 128 维
        """
        try:
            h, w = frame.shape[:2]
            x, y, bw, bh = bbox

            # 从归一化坐标转换到像素坐标
            x1 = int(max(0, x * w))
            y1 = int(max(0, y * h))
            x2 = int(min(w, (x + bw) * w))
            y2 = int(min(h, (y + bh) * h))

            if x2 <= x1 or y2 <= y1:
                return None

            person_roi = frame[y1:y2, x1:x2]
            if person_roi.size == 0:
                return None

            hsv = cv2.cvtColor(person_roi, cv2.COLOR_BGR2HSV)

            # 上下分区
            mid_y = hsv.shape[0] // 2
            top = hsv[:mid_y, :]
            bottom = hsv[mid_y:, :]

            features = []
            for region in [top, bottom]:
                if region.size == 0:
                    features.extend([0.0] * 24)
                    continue
                # H 直方图 (16 bins)
                h_hist = cv2.calcHist([region], [0], None, [16], [0, 180])
                h_hist = cv2.normalize(h_hist, h_hist).flatten()
                # S 直方图 (8 bins)
                s_hist = cv2.calcHist([region], [1], None, [8], [0, 256])
                s_hist = cv2.normalize(s_hist, s_hist).flatten()
                features.extend(h_hist.tolist())
                features.extend(s_hist.tolist())

            feat = np.array(features, dtype=np.float32)

            # 填充/截断到 FEATURE_DIM
            if len(feat) < FEATURE_DIM:
                feat = np.pad(feat, (0, FEATURE_DIM - len(feat)), mode='constant')
            else:
                feat = feat[:FEATURE_DIM]

            # L2 归一化
            norm = np.linalg.norm(feat)
            if norm > 0:
                feat = feat / norm

            return feat
        except Exception as e:
            logger.debug(f'HSV feature extraction error: {e}')
            return None

    def _extract_osnet(self, frame: np.ndarray, bbox: tuple[float, float, float, float]) -> Optional[np.ndarray]:
        """OSNet CNN 特征提取（保留接口，待后续实现）"""
        return self._extract_hsv_histogram(frame, bbox)

    @staticmethod
    def cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
        """外观特征余弦距离 (0-2, 越小越相似)"""
        if a is None or b is None:
            return 1.0
        similarity = float(np.dot(a, b))
        return 1.0 - similarity  # 转为距离
