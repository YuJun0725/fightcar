"""独立视觉流水线：原始标签检测 → 方块中心融合 → 位置时序滤波。"""

from dataclasses import dataclass
import time


@dataclass(frozen=True)
class VisionFrame:
    detections: list
    positions: list
    warnings: tuple


class VisionPipeline:
    """每个摄像头会话创建一个实例；不会打开摄像头或控制电机。"""

    def __init__(self, config):
        # 仅实例化视觉处理时加载可选依赖，帮助/配置入口仍可独立使用。
        from .apriltag import AprilTagDetector
        from .postprocess import PositionProcessor

        self.detector = AprilTagDetector(config)
        self.processor = PositionProcessor(config)

    @property
    def pose_status(self):
        return self.detector.pose_status

    def reset(self):
        """切换摄像头、重新开始视频或改变坐标基准时清除位置历史。"""
        self.processor.reset()

    def detect(self, frame, timestamp_s=None):
        """timestamp_s 使用读帧后的单调时钟，不是曝光时间；省略时在调用开始取时。"""
        stamp = time.monotonic() if timestamp_s is None else timestamp_s
        detections = self.detector.detect(frame)
        processed = self.processor.process(detections, stamp)
        return VisionFrame(detections, processed.positions, processed.warnings)
