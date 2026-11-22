"""AprilTag 检测与标签/方块中心的相机坐标估计，不持有摄像头。"""

from copy import deepcopy
from dataclasses import dataclass
import math
from typing import Optional, Tuple

try:
    import cv2
    import numpy as np
except ImportError as error:
    raise ImportError("视觉模块需要安装 vision/requirements.txt 中的可选依赖") from error

from .config import validate_config


Vector3 = Tuple[float, float, float]


@dataclass(frozen=True)
class TagPose:
    tag_position_m: Vector3
    block_position_m: Optional[Vector3]
    rotation_tag_to_camera: Tuple[Vector3, Vector3, Vector3]
    range_m: float
    bearing_deg: float
    reprojection_error_px: float
    alternative_error_px: Optional[float]


@dataclass(frozen=True)
class TagDetection:
    tag_id: int
    family: str
    center_px: Tuple[float, float]
    corners_px: Tuple[Tuple[float, float], ...]
    pose: Optional[TagPose]
    pose_status: str


def tag_object_points(size_m):
    """IPPE_SQUARE 固定顺序；Tag 的 X 向右、Y 向上、Z 朝印刷面外。"""
    half = size_m / 2.0
    return np.array([[-half, half, 0], [half, half, 0],
                     [half, -half, 0], [-half, -half, 0]], dtype=np.float64)


def estimate_tag_pose(corners_px, tag_size_m, camera_matrix, dist_coeffs,
                      block_center_offset_m=None, max_reprojection_error_px=3.0):
    """返回 Tag→相机位姿；退化/超差返回 None。单位米，畸变使用 OpenCV 针孔模型。

    corners_px 必须保留检测器解码后的顺序，不可按屏幕位置重新排序。
    单平面可能有两个近似解，此处选正深度且重投影误差最小的一解。
    """
    if not math.isfinite(tag_size_m) or tag_size_m <= 0:
        raise ValueError("tag_size_m 必须为有限正数")
    corners = np.asarray(corners_px, dtype=np.float64).reshape(4, 2)
    matrix = np.asarray(camera_matrix, dtype=np.float64).reshape(3, 3)
    distortion = np.asarray(dist_coeffs, dtype=np.float64)
    if not np.isfinite(corners).all():
        return None
    if abs(cv2.contourArea(corners.astype(np.float32))) < 1.0:
        return None
    points = tag_object_points(tag_size_m)
    solutions = cv2.solvePnPGeneric(points, corners, matrix, distortion,
                                   flags=cv2.SOLVEPNP_IPPE_SQUARE)
    initial = list(zip(solutions[1], solutions[2]))
    # IPPE 在严格正视等姿态下可能产生数值退化；平面 ITERATIVE 提供备用初值。
    success, rvec, tvec = cv2.solvePnP(points, corners, matrix, distortion,
                                     flags=cv2.SOLVEPNP_ITERATIVE)
    if success:
        initial.append((rvec, tvec))
    candidates = []
    for rotation_vector, translation in initial:
        if not (np.isfinite(rotation_vector).all() and np.isfinite(translation).all()):
            continue
        rotation_vector, translation = cv2.solvePnPRefineLM(
            points, corners, matrix, distortion, rotation_vector.copy(), translation.copy())
        if not (np.isfinite(rotation_vector).all() and np.isfinite(translation).all()):
            continue
        rotation = cv2.Rodrigues(rotation_vector)[0]
        translation = translation.reshape(3)
        camera_points = points @ rotation.T + translation
        if np.any(camera_points[:, 2] <= 0):
            continue
        projected = cv2.projectPoints(points, rotation_vector, translation, matrix, distortion)[0]
        error = float(np.sqrt(np.mean(np.sum((projected.reshape(4, 2) - corners) ** 2, axis=1))))
        # 不把多个初值收敛到同一个解误报为独立的第二种姿态。
        duplicate = any(np.linalg.norm(rotation - old[1]) < 1e-6
                        and np.linalg.norm(translation - old[2]) < 1e-8 for old in candidates)
        if math.isfinite(error) and not duplicate:
            candidates.append((error, rotation, translation))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    error, rotation, translation = candidates[0]
    if error > max_reprojection_error_px:
        return None
    block = None
    if block_center_offset_m is not None:
        block = tuple(float(value) for value in
                      (rotation @ np.asarray(block_center_offset_m) + translation))
    return TagPose(
        tag_position_m=tuple(float(value) for value in translation),
        block_position_m=block,
        rotation_tag_to_camera=tuple(tuple(float(value) for value in row) for row in rotation),
        range_m=float(np.linalg.norm(translation)),
        bearing_deg=math.degrees(math.atan2(translation[0], translation[2])),
        reprojection_error_px=error,
        alternative_error_px=candidates[1][0] if len(candidates) > 1 else None,
    )


class AprilTagDetector:
    """创建一次，逐帧 detect(frame)。不保存上一帧目标，不开线程或控制电机。"""

    def __init__(self, config):
        validate_config(config)
        self.config = deepcopy(config)
        if not hasattr(cv2, "aruco") or not hasattr(cv2.aruco, "ArucoDetector"):
            raise RuntimeError("需要含 cv2.aruco.ArucoDetector 的 OpenCV，请安装 vision/requirements.txt")
        family = self.config["family"]
        dictionary = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, "DICT_APRILTAG_" + family[3:]))
        parameters = cv2.aruco.DetectorParameters()
        parameters.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
        self.detector = cv2.aruco.ArucoDetector(dictionary, parameters)
        self.calibration = self.config["camera"]["calibration"]

    @property
    def pose_status(self):
        if self.calibration is None:
            return "calibration_missing"
        if self.config["tag_size_m"] is None:
            return "tag_size_missing"
        return "ready"

    def detect(self, frame):
        """输入原分辨率 uint8 灰度或 BGR 图像，返回本帧所有识别结果。"""
        if not isinstance(frame, np.ndarray) or frame.dtype != np.uint8 or frame.size == 0:
            raise ValueError("frame 必须为非空 uint8 图像")
        if frame.ndim == 2:
            gray = frame
        elif frame.ndim == 3 and frame.shape[2] == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            raise ValueError("frame 必须为灰度或三通道 BGR 图像")
        if self.calibration is not None and tuple(gray.shape[::-1]) != tuple(self.calibration["image_size"]):
            raise ValueError("图像分辨率与 calibration.image_size 不符，请使用标定时的相机模式；不要裁剪或缩放")
        corners, ids, _ = self.detector.detectMarkers(gray)
        if ids is None:
            return []
        results = []
        for tag_corners, tag_id in zip(corners, ids.flatten()):
            points = tag_corners.reshape(4, 2)
            # 对角线交点作为像素中心，减少透视下直接平均四角造成的偏移。
            homogeneous = np.column_stack((points, np.ones(4)))
            center = np.cross(np.cross(homogeneous[0], homogeneous[2]),
                              np.cross(homogeneous[1], homogeneous[3]))
            if abs(center[2]) < 1e-9:
                continue
            center = center[:2] / center[2]
            pose = None
            status = self.pose_status
            if status == "ready":
                pose = estimate_tag_pose(
                    points, self.config["tag_size_m"], self.calibration["camera_matrix"],
                    self.calibration["dist_coeffs"], self.config["block_center_offset_m"],
                    self.config["detector"]["max_reprojection_error_px"],
                )
                status = "ok" if pose is not None else "pose_rejected"
            results.append(TagDetection(
                int(tag_id), self.config["family"], tuple(float(value) for value in center),
                tuple(tuple(float(value) for value in point) for point in points), pose, status,
            ))
        return results


def annotate_frame(frame, detections):
    """返回可保存的标注副本，原始图像不变；不调用 GUI。"""
    result = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR) if frame.ndim == 2 else frame.copy()
    for detection in detections:
        corners = np.rint(detection.corners_px).astype(np.int32)
        cv2.polylines(result, [corners], True, (0, 200, 0), 2)
        center = tuple(int(round(value)) for value in detection.center_px)
        cv2.drawMarker(result, center, (0, 0, 255), cv2.MARKER_CROSS, 12, 1)
        label = "ID {}".format(detection.tag_id)
        if detection.pose is not None:
            label += " tag xyz=({:.3f},{:.3f},{:.3f})m".format(*detection.pose.tag_position_m)
        else:
            label += " " + detection.pose_status
        cv2.putText(result, label, (max(0, center[0] - 60), max(20, center[1] - 15)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 150, 0), 1, cv2.LINE_AA)
    return result
