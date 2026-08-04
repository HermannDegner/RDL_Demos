"""RDL簡易村シミュレーター v0.1。

設計:
  RDL_簡易村シミュレーター（T4 / DRAFT v0.1）
  RDL_NPC行動決定システム（T4 / DRAFT v0.3）
係数:
  RDL_Demos/rdl_system/profiles の reference profile

実装範囲は村§15.2「v0.1で実装するもの」、構成は村§16 の主要クラス表に対応する。
"""

from .core import HVec, LeapEngine, Phase, XiPool
from .npc import VillageNPC
from .profiles import REFERENCE_PROFILE, VILLAGE_PROFILE, Profile
from .simulation import VillageObserver, VillageSimulation
from .world import PhysicalWorld, VillageClock

__all__ = [
    "HVec",
    "LeapEngine",
    "Phase",
    "XiPool",
    "Profile",
    "REFERENCE_PROFILE",
    "VILLAGE_PROFILE",
    "PhysicalWorld",
    "VillageClock",
    "VillageNPC",
    "VillageSimulation",
    "VillageObserver",
]
