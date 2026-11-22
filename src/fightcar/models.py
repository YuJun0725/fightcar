"""各层共用的数据；轮速以朝车头方向为正，ADC 为原始值。"""

from dataclasses import dataclass
from typing import Optional, Tuple

DIRECTIONS = ("front", "right", "rear", "left")


@dataclass(frozen=True)
class PositionFrame:
    timestamp: float
    positions: tuple


@dataclass(frozen=True)
class WheelCommand:
    left: int = 0
    right: int = 0


@dataclass(frozen=True)
class Command:
    wheels: WheelCommand = WheelCommand()
    support: Optional[str] = None


@dataclass(frozen=True)
class SensorSnapshot:
    timestamp: float
    adc: Tuple[int, ...]
    io: Tuple[int, ...]


@dataclass(frozen=True)
class Observation:
    platform: str  # below / partial / on，分别为两端低、一端高、两端高
    candidates: Tuple[str, ...]  # 低位光电触发且上层测距未见近围栏
    walls: Tuple[str, ...]
    aligned: Optional[str]  # front / rear / None；只是传感器组合判断
    distance_adc: Tuple[float, ...] = ()  # 前右后左：当前真正用于围栏判断的 ADC
