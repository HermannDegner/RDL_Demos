"""RDL中核動態：B・H_vec・ξ・θ・Leap・相状態。

参照:
  RDL_NPC行動決定システム §3（主要変数）, §6（ξ探索と跳躍の区別）
  RDL_簡易村シミュレーター §12（H_vec・ξ・Leap）
  RDL_Demos/rdl_system/core（H更新式・θ算出・leap判定）
"""

import math
import random
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum


H_CHANNELS = (
    "body",
    "resource",
    "motion",
    "relation",
    "dialogue",
    "goal",
    "environment",
    "boredom",
)

# 誤差から積み上げるのではなく、外から直接与えるチャネル。
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


class HVec:
    """破断位置を保持するHベクトル。

    単一のストレス値へ圧縮しない（村§19-9）。
    観測されなかったチャネルも減衰させ、古い熱が残り続けないようにする。
    """

    def __init__(self, coeffs, channels=H_CHANNELS, direct=DIRECT_CHANNELS):
        self.coeffs = coeffs
        self.values = {channel: 0.0 for channel in channels}
        self.direct = set(direct)
        self.history = deque(maxlen=48)

    def set_direct(self, channel, value):
        """予測差の蓄積ではなく、自発生成された仮想熱をそのまま置く。"""
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
        """Leap後もHを完全消去しない（村§12）。再編前の履歴を一部残す。"""
        residual = self.coeffs.residual_after_leap
        targets = [channel] if channel else list(self.values)
        for key in targets:
            # 直接チャネルは毎tick外から書き直されるので、ここで減らしても消える。
            # 放出は熱源側（BasalHeat.discharge）が行う。
            if key in self.direct:
                continue
            self.values[key] *= residual

    def snapshot(self):
        return {key: round(value, 3) for key, value in self.values.items() if value > 0.001}


@dataclass
class Explanation:
    channel: str
    label: str
    magnitude: float


class ErrorLedger:
    """1tick分の予測差Eと、その説明を保持する。

    説明のつく誤差はM_B内で処理済みとみなし、ξへは残さない。
    説明のつかない残差だけが不定剰余としてξへ流れる。

    重要：説明には必ず具体的な根拠（進路封鎖、外力、既知の危険文脈など）を要求する。
    無条件の下駄を置くと平常時の誤差が丸ごと消え、Leapが原理的に発火しなくなる。
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


class BasalHeat:
    """基層構造的跳躍：誤差が少ないときに仮想熱を自発生成する。

    参照:
      RDL_階層構造モジュール §2（退屈という現象）
      神経力学的基層構造 §1（ドーパミン D4）

    誤差が起きてから対応するだけでは生存可能性が低い。予測性が非常に高い状態が
    続くと「退屈」という仮想熱が立ち、探索行動を促す予防的誤差探索機構として働く。

        誤差が少ない状態 → 仮想熱の自発生成 → 探索行動 → 新しい誤差 → M_Bの拡張

    誤差ベースのHとは熱源が別なので、蓄積も別に持つ。
    """

    def __init__(self, neuro):
        self.neuro = neuro
        self.calm = 0.0
        self.value = 0.0
        self.quiet_ticks = 0

    def update(self, mean_error, margin=1.0):
        """判定には誤差の平均を使う。

        「予測性が非常に高い状態」は全チャネルにわたる予測成功度であって、
        最大値ではない。チャネル数が多いと max はほぼ常に高く、静穏が成立しない。

        margin は身体的な余裕（0で逼迫、1で余裕あり）。
        退屈は予防的誤差探索であり、投資である。払えない投資は予防にならない。
        「正しく飢えている」個体は予測誤差が小さいため、余裕を見ないと
        静穏と判定されて探索に出てしまい、そのまま戻れずに死ぬ。
        """
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
            # 新しい誤差が見つかれば退屈は解消する
            self.quiet_ticks = 0
            self.value *= 1.0 - clamp(mean_error, 0.0, 1.0) * 0.5
        return self.value

    def discharge(self, factor):
        self.value *= factor
        self.calm *= factor
        self.quiet_ticks = 0

    def snapshot(self):
        return {"heat": round(self.value, 3), "quiet": self.quiet_ticks}


class XiPool:
    """ξ：不定剰余と、未確定結果の保持プール。

    NPC§3.6  ξ探索は一様乱数ではなく、実行可能領域内の低頻度候補を試す操作。
    NPC§8.3  判定できない結果は成功にも失敗にも確定させず、ここへ残して後で再評価する。
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
        """ξが高いほど低頻度候補を試しやすくなる。跳躍とは別系統。"""
        return clamp(self.value / max(0.01, self.coeffs.xi_max), 0.0, 1.0)


class Boundary:
    """B：行動境界。θはξによって下がる（RDL_Demos/core と同式）。"""

    def __init__(self, coeffs):
        self.coeffs = coeffs
        self.summary = {}

    def theta_effective(self, xi_value):
        return clamp(
            self.coeffs.theta_base - xi_value * self.coeffs.xi_theta_weight,
            self.coeffs.theta_min,
            self.coeffs.theta_max,
        )


@dataclass
class LeapEvent:
    t: int
    channel: str
    pressure: float
    threshold: float
    xi: float
    actions: list = field(default_factory=list)

    def as_record(self):
        return {
            "t": self.t,
            "channel": self.channel,
            "pressure": round(self.pressure, 3),
            "threshold": round(self.threshold, 3),
            "xi": round(self.xi, 3),
            "actions": list(self.actions),
        }


class LeapEngine:
    """M_act → M_Δ → M_B' の遷移判定。

    跳躍を無条件のランダム行動として実装しない（NPC§12-3、村§19-10）。
    再編対象は最大Hのチャネルに局所化し、何を組み替えたかを記録する。
    """

    def __init__(self, leap_coeffs, boundary):
        self.coeffs = leap_coeffs
        self.boundary = boundary
        self.last_leap_t = -10 ** 6
        self.last_basal_t = -10 ** 6
        self.count = 0

    def check(self, h_vec, xi, t, exclude=()):
        """誤差由来の跳躍。excludeで自発熱チャネルを外す。"""
        if t - self.last_leap_t < self.coeffs.cooldown_ticks:
            return None
        pool = {k: v for k, v in h_vec.values.items() if k not in exclude}
        if not pool:
            return None
        channel = max(pool, key=lambda key: pool[key])
        pressure = pool[channel]
        threshold = self.boundary.theta_effective(xi.value)
        if pressure < threshold:
            return None
        self.last_leap_t = t
        self.count += 1
        return LeapEvent(t=t, channel=channel, pressure=pressure, threshold=threshold, xi=xi.value)

    def check_basal(self, h_vec, xi, t, channel="boredom"):
        """基層構造的跳躍。熱源が誤差ではないので、クールダウンも誤差系と分ける。

        共有すると自発熱の跳躍が誤差由来の跳躍の枠を奪い、
        本来処理すべき破断への再編が遅れる。
        """
        if t - self.last_basal_t < self.coeffs.cooldown_ticks:
            return None
        pressure = h_vec.values.get(channel, 0.0)
        threshold = self.boundary.theta_effective(xi.value)
        if pressure < threshold:
            return None
        self.last_basal_t = t
        self.count += 1
        return LeapEvent(t=t, channel=channel, pressure=pressure, threshold=threshold, xi=xi.value)


def weighted_choice(scored, rng, top_n=3):
    """上位候補群からの重み付き選択（NPC§5.6）。最大値を必ず選ぶ必要はない。"""
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
