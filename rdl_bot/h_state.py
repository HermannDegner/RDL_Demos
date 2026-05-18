"""
h_state.py
H_vec 管理: 誤差蓄積の観測
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class HistoryEntry:
    timestamp: str
    node_id: str
    event: str       # miss / partial / exact / deny / rephrase / agree / silence
    delta: float


class HState:
    def __init__(self, theta: float = 2.0):
        self.H_pre: dict[str, float] = {}   # 入力時のノードミスH（軽い）
        self.H_post: dict[str, float] = {}  # 応答後のユーザー反応H（重い）
        self.theta = theta
        self.history: list[HistoryEntry] = []

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
        self._add_post(node_id, 0.5, "silence")

    # --- leap 判定 ---

    def should_leap(self) -> tuple[bool, str]:
        if not self.H_post:
            return False, ""
        max_id = max(self.H_post, key=lambda k: self.H_post[k])
        if self.H_post[max_id] > self.theta:
            return True, max_id
        return False, ""

    def leap_done(self, node_id: str):
        self.H_post[node_id] = self.H_post.get(node_id, 0) * 0.3
        self.theta = min(self.theta * 1.05, 5.0)

    # --- 状態表示 ---

    def summary(self) -> str:
        max_pre = max(self.H_pre.values(), default=0.0)
        max_post = max(self.H_post.values(), default=0.0)
        return f"H_pre_max={max_pre:.2f}  H_post_max={max_post:.2f}  θ={self.theta:.2f}"

    def hot_nodes(self, top: int = 3) -> list[tuple[str, float]]:
        merged = {}
        for nid, v in self.H_pre.items():
            merged[nid] = merged.get(nid, 0) + v * 0.4
        for nid, v in self.H_post.items():
            merged[nid] = merged.get(nid, 0) + v
        return sorted(merged.items(), key=lambda x: x[1], reverse=True)[:top]

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
        self.history.append(HistoryEntry(
            timestamp=datetime.now().isoformat(),
            node_id=nid,
            event=event,
            delta=delta,
        ))
        if len(self.history) > 500:
            self.history = self.history[-500:]
