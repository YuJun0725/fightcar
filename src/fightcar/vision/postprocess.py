"""同帧方块中心融合和按身份隔离的因果位置滤波；不控制硬件。"""

from collections import Counter, deque
from dataclasses import dataclass
from itertools import combinations
import math
from statistics import mean, median

from .config import position_filter_config, multi_tag_fusion_config


@dataclass(frozen=True)
class PositionEstimate:
    target_id: str
    kind: str
    tag_ids: tuple
    raw_position_m: tuple
    position_m: tuple
    filter_method: str
    source: str
    rejected_tag_ids: tuple = ()


@dataclass(frozen=True)
class ProcessedPositions:
    positions: list
    warnings: tuple


def _point(value):
    point = tuple(float(v) for v in value)
    if len(point) != 3 or not all(math.isfinite(v) for v in point) or point[2] <= 0:
        raise ValueError("位置无效或位于相机后方")
    return point


def _reprojection_error(value):
    error = float(value)
    if not math.isfinite(error) or error < 0:
        raise ValueError("重投影误差无效")
    return error


def _weighted_center(candidates):
    weights = [1 / (1 + c[2] ** 2) for c in candidates]
    total = sum(weights)
    return tuple(sum(c[1][axis] * weight for c, weight in zip(candidates, weights)) / total
                 for axis in range(3))


def _same_id_cube_center(detections, max_spread_m):
    # 正方体至多同时看到三个面；每两个可见面的外法线应接近垂直。
    if not 2 <= len(detections) <= 3:
        return None
    poses = [d.pose for d in detections]
    if any(pose is None or pose.block_position_m is None for pose in poses):
        return None
    normals = [tuple(row[2] for row in pose.rotation_tag_to_camera) for pose in poses]
    max_dot = math.sin(math.radians(25))
    if any(abs(sum(x * y for x, y in zip(a, b))) > max_dot for a, b in combinations(normals, 2)):
        return None
    candidates = [(d.tag_id, _point(pose.block_position_m),
                   _reprojection_error(pose.reprojection_error_px))
                  for d, pose in zip(detections, poses)]
    if any(math.dist(a[1], b[1]) > max_spread_m for a, b in combinations(candidates, 2)):
        return None
    return _weighted_center(candidates)


class PositionProcessor:
    def __init__(self, config):
        self.filter = position_filter_config(config)
        self.fusion = multi_tag_fusion_config(config)
        self.family = config["family"]
        self.mapping = {}
        if self.fusion["enabled"]:
            for block in self.fusion["blocks"]:
                for tag in block["tags"]:
                    self.mapping[tag["id"]] = (block["block_id"], tag["center_offset_m"])
        self.reset()

    def reset(self):
        self.history = {}
        self.last_timestamp = None

    def _identity(self, detection):
        mapped = self.mapping.get(detection.tag_id) if detection.family == self.family else None
        if mapped:
            return "block:" + mapped[0]
        return "tag:{}:{}".format(detection.family, detection.tag_id)

    def _smooth(self, identity, kind, point, stamp):
        if not self.filter["enabled"]:
            return point, "none"
        old = self.history.get(identity)
        fresh = old is None or old[0] != kind
        if fresh:
            samples = deque(maxlen=self.filter["window"])
            previous = point
        else:
            _, _, samples, previous = old
        samples.append(point)
        method = self.filter["method"]
        if method == "ema":
            alpha = self.filter["alpha"]
            used = point if fresh else tuple(alpha * now + (1 - alpha) * before
                                             for now, before in zip(point, previous))
        else:
            reducer = mean if method == "mean" else median
            used = tuple(float(reducer(values)) for values in zip(*samples))
        self.history[identity] = (kind, stamp, samples, used)
        return used, method

    def process(self, detections, timestamp_s):
        if (isinstance(timestamp_s, bool) or not isinstance(timestamp_s, (int, float))
                or not math.isfinite(timestamp_s)):
            raise ValueError("位置处理时间戳必须是有限的单调时钟秒数")
        if self.last_timestamp is not None and timestamp_s <= self.last_timestamp:
            self.reset()
        self.last_timestamp = timestamp_s
        self.history = {key: value for key, value in self.history.items()
                        if timestamp_s - value[1] <= self.filter["reset_after_s"]}
        detections = list(detections)
        counts = Counter((d.family, d.tag_id) for d in detections)
        warnings, estimates, groups = [], [], {}
        duplicates = {}
        for d in detections:
            if counts[d.family, d.tag_id] > 1:
                duplicates.setdefault(self._identity(d), []).append(d)

        def emit(identity, kind, ids, point, source, rejected=()):
            used, method = self._smooth(identity, kind, point, timestamp_s)
            estimates.append(PositionEstimate(identity, kind, tuple(ids), point, used,
                                               method, source, tuple(rejected)))

        max_spread = self.fusion["same_id_max_spread_m"]
        for identity, repeated in sorted(duplicates.items()):
            point = None
            if max_spread is not None and identity.startswith("tag:"):
                try:
                    point = _same_id_cube_center(repeated, max_spread)
                except (ValueError, TypeError, OverflowError):
                    pass
            if point is not None:
                emit(identity, "block", (d.tag_id for d in repeated), point, "same_id_fusion")
            else:
                self.history.pop(identity, None)
                warnings.append("{} 重复ID的检测无法合并，本帧跳过位置处理".format(identity))

        for d in detections:
            identity = self._identity(d)
            if identity in duplicates or d.pose is None:
                continue
            pose = d.pose
            try:
                error = _reprojection_error(pose.reprojection_error_px)
                mapped = self.mapping.get(d.tag_id) if d.family == self.family else None
                if mapped:
                    offset = mapped[1]
                    point = _point(tuple(t + sum(r * o for r, o in zip(row, offset))
                                         for t, row in zip(pose.tag_position_m, pose.rotation_tag_to_camera)))
                    groups.setdefault(identity, []).append((d.tag_id, point, error))
                else:
                    block = pose.block_position_m is not None
                    point = _point(pose.block_position_m if block else pose.tag_position_m)
                    emit(identity, "block" if block else "tag", (d.tag_id,), point,
                         "single_tag" if block else "tag")
            except (ValueError, TypeError, OverflowError) as error:
                self.history.pop(identity, None)
                warnings.append("{}：{}".format(identity, error))

        for identity, candidates in sorted(groups.items()):
            candidates.sort(key=lambda c: c[0])
            # 每块最多6个面，穷举最大一致子集最多63组，避免链式相近误合并。
            best, best_weight = (), -1.0
            for size in range(len(candidates), 0, -1):
                for subset in combinations(candidates, size):
                    if not all(math.sqrt(sum((x - y) ** 2 for x, y in zip(a[1], b[1])))
                               <= self.fusion["max_spread_m"] for a, b in combinations(subset, 2)):
                        continue
                    weight = sum(1 / (1 + c[2] ** 2) for c in subset)
                    if weight > best_weight:
                        best, best_weight = subset, weight
                if best:
                    break
            if len(best) >= self.fusion["min_tags"]:
                point = _weighted_center(best)
                source = "multi_tag_fusion"
            else:
                reason = "标签数量不足" if len(candidates) < self.fusion["min_tags"] else "标签中心观测不一致"
                if not self.fusion["fallback_to_single"]:
                    self.history.pop(identity, None)
                    warnings.append("{}：{}，本帧不输出位置".format(identity, reason))
                    continue
                best = (min(candidates, key=lambda c: (c[2], c[0])),)
                point, source = best[0][1], "single_tag"
                warnings.append("{}：{}，回退到单标签 {}".format(identity, reason, best[0][0]))
            ids = tuple(c[0] for c in best)
            rejected = tuple(c[0] for c in candidates if c[0] not in ids)
            if rejected:
                warnings.append("{} 未采用标签 {}".format(identity, ",".join(map(str, rejected))))
            emit(identity, "block", ids, point, source, rejected)
        return ProcessedPositions(estimates, tuple(warnings))
