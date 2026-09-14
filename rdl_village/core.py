"""Village simulation dynamics with Core v2.3 role separation.

The village predates the current RIB/RIB_B model.  Several useful simulation
states were historically named with Core symbols.  Their behaviour is retained
for regression stability, but the canonical implementation names now describe
their actual local roles:

- ``LocalLoadVector``: demo-local multi-channel load, not Core H by identity;
- ``BasalExplorationLoad``: boredom/exploration motivation, not Core H;
- ``ExplorationState``: search pressure + unresolved outcome queue, not Core xi;
- ``ActionBoundary``: village-local action policy boundary, not the complete
  semantics of Core B.

Historical names ``HVec``, ``BasalHeat``, ``XiPool`` and ``Boundary`` remain as
compatibility aliases while callers are migrated.  Canonical Core v2.3
comparison is implemented separately in ``v23_boundary.py``.
"""

import math
import random
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum


LOAD_CHANNELS = (
    "body",
    "resource",
    "motion",
    "relation",
    "dialogue",
    "goal",
    "environment",
    "boredom",
)
H_CHANNELS = LOAD_CHANNELS  # compatibility public name

# Channels supplied directly by the village motivation model rather than from
# canonical Delta(F, F').
DIRECT_CHANNELS = ("boredom",)


class Phase(Enum):
    LAT = "M_lat"
    ACT = "M_act"
    DELTA = "M_Δ"
    REFORMED = "M_B'"


def clamp(value, low, high):
    return max(low, min(high, value))


def distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def normalized(x, y):
    length = math.hypot(x, y)
    if length == 0.0:
        return 0.0, 0.0
    return x / length, y / length


def point_to_segment_distance(point, start, end):
    dx, dy = end[0] - start[0], end[1] - start[1]
    length_squared = dx * dx + dy * dy
    if length_squared == 0.0:
        return distance(point, start)
    t = clamp(((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length_squared, 0.0, 1.0)
    return distance(point, (start[0] + t * dx, start[1] + t * dy))


class LocalLoadVector:
    """Village-local multi-channel load history.

    This class preserves the historical behaviour of ``HVec``.  Its channels
    mix prediction residuals and direct motivations, so the whole vector must
    not be identified with Core H.  Migration code should use
    ``VillageUnresolvedH`` in ``v23_boundary.py`` when it needs the canonical
    unresolved-mismatch role.
    """

    def __init__(self, coeffs, channels=LOAD_CHANNELS, direct=DIRECT_CHANNELS):
        self.coeffs = coeffs
        self.values = {channel: 0.0 for channel in channels}
        self.direct = set(direct)
        self.history = deque(maxlen=48)

    def set_direct(self, channel, value):
        """Place a direct village-local motivation/load value."""
        self.values[channel] = clamp(value, 0.0, self.coeffs.ceiling)

    def observe(self, errors):
        for channel in self.values:
            if channel in self.direct:
                continue
            decay = self.coeffs.decay_for(channel)
            gain = self.coeffs.gain_for(channel)
            error = errors.get(channel, 0.0)
            self.values[channel] = clamp(
                self.values[channel] * decay + error * gain, 0.0, self.coeffs.ceiling
            )
        self.history.append(dict(self.values))

    def dominant(self):
        channel = max(self.values, key=lambda key: self.values[key])
        return channel, self.values[channel]

    def retain_after_leap(self, channel=None):
        residual = self.coeffs.residual_after_leap
        targets = [channel] if channel else list(self.values)
        for key in targets:
            if key in self.direct:
                continue
            self.values[key] *= residual

    def snapshot(self):
        return {key: round(value, 3) for key, value in self.values.items() if value > 0.001}


# Legacy public name.  Keeping the alias does not mean LocalLoadVector == Core H.
HVec = LocalLoadVector


@dataclass
class Explanation:
    channel: str
    label: str
    magnitude: float


class ErrorLedger:
    """One-tick village prediction differences plus local explanations.

    ``residual()`` is an implementation diagnostic: it is not Core xi.  The
    existing runtime still routes part of this value to the historical
    exploration state; that path is retained until the staged migration reaches
    ``npc.py`` / ``simulation.py``.
    """

    def __init__(self):
        self.errors = defaultdict(float)
        self.explanations = defaultdict(list)

    def record(self, channel, predicted, observed):
        error = abs(observed - predicted)
        self.errors[channel] = max(self.errors[channel], error)
        return error

    def record_raw(self, channel, error):
        self.errors[channel] = max(self.errors[channel], abs(error))

    def explain(self, channel, label, magnitude):
        if magnitude <= 0.0:
            return
        self.explanations[channel].append(Explanation(channel, label, magnitude))

    def residual(self):
        residual = {}
        for channel, error in self.errors.items():
            explained = sum(item.magnitude for item in self.explanations[channel])
            residual[channel] = max(0.0, error - min(explained, error))
        return residual

    def largest_residual(self):
        residual = self.residual()
        if not residual:
            return 0.0
        return max(residual.values())

    def explanation_labels(self):
        return {
            channel: [item.label for item in items]
            for channel, items in self.explanations.items()
            if items
        }


class BasalExplorationLoad:
    """Village-local boredom/exploration motivation.

    The historical class name ``BasalHeat`` is kept as an alias.  This state is
    not Core H because it is generated without a canonical Delta(F, F').
    """

    def __init__(self, neuro):
        self.neuro = neuro
        self.calm = 0.0
        self.value = 0.0
        self.quiet_ticks = 0

    def update(self, mean_error, margin=1.0):
        threshold = self.neuro.boredom_threshold
        quiet = max(0.0, threshold - mean_error) / max(0.01, threshold)
        self.calm = self.calm * 0.88 + quiet * 0.12
        if mean_error < threshold:
            self.quiet_ticks += 1
            self.value = clamp(
                self.value + self.calm * self.neuro.d4 * 0.085 * clamp(margin, 0.0, 1.0),
                0.0,
                2.2,
            )
        else:
            self.quiet_ticks = 0
            self.value *= 1.0 - clamp(mean_error, 0.0, 1.0) * 0.5
        return self.value

    def discharge(self, factor):
        self.value *= factor
        self.calm *= factor
        self.quiet_ticks = 0

    def snapshot(self):
        return {"heat": round(self.value, 3), "quiet": self.quiet_ticks}


BasalHeat = BasalExplorationLoad  # compatibility alias


class ExplorationState:
    """Village-local exploration pressure and unresolved-outcome queue.

    Historical ``XiPool`` behaviour is preserved, but this state is explicitly
    not Core xi.  The ``xi_*`` coefficient names in old profiles are legacy
    configuration keys and will be renamed in a later compatibility pass.
    """

    def __init__(self, coeffs):
        self.coeffs = coeffs
        self.value = 0.0
        self.unresolved = deque(maxlen=24)

    def accumulate(self, largest_residual):
        self.value = clamp(
            self.value + largest_residual * self.coeffs.xi_gain, 0.0, self.coeffs.xi_max
        )

    def decay(self):
        self.value *= self.coeffs.xi_decay

    def hold(self, record, t, reevaluate_after=8):
        self.unresolved.append({"record": record, "due": t + reevaluate_after})

    def take_due(self, t):
        due, pending = [], deque(maxlen=self.unresolved.maxlen)
        for item in self.unresolved:
            if item["due"] <= t:
                due.append(item["record"])
            else:
                pending.append(item)
        self.unresolved = pending
        return due

    def exploration_pressure(self):
        return clamp(self.value / max(0.01, self.coeffs.xi_max), 0.0, 1.0)


XiPool = ExplorationState  # compatibility alias; not Core xi


class ActionBoundary:
    """Village-local action/reconstruction threshold policy.

    The historical policy lowers its threshold with ``ExplorationState.value``.
    That is a simulation policy, not a Core ``B`` or ``xi -> theta`` law.  The
    old public name ``Boundary`` remains as a compatibility alias.
    """

    def __init__(self, coeffs):
        self.coeffs = coeffs
        self.summary = {}

    def theta_effective(self, exploration_value):
        return clamp(
            self.coeffs.theta_base - exploration_value * self.coeffs.xi_theta_weight,
            self.coeffs.theta_min,
            self.coeffs.theta_max,
        )


Boundary = ActionBoundary  # compatibility alias


@dataclass
class LeapEvent:
    t: int
    channel: str
    pressure: float
    threshold: float
    xi: float  # legacy serialized field; value is ExplorationState.value, not Core xi
    actions: list = field(default_factory=list)

    @property
    def exploration_value(self):
        return self.xi

    def as_record(self):
        return {
            "t": self.t,
            "channel": self.channel,
            "pressure": round(self.pressure, 3),
            "threshold": round(self.threshold, 3),
            "xi": round(self.xi, 3),  # legacy record key retained for snapshot compatibility
            "actions": list(self.actions),
        }


class LeapEngine:
    """Village-local structural reconfiguration trigger.

    Existing behaviour is preserved.  This class does not by itself establish a
    Core ``H >= theta -> M_delta`` event, because its input vector can contain
    non-canonical local loads.  ``v23_boundary.py`` supplies the canonical
    unresolved-H comparison boundary for migration.
    """

    def __init__(self, leap_coeffs, boundary):
        self.coeffs = leap_coeffs
        self.boundary = boundary
        self.last_leap_t = -10 ** 6
        self.last_basal_t = -10 ** 6
        self.count = 0

    def check(self, h_vec, exploration_state, t, exclude=()):
        if t - self.last_leap_t < self.coeffs.cooldown_ticks:
            return None
        pool = {k: v for k, v in h_vec.values.items() if k not in exclude}
        if not pool:
            return None
        channel = max(pool, key=lambda key: pool[key])
        pressure = pool[channel]
        threshold = self.boundary.theta_effective(exploration_state.value)
        if pressure < threshold:
            return None
        self.last_leap_t = t
        self.count += 1
        return LeapEvent(
            t=t,
            channel=channel,
            pressure=pressure,
            threshold=threshold,
            xi=exploration_state.value,
        )

    def check_basal(self, h_vec, exploration_state, t, channel="boredom"):
        if t - self.last_basal_t < self.coeffs.cooldown_ticks:
            return None
        pressure = h_vec.values.get(channel, 0.0)
        threshold = self.boundary.theta_effective(exploration_state.value)
        if pressure < threshold:
            return None
        self.last_basal_t = t
        self.count += 1
        return LeapEvent(
            t=t,
            channel=channel,
            pressure=pressure,
            threshold=threshold,
            xi=exploration_state.value,
        )


def weighted_choice(scored, rng, top_n=3):
    """上位候補群からの重み付き選択。最大値を必ず選ぶ必要はない。"""
    if not scored:
        return None, []
    top = sorted(scored, key=lambda item: item[1], reverse=True)[:top_n]
    total = sum(max(0.01, score) for _, score in top)
    pick = rng.random() * total
    upto = 0.0
    for candidate, score in top:
        upto += max(0.01, score)
        if upto >= pick:
            return candidate, top
    return top[0][0], top
