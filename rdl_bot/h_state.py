"""Legacy rdl_bot feedback/load state during the Core v2.3 migration.

The current CLI still depends on this historical state machine.  Its values are
useful runtime signals, but they do not have current Core identities:

- unresolved input pool size / pressure != Core xi;
- miss / deny / silence counters != Core H by identity;
- pressure-adjusted threshold is a legacy bot-local policy, not a Core law.

Canonical RIB_B -> F/F' -> E -> unresolved H semantics live in ``v23_state.py``.
"""

import random
import dynamics
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, Optional, Sized


def unresolved_input_pressure(pool: Sized, saturation: Optional[float] = None) -> float:
    """Normalize the legacy unresolved-input queue length into a local pressure.

    This is an observable bot-local coverage / unresolved-input metric.  It is
    explicitly not Core xi.
    """
    saturation = dynamics.resolve(saturation, "xi_saturation")  # legacy config key
    if saturation <= 0:
        return 0.0
    return min(1.0, len(pool) / saturation)


# Compatibility import used by the historical CLI/tests.
xi_pressure = unresolved_input_pressure


@dataclass
class HistoryEntry:
    timestamp: str
    node_id: str
    event: str
    delta: float
    seq: int = 0


class LegacyFeedbackLoadState:
    """Historical bot feedback/load accumulator.

    The persisted field names ``H_pre`` / ``H_post`` are kept for session
    compatibility.  Because they directly accumulate miss/deny/silence events,
    this whole object is not current Core H.  Canonical H is represented by
    ``UnresolvedMismatchState`` in ``v23_state.py``.
    """

    PENDING_MISS_ID = "__unresolved__"

    def __init__(self, theta: Optional[float] = None, rng: Optional[random.Random] = None):
        theta = dynamics.resolve(theta, "theta_initial")
        self.H_pre: dict[str, float] = {}
        self.H_post: dict[str, float] = {}
        self.theta = theta
        self.theta_base = theta
        self.history: list[HistoryEntry] = []
        self._seq_counter = 0
        self.drift_checkpoint_seq = 0
        self._rng = rng or random.Random()

    def on_miss(self, context_node_id: Optional[str] = None):
        self._add_pre(context_node_id or self.PENDING_MISS_ID, 0.5, "miss")

    def on_partial(self, node_id: str):
        self._add_pre(node_id, 0.2, "partial")

    def on_exact(self, node_id: str):
        self._mul_pre(node_id, 0.8, "exact")

    def on_deny(self, node_id: str):
        self._add_post(node_id, 1.0, "deny")

    def on_rephrase(self, node_id: str):
        self._add_post(node_id, 0.3, "rephrase")

    def on_agree(self, node_id: str):
        self._mul_post(node_id, 0.7, "agree")

    def on_silence(self, node_id: str):
        self._add_post(node_id, 0.5, "silence")

    H_PRE_WEIGHT = 0.4

    def _local_pressure_adjustment(self, pressure: float) -> float:
        """Historical bot-local threshold adjustment.

        The formula and random jitter are retained only for behavioural
        compatibility. ``pressure`` is unresolved-input pressure, not Core xi,
        and this function must not be cited as a Core ``xi -> theta`` rule.
        """
        if pressure <= 0:
            return 0.0
        cfg = dynamics.CONFIG
        systematic = -cfg.xi_drop_ratio * pressure  # legacy config key
        stochastic = self._rng.uniform(-1.0, 1.0) * cfg.xi_jitter_ratio * pressure
        return self.theta * (systematic + stochastic)

    # Historical private name retained for callers outside this repository.
    def _g_xi(self, pressure: float) -> float:
        return self._local_pressure_adjustment(pressure)

    def local_threshold(self, pressure: float = 0.0) -> float:
        """Legacy CLI threshold policy; not the canonical Core theta rule."""
        return self.theta + self._local_pressure_adjustment(pressure)

    def theta_eff(self, pressure: float = 0.0) -> float:
        """Compatibility alias for the historical CLI/tests."""
        return self.local_threshold(pressure)

    def merged_h(self, node_id: str) -> float:
        """Historical combined feedback-load score for one node."""
        return self.H_pre.get(node_id, 0.0) * self.H_PRE_WEIGHT + self.H_post.get(node_id, 0.0)

    def should_leap(self, pressure: float = 0.0) -> tuple[bool, str]:
        merged = {}
        for nid, value in self.H_pre.items():
            merged[nid] = merged.get(nid, 0) + value * self.H_PRE_WEIGHT
        for nid, value in self.H_post.items():
            merged[nid] = merged.get(nid, 0) + value
        if not merged:
            return False, ""
        max_id = max(merged, key=lambda key: merged[key])
        if merged[max_id] > self.local_threshold(pressure):
            return True, max_id
        return False, ""

    def leap_done(self, node_id: str):
        self.H_pre[node_id] = self.H_pre.get(node_id, 0) * 0.3
        self.H_post[node_id] = self.H_post.get(node_id, 0) * 0.3
        cfg = dynamics.CONFIG
        self.theta = min(self.theta * cfg.theta_raise_on_leap, cfg.theta_max)

    def dissipate(self, rates: Dict[str, float]) -> None:
        """Apply the historical node-local load dissipation policy."""
        for nid, rate in rates.items():
            factor = 1.0 - max(0.0, min(1.0, rate))
            if nid in self.H_pre:
                self.H_pre[nid] *= factor
            if nid in self.H_post:
                self.H_post[nid] *= factor

    def relax_theta(self, factor: Optional[float] = None):
        factor = dynamics.resolve(factor, "theta_relax")
        self.theta = max(self.theta * factor, self.theta_base)

    def forget(self, node_id: str):
        self.H_pre.pop(node_id, None)
        self.H_post.pop(node_id, None)

    def prune(self, valid_node_ids) -> int:
        valid = set(valid_node_ids) | {self.PENDING_MISS_ID}
        stale = (set(self.H_pre) | set(self.H_post)) - valid
        for nid in stale:
            self.forget(nid)
        return len(stale)

    def last_event_seq(self, node_id: str) -> int:
        for entry in reversed(self.history):
            if entry.node_id == node_id:
                return entry.seq
        return 0

    def dominant_cause(self, node_id: str) -> str:
        weights = {"deny": 0.0, "rephrase": 0.0, "miss": 0.0, "silence": 0.0}
        for entry in self.history:
            if entry.node_id == node_id and entry.event in weights:
                weights[entry.event] += abs(entry.delta)
        cause = max(weights, key=lambda key: weights[key])
        return cause if weights[cause] > 0 else "unknown"

    def on_llm_call(self, node_id: str = "__llm__"):
        self._log(node_id, "llm_call", 0.1)

    def resolve_miss(self, context_node_id: Optional[str] = None, factor: float = 0.3):
        nid = context_node_id or self.PENDING_MISS_ID
        if nid in self.H_pre:
            self.H_pre[nid] *= factor
            self._log(nid, "miss_resolved", 0.0)

    def summary(self, pressure: float = 0.0) -> str:
        max_pre = max(self.H_pre.values(), default=0.0)
        max_post = max(self.H_post.values(), default=0.0)
        return (
            f"legacy_pre={max_pre:.2f}  legacy_post={max_post:.2f}  "
            f"local_theta={self.theta:.2f}  unresolved_input_pressure={pressure:.2f}  "
            f"theta_eff≈{self.theta_eff(pressure):.2f}"
        )

    def hot_nodes(self, top: int = 3) -> list[tuple[str, float]]:
        merged = {}
        for nid, value in self.H_pre.items():
            merged[nid] = merged.get(nid, 0) + value * self.H_PRE_WEIGHT
        for nid, value in self.H_post.items():
            merged[nid] = merged.get(nid, 0) + value
        return sorted(merged.items(), key=lambda item: item[1], reverse=True)[:top]

    def drift_deltas(self) -> Dict[str, int]:
        new_events = [entry for entry in self.history if entry.seq > self.drift_checkpoint_seq]
        self.drift_checkpoint_seq = self._seq_counter
        counts = {"deny": 0, "agree": 0, "llm_usage": 0}
        for entry in new_events:
            if entry.event == "deny":
                counts["deny"] += 1
            elif entry.event == "agree":
                counts["agree"] += 1
            elif entry.event == "llm_call":
                counts["llm_usage"] += 1
        return counts

    def to_dict(self) -> dict:
        return {
            "H_pre": self.H_pre,
            "H_post": self.H_post,
            "theta": self.theta,
            "theta_base": self.theta_base,
            "history": [asdict(entry) for entry in self.history],
            "seq_counter": self._seq_counter,
            "drift_checkpoint_seq": self.drift_checkpoint_seq,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LegacyFeedbackLoadState":
        state = cls(theta=data.get("theta"))
        state.theta_base = data.get("theta_base", dynamics.CONFIG.theta_initial)
        state.H_pre = data.get("H_pre", {})
        state.H_post = data.get("H_post", {})
        state.history = [HistoryEntry(**entry) for entry in data.get("history", [])]
        state._seq_counter = data.get("seq_counter", 0)
        state.drift_checkpoint_seq = data.get("drift_checkpoint_seq", 0)
        return state

    def _add_pre(self, nid: str, delta: float, event: str):
        self.H_pre[nid] = self.H_pre.get(nid, 0) + delta
        self._log(nid, event, delta)

    def _mul_pre(self, nid: str, factor: float, event: str):
        before = self.H_pre.get(nid, 0)
        self.H_pre[nid] = before * factor
        self._log(nid, event, self.H_pre[nid] - before)

    def _add_post(self, nid: str, delta: float, event: str):
        self.H_post[nid] = self.H_post.get(nid, 0) + delta
        self._log(nid, event, delta)

    def _mul_post(self, nid: str, factor: float, event: str):
        before = self.H_post.get(nid, 0)
        self.H_post[nid] = before * factor
        self._log(nid, event, self.H_post[nid] - before)

    def _log(self, nid: str, event: str, delta: float):
        self._seq_counter += 1
        self.history.append(HistoryEntry(
            timestamp=datetime.now().isoformat(),
            node_id=nid,
            event=event,
            delta=delta,
            seq=self._seq_counter,
        ))
        if len(self.history) > 500:
            self.history = self.history[-500:]


# Historical public class name retained during staged migration.
HState = LegacyFeedbackLoadState
