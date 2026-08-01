"""
h_state.py
H_vec 管理: 誤差蓄積の観測
"""

import random
import dynamics
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Dict, List, Optional, Sized


def xi_pressure(xi_pool: Sized, saturation: Optional[float] = None) -> float:
    """
    ξプールの滞留量を 0〜1 の「ξ圧」に正規化する。
    ノード化できずに残っている入力が多いほど、現在のM_Bが世界を
    捉えきれていないことを意味する。
    """
    saturation = dynamics.resolve(saturation, "xi_saturation")
    if saturation <= 0:
        return 0.0
    return min(1.0, len(xi_pool) / saturation)


@dataclass
class HistoryEntry:
    timestamp: str
    node_id: str
    event: str       # miss / partial / exact / deny / rephrase / agree / silence / llm_call
    delta: float
    seq: int = 0      # 通算イベント番号。history は500件でtrimされるがseqは増え続ける


class HState:
    # 最近傍ノードが無い未知入力のHを積む先。実ノードIDではないが、
    # 「未解決の入力が溜まっている」という意味のある蓄積なので、
    # __llm__ などの解決不能な疑似IDとは区別して扱う
    # （leapすると新規ノード学習になる）。
    PENDING_MISS_ID = "__unresolved__"

    def __init__(self, theta: Optional[float] = None, rng: Optional[random.Random] = None):
        theta = dynamics.resolve(theta, "theta_initial")
        self.H_pre: dict[str, float] = {}   # 入力時のノードミスH（軽い）
        self.H_post: dict[str, float] = {}  # 応答後のユーザー反応H（重い）
        self.theta = theta
        self.theta_base = theta  # 弛緩の下限（設計書 §2 「初期値2.0、動的調整」）
        self.history: list[HistoryEntry] = []
        self._seq_counter = 0
        self.drift_checkpoint_seq = 0  # 前回のドリフト集計位置（M_Δ相の二重集計を防ぐ）
        # θ_eff の揺動用。テストから差し替えられるよう外部注入可能にする。
        self._rng = rng or random.Random()

    # --- H_pre 更新 ---

    def on_miss(self, context_node_id: Optional[str] = None):
        """
        未知入力のHを積む。context_node_id が None（＝十分に似た既存ノードが
        無い）なら PENDING_MISS_ID に積む。無関係なノードへ積むと、
        そのノードが後で誤って修正・隔離の対象に選ばれてしまう。
        """
        self._add_pre(context_node_id or self.PENDING_MISS_ID, 0.5, "miss")

    def on_partial(self, node_id: str):
        self._add_pre(node_id, 0.2, "partial")

    def on_exact(self, node_id: str):
        self._mul_pre(node_id, 0.8, "exact")

    # --- H_post 更新（ユーザー反応） ---

    def on_deny(self, node_id: str):
        self._add_post(node_id, 1.0, "deny")

    def on_rephrase(self, node_id: str):
        self._add_post(node_id, 0.3, "rephrase")

    def on_agree(self, node_id: str):
        self._mul_post(node_id, 0.7, "agree")

    def on_silence(self, node_id: str):
        self._add_post(node_id, 0.5, "silence") # 設計書 v0.3 §3.2 に合わせて 0.5 に変更

    # --- leap 判定 ---

    # H_pre / H_post の合成比率。H_pre は軽め（入力ミス）、H_post は重め（ユーザー反応）。
    H_PRE_WEIGHT = 0.4

    def _g_xi(self, pressure: float) -> float:
        """
        Core §6.2 の g(ξ)。ξ は閾値に直接加算されるのではなく、
        この関数を介して跳躍境界そのものを揺らす。

        二成分を持つ：
          系統成分 : ξ が溜まるほど θ_eff を下げる。ノード化できない残余は
                     「現在のM_Bが世界を捉えきれていない」ことの指標なので、
                     再編を起こしやすくする方向に働く
          揺動成分 : ξ が溜まるほど境界のブレ幅が広がる。Core が「揺らす」と
                     書くとおり、境界は決定的な線ではなくなる

        ξ圧が0のときは厳密に0を返す（ξが無ければ θ_eff == θ）。
        """
        if pressure <= 0:
            return 0.0
        cfg = dynamics.CONFIG
        systematic = -cfg.xi_drop_ratio * pressure
        stochastic = self._rng.uniform(-1.0, 1.0) * cfg.xi_jitter_ratio * pressure
        return self.theta * (systematic + stochastic)

    def theta_eff(self, pressure: float = 0.0) -> float:
        """
        実効跳躍閾値 θ_eff(t) = θ + g(ξ(t))（Core §6.2）。
        揺動成分があるため、同じ引数でも呼ぶたびに値が変わりうる。
        1ターンに1回だけ評価すること。
        """
        return self.theta + self._g_xi(pressure)

    def merged_h(self, node_id: str) -> float:
        """そのノードの合成H（H_pre×重み + H_post）。"""
        return self.H_pre.get(node_id, 0.0) * self.H_PRE_WEIGHT + self.H_post.get(node_id, 0.0)

    def should_leap(self, pressure: float = 0.0) -> tuple[bool, str]:
        merged = {}
        for nid, v in self.H_pre.items():
            merged[nid] = merged.get(nid, 0) + v * self.H_PRE_WEIGHT
        for nid, v in self.H_post.items():
            merged[nid] = merged.get(nid, 0) + v
        if not merged:
            return False, ""
        max_id = max(merged, key=lambda k: merged[k])
        if merged[max_id] > self.theta_eff(pressure):
            return True, max_id
        return False, ""

    def leap_done(self, node_id: str):
        # H_pre側の蓄積を放置すると、leap直後にも閾値超過状態が残ってしまうため、
        # H_pre/H_post 両方を弱める（再編成された領域全体を鎮める）。
        self.H_pre[node_id] = self.H_pre.get(node_id, 0) * 0.3
        self.H_post[node_id] = self.H_post.get(node_id, 0) * 0.3
        cfg = dynamics.CONFIG
        self.theta = min(self.theta * cfg.theta_raise_on_leap, cfg.theta_max)

    def dissipate(self, rates: Dict[str, float]) -> None:
        """
        dH_vec/dt の散逸項 −A·H_vec を1ステップ適用する（NN借用 v0.1 §4）。

        rates はノードごとの散逸速度 a_k = γ·λ_k。慣性の強い（＝M_Bの得意な）
        方向ほど速く熱を逃がし、弱い方向には熱が残る。

        以前は H が自然に減る経路が無く、完全ヒット・同意・leap という
        離散イベントでしか下がらなかった。そのため「M_B の苦手な方向に
        熱が蓄積する」という指向性が生まれず、どのノードも同じ速度で
        しか冷めなかった。
        """
        for nid, rate in rates.items():
            factor = 1.0 - max(0.0, min(1.0, rate))
            if nid in self.H_pre:
                self.H_pre[nid] *= factor
            if nid in self.H_post:
                self.H_post[nid] *= factor

    def relax_theta(self, factor: Optional[float] = None):
        """
        θを初期値へ向けてゆっくり戻す（M_Δ相から呼ばれる）。

        leap_done() の θ×1.05 だけだと閾値は単調増加のラチェットになり、
        30回ほどleapした時点で上限5.0に張り付いて二度と下がらない。
        設計書 §2 は θ を「動的調整」と定めており、再編成が落ち着いた
        期間には緩んで再び反応できるようになる必要がある。
        theta_base を下限とし、それ以下には緩まない。
        """
        factor = dynamics.resolve(factor, "theta_relax")
        self.theta = max(self.theta * factor, self.theta_base)

    def forget(self, node_id: str):
        """
        あるノードIDのH蓄積を完全に破棄する。

        M_Δ相で退場したノードや、__llm__ / __crisis__ / __none__ といった
        実ノードに対応しない疑似IDにHが溜まると、修正対象が存在しないため
        leapで消化できない。それが毎ターン should_leap() の最大値を占め続け、
        実在ノードのleapが永久に起きなくなる（＝学習が止まる）。
        """
        self.H_pre.pop(node_id, None)
        self.H_post.pop(node_id, None)

    def prune(self, valid_node_ids) -> int:
        """
        グラフに存在しないノードIDのH蓄積をまとめて破棄する。破棄件数を返す。
        M_Δ相の retire_dead_nodes() 後に呼ぶことで、退場済みノードのHが
        永久に残り続けるのを防ぐ。
        PENDING_MISS_ID は実ノードではないが未解決入力の正当な蓄積先
        なので、退場処理の巻き添えにしない。
        """
        valid = set(valid_node_ids) | {self.PENDING_MISS_ID}
        stale = (set(self.H_pre) | set(self.H_post)) - valid
        for nid in stale:
            self.forget(nid)
        return len(stale)

    def last_event_seq(self, node_id: str) -> int:
        """そのノードに最後に起きたイベントの通番。leapの追跡用。"""
        for entry in reversed(self.history):
            if entry.node_id == node_id:
                return entry.seq
        return 0

    def dominant_cause(self, node_id: str) -> str:
        """
        そのノードのHを最も押し上げた原因を返す。leapの記録用で、
        制御には使わない。
        """
        weights = {"deny": 0.0, "rephrase": 0.0, "miss": 0.0, "silence": 0.0}
        for entry in self.history:
            if entry.node_id == node_id and entry.event in weights:
                weights[entry.event] += abs(entry.delta)
        cause = max(weights, key=lambda k: weights[k])
        return cause if weights[cause] > 0 else "unknown"

    def on_llm_call(self, node_id: str = "__llm__"):
        self._log(node_id, "llm_call", 0.1) # LLM呼び出しも履歴として記録

    def resolve_miss(self, context_node_id: Optional[str] = None, factor: float = 0.3):
        """
        未知入力がH閾値を待たずに新規ノード生成（ドメイン信用度による
        早期相談など）で解決された場合、その原因となったmiss分の
        H_preを軽減する。放置すると、たまたま近くにいた無関係な
        既存ノードにHが積み上がり続け、後で誤って修正対象に
        選ばれてしまう。
        """
        nid = context_node_id or self.PENDING_MISS_ID
        if nid in self.H_pre:
            self.H_pre[nid] *= factor
            self._log(nid, "miss_resolved", 0.0)

    # --- 状態表示 ---

    def summary(self, pressure: float = 0.0) -> str:
        max_pre = max(self.H_pre.values(), default=0.0)
        max_post = max(self.H_post.values(), default=0.0)
        return (f"H_pre_max={max_pre:.2f}  H_post_max={max_post:.2f}  "
                f"θ={self.theta:.2f}  ξ圧={pressure:.2f}  θ_eff≈{self.theta_eff(pressure):.2f}")

    def hot_nodes(self, top: int = 3) -> list[tuple[str, float]]:
        merged = {}
        for nid, v in self.H_pre.items():
            merged[nid] = merged.get(nid, 0) + v * self.H_PRE_WEIGHT
        for nid, v in self.H_post.items():
            merged[nid] = merged.get(nid, 0) + v
        return sorted(merged.items(), key=lambda x: x[1], reverse=True)[:top]

    def drift_deltas(self) -> Dict[str, int]:
        """
        前回のM_Δ代謝（チェックポイント）以降に発生したイベントだけを集計する。
        毎回history全体を数え直すと同じイベントが何度もdrift_factorに
        加算されてしまうため、seqでの差分集計に変更。
        """
        new_events = [e for e in self.history if e.seq > self.drift_checkpoint_seq]
        self.drift_checkpoint_seq = self._seq_counter
        counts = {"deny": 0, "agree": 0, "llm_usage": 0}
        for e in new_events:
            if e.event == "deny":
                counts["deny"] += 1
            elif e.event == "agree":
                counts["agree"] += 1
            elif e.event == "llm_call":
                counts["llm_usage"] += 1
        return counts

    # --- 永続化 ---

    def to_dict(self) -> dict:
        return {
            "H_pre": self.H_pre,
            "H_post": self.H_post,
            "theta": self.theta,
            "theta_base": self.theta_base,
            "history": [asdict(e) for e in self.history],
            "seq_counter": self._seq_counter,
            "drift_checkpoint_seq": self.drift_checkpoint_seq,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "HState":
        h = cls(theta=data.get("theta"))
        # theta_base 未保存の旧セッションでは、既に上がりきったthetaを
        # 下限として固定してしまわないよう既定値2.0に戻す。
        h.theta_base = data.get("theta_base", dynamics.CONFIG.theta_initial)
        h.H_pre = data.get("H_pre", {})
        h.H_post = data.get("H_post", {})
        h.history = [HistoryEntry(**e) for e in data.get("history", [])]
        h._seq_counter = data.get("seq_counter", 0)
        h.drift_checkpoint_seq = data.get("drift_checkpoint_seq", 0)
        return h

    # --- 内部ヘルパー ---

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
