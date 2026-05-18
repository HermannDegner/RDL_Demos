"""
node_graph.py
ノードグラフ: ユーザーM_B断面の蓄積
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional


class Node:
    def __init__(
        self,
        inputs: list[str],
        rdl_type: str,
        spatial_tag: str = "概念",
        response: Optional[str] = None,
        source: str = "manual",
        confidence: float = 0.8,
        ttl: int = 200,
    ):
        self.id = str(uuid.uuid4())[:8]
        self.input = inputs                  # マッチする入力パターン
        self.rdl_type = rdl_type             # 関係性開始 / H過負荷 / ...
        self.spatial_tag = spatial_tag       # 人/概念/物語/制度/身体
        self.response = response             # 返答テンプレート（Noneなら合成）
        self.confidence = confidence         # 0.0〜1.0
        self.ttl = ttl                       # 残存ステップ数
        self.phase = "M_lat"                 # M_lat → M_act
        self.source = source                 # manual / llm_seed / llm_learned / graph_composed
        self.relations: list[str] = []       # 関連ノードID（W_ij）
        self.activation_count = 0            # 安定化カウント
        self.created_at = datetime.now().isoformat()
        self.last_used = self.created_at

    def touch(self):
        self.last_used = datetime.now().isoformat()
        self.activation_count += 1
        # N=3 で M_act 昇格（最初は低め、運用で調整）
        if self.activation_count >= 3 and self.phase == "M_lat":
            self.phase = "M_act"

    def decay_confidence(self, rate: float = 0.995):
        self.confidence *= rate
        self.ttl -= 1

    def to_dict(self) -> dict:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d: dict) -> "Node":
        n = cls.__new__(cls)
        n.__dict__.update(d)
        return n


class NodeGraph:
    def __init__(self, path: str = "data/graph.json"):
        self.path = Path(path)
        self.nodes: dict[str, Node] = {}
        self.load()

    def add(self, node: Node):
        self.nodes[node.id] = node

    def search(self, text: str) -> tuple[Optional[Node], str]:
        """
        入力テキストにマッチするノードを返す。
        返り値: (node, match_type)
        match_type: "exact" / "partial" / "miss"
        """
        text_lower = text.lower()
        best_node = None
        best_score = 0.0
        match_type = "miss"

        for node in self.nodes.values():
            for pattern in node.input:
                if pattern.lower() == text_lower:
                    return node, "exact"
                if pattern.lower() in text_lower or text_lower in pattern.lower():
                    score = len(pattern) / max(len(text), 1)
                    if score > best_score:
                        best_score = score
                        best_node = node
                        match_type = "partial"

        if best_score < 0.3:
            return None, "miss"
        return best_node, match_type

    def get_by_id(self, node_id: str) -> Optional[Node]:
        return self.nodes.get(node_id)

    def retire_dead_nodes(self):
        to_remove = [
            nid for nid, n in self.nodes.items()
            if n.ttl <= 0 and n.source == "llm_seed"
        ]
        for nid in to_remove:
            del self.nodes[nid]

    def stats(self) -> dict:
        total = len(self.nodes)
        by_source = {}
        by_phase = {"M_lat": 0, "M_act": 0}
        for n in self.nodes.values():
            by_source[n.source] = by_source.get(n.source, 0) + 1
            by_phase[n.phase] = by_phase.get(n.phase, 0) + 1
        return {"total": total, "by_source": by_source, "by_phase": by_phase}

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {nid: n.to_dict() for nid, n in self.nodes.items()}
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    def load(self):
        if self.path.exists():
            data = json.loads(self.path.read_text())
            self.nodes = {nid: Node.from_dict(d) for nid, d in data.items()}
