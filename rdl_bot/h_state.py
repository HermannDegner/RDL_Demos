"""
h_state.py
H_vec 管理: 誤差蓄積の観測
"""

from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class HistoryEntry:
    timestamp: str
    node_id: str
    event: str       # miss / partial / exact / deny / rephrase / agree / silence / llm_call
    delta: float
    seq: int = 0      # 通算イベント番号。history は500件でtrimされるがseqは増え続ける


class HState:
    def __init__(self, theta: float = 2.0):
        self.H_pre: dict[str, float] = {}   # 入力時のノードミスH（軽い）
        self.H_post: dict[str, float] = {}  # 応答後のユーザー反応H（重い）
        self.theta = theta
        self.history: list[HistoryEntry] = []
        self._seq_counter = 0
        self.drift_checkpoint_seq = 0  # 前回のドリフト集計位置（M_Δ相の二重集計を防ぐ）

    # --- H_pre 更新 ---

    def on_miss(self, context_node_id: str = "__none__"):
        self._add_pre(context_node_id, 0.5, "miss")

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

    def should_leap(self) -> tuple[bool, str]:
        merged = {}
        for nid, v in self.H_pre.items():
            merged[nid] = merged.get(nid, 0) + v * self.H_PRE_WEIGHT
        for nid, v in self.H_post.items():
            merged[nid] = merged.get(nid, 0) + v
        if not merged:
            return False, ""
        max_id = max(merged, key=lambda k: merged[k])
        if merged[max_id] > self.theta:
            return True, max_id
        return False, ""

    def leap_done(self, node_id: str):
        # H_pre側の蓄積を放置すると、leap直後にも閾値超過状態が残ってしまうため、
        # H_pre/H_post 両方を弱める（再編成された領域全体を鎮める）。
        self.H_pre[node_id] = self.H_pre.get(node_id, 0) * 0.3
        self.H_post[node_id] = self.H_post.get(node_id, 0) * 0.3
        self.theta = min(self.theta * 1.05, 5.0)

    def on_llm_call(self, node_id: str = "__llm__"):
        self._log(node_id, "llm_call", 0.1) # LLM呼び出しも履歴として記録

    def resolve_miss(self, context_node_id: str, factor: float = 0.3):
        """
        未知入力がH閾値を待たずに新規ノード生成（ドメイン信用度による
        早期相談など）で解決された場合、その原因となったmiss分の
        H_preを軽減する。放置すると、たまたま近くにいた無関係な
        既存ノードにHが積み上がり続け、後で誤って修正対象に
        選ばれてしまう。
        """
        if context_node_id in self.H_pre:
            self.H_pre[context_node_id] *= factor
            self._log(context_node_id, "miss_resolved", 0.0)

    # --- 状態表示 ---

    def summary(self) -> str:
        max_pre = max(self.H_pre.values(), default=0.0)
        max_post = max(self.H_post.values(), default=0.0)
        return f"H_pre_max={max_pre:.2f}  H_post_max={max_post:.2f}  θ={self.theta:.2f}"

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
            "history": [asdict(e) for e in self.history],
            "seq_counter": self._seq_counter,
            "drift_checkpoint_seq": self.drift_checkpoint_seq,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "HState":
        h = cls(theta=data.get("theta", 2.0))
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
