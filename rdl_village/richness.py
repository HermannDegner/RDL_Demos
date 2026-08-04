"""行動の豊かさの測定。

参照:
  RDL_簡易村シミュレーター §2（B_village）, §6.2（場所の個体的意味）, §17.2（村ログ）

生存率は目的ではない。測るのは、村§2 が B として掲げた状態がどれだけ立ち上がったか。

    B_village = 少数のNPCが、共有された物理世界の中で、
                共有されていない個体記憶と関係履歴を持ち、
                日ごとに少しずつ異なる生活構造を形成する状態

ここから4つの操作的指標を引く。
  repertoire  行動レパートリーの広さ        （画一なら貧しい）
  divergence  個体間の分岐                  「共有されていない個体記憶」
  meaning_var 同じ場所の意味の個体差        §6.2「意味は共有されない」
  day_drift   日ごとの生活構造の変化        「日ごとに少しずつ異なる」
  leap_var    破断位置の多様性              単一チャネルに偏れば貧しい
"""

import math
import random
from collections import Counter, defaultdict

from .core import H_CHANNELS
from .world import TICKS_PER_DAY

# day_drift の測定パラメータ。
# 初版は「行動種別・村全体」で測っていたが、検証により無効と判明した。
#   観測 0.0441 に対しノイズ床 0.0313（1.4倍）
#   別々の村の差 0.0109 が、同じ村の隣接日の差より小さい
# 集約が個体差を打ち消し、行動種別が構造を区別できていなかった。
# 構造は「何をしたか」ではなく「どこで」に宿るため、個体別・(行動,場所)で測る。
DRIFT_RESAMPLES = 5
DRIFT_RNG_SEED = 20260803


def _day_of(tick):
    """tick番号を日へ割り当てる。

    VillageClock.decision_tick と同じ定義を使う。
    評価側だけが独自に補正すると、世界時計の day と評価側の day がずれ、
    個体の予定・光量と評価上の日付が食い違う。
    """
    return max(0, tick - 1) // TICKS_PER_DAY


def _entropy(counter):
    total = sum(counter.values())
    if total <= 0:
        return 0.0
    return -sum((n / total) * math.log2(n / total) for n in counter.values() if n)


def _normalized_entropy(counter):
    distinct = len([n for n in counter.values() if n])
    if distinct <= 1:
        return 0.0
    return _entropy(counter) / math.log2(distinct)


def _js_divergence(left, right):
    keys = set(left) | set(right)
    if not keys:
        return 0.0
    left_total = sum(left.values()) or 1
    right_total = sum(right.values()) or 1
    divergence = 0.0
    for key in keys:
        p = left.get(key, 0) / left_total
        q = right.get(key, 0) / right_total
        m = (p + q) / 2
        if p:
            divergence += 0.5 * p * math.log2(p / m)
        if q:
            divergence += 0.5 * q * math.log2(q / m)
    return divergence


def _day_drift(rows):
    """個体ごとの生活構造が日ごとにどれだけ変わるか。

    有限標本の揺らぎだけでJSダイバージェンスは正の値を取る。
    同一分布から同じ件数を再抽出したときの期待値をノイズ床として差し引く。
    """
    rng = random.Random(DRIFT_RNG_SEED)
    per_agent = defaultdict(lambda: defaultdict(Counter))
    for row in rows:
        key = (row["selected"], row.get("place"))
        per_agent[row["npc"]][_day_of(row["tick"])][key] += 1

    excess = []
    for days in per_agent.values():
        ordered = sorted(days)
        pool = Counter()
        for counts in days.values():
            pool.update(counts)
        items = list(pool.elements())
        if len(items) < 2:
            continue
        for index in range(len(ordered) - 1):
            left, right = days[ordered[index]], days[ordered[index + 1]]
            n_left, n_right = sum(left.values()), sum(right.values())
            if not n_left or not n_right:
                continue
            observed = _js_divergence(left, right)
            floor = sum(
                _js_divergence(
                    Counter(rng.choices(items, k=n_left)),
                    Counter(rng.choices(items, k=n_right)),
                )
                for _ in range(DRIFT_RESAMPLES)
            ) / DRIFT_RESAMPLES
            excess.append(max(0.0, observed - floor))
    return sum(excess) / len(excess) if excess else 0.0


def measure(simulation):
    rows = [row for row in simulation.logs if "selection_mode" in row]

    village_actions = Counter(row["selected"] for row in rows)
    per_agent = defaultdict(Counter)
    per_day = defaultdict(Counter)
    for row in rows:
        per_agent[row["npc"]][row["selected"]] += 1
        per_day[_day_of(row["tick"])][row["selected"]] += 1

    # 死亡による交絡を分離する（破断検査 v0.5 §4）。
    # 死んだ個体はログが途中で止まり、行動分布が短く偏るため分岐が水増しされる。
    survivors = {agent.name for agent in simulation.agents if agent.alive}
    names = sorted(per_agent)
    living_names = sorted(n for n in names if n in survivors)

    def _mean_pairwise(pool, keys):
        values = [
            _js_divergence(pool[a], pool[b])
            for index, a in enumerate(keys)
            for b in keys[index + 1 :]
        ]
        return sum(values) / len(values) if values else 0.0

    pairs_all = _mean_pairwise(per_agent, names)
    pairs_alive = _mean_pairwise(per_agent, living_names)

    days = sorted(per_day)
    village_drift = [
        _js_divergence(per_day[days[i]], per_day[days[i + 1]]) for i in range(len(days) - 1)
    ]

    # 同じ場所が個体ごとに別の意味を持っているか（§6.2）
    place_axes = defaultdict(lambda: defaultdict(list))
    for agent in simulation.agents:
        for meaning in agent.prediction_field.known_places():
            for axis in ("comfort", "social_expectation", "resource_expectation", "familiarity"):
                place_axes[meaning.place_id][axis].append(getattr(meaning, axis))
    # 意味の分散が低いのが「似ている」からか「そもそも共有していない」からかを
    # 値だけで判別できるよう、共有の範囲も返す。
    shared_counts = [
        len(values)
        for axes in place_axes.values()
        for values in list(axes.values())[:1]
    ]
    comparable = sum(1 for count in shared_counts if count >= 2)
    everyone = sum(1 for count in shared_counts if count >= len(simulation.agents))

    variances = []
    for axes in place_axes.values():
        for values in axes.values():
            if len(values) < 2:
                continue
            mean = sum(values) / len(values)
            variances.append(sum((v - mean) ** 2 for v in values) / len(values))

    leap_channels = Counter()
    for key, count in simulation.village_log.items():
        if key.startswith("leap:"):
            leap_channels[key.split(":", 1)[1]] += count

    return {
        "repertoire": _normalized_entropy(village_actions),
        "distinct_actions": len(village_actions),
        # 主軸は生存者のみで測る。全個体版は照合用に併記する。
        "divergence": pairs_alive,
        "divergence_all": pairs_all,
        "meaning_var": sum(variances) / len(variances) if variances else 0.0,
        "meaning_comparable": comparable,
        "meaning_shared_by_all": everyone,
        "meaning_observers": sum(shared_counts) / len(shared_counts) if shared_counts else 0.0,
        "day_drift": _day_drift(rows),
        # 旧定義。無効と判明済みだが、過去の測定値との照合用に残す。
        "day_drift_legacy": sum(village_drift) / len(village_drift) if village_drift else 0.0,
        # 出現したチャネル数で正規化すると、2チャネルしか発火しなくても1.0になる。
        # 破断位置の広さを見るなら、可能な全チャネル数で割る。
        "leap_var": _entropy(leap_channels) / math.log2(len(H_CHANNELS)),
        "leap_channels": len(leap_channels),
        "leap_total": sum(leap_channels.values()),
    }
