import json
import uuid
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Tuple


def _char_ngrams(text: str, n: int = 2) -> set:
    """
    日本語は分かち書きされていないため、空白split()による単語比較では
    ほぼ常に類似度ゼロになる。文字N-gramなら分かち書き不要で近傍比較できる。
    """
    text = text.strip()
    if not text:
        return set()
    if len(text) < n:
        return {text}
    return {text[i:i + n] for i in range(len(text) - n + 1)}


def _ngram_similarity(grams_a: set, grams_b: set) -> float:
    union = grams_a | grams_b
    if not union:
        return 0.0
    return len(grams_a & grams_b) / len(union)


@dataclass
class Node:
    id: str = field(init=False)
    inputs: List[str] = field(default_factory=list)
    rdl_type: str = "未分類"
    relations: List[str] = field(default_factory=list)  # NodeID[]
    response: Optional[str] = None
    confidence: float = 1.0
    ttl: int = 100  # Time To Live, 残存ステップ数
    usage_count: int = 0 # ユーザー相互作用回数
    phase: str = "M_lat"  # "M_lat" (潜在相) | "M_act" (活性相)
    status: str = "active"  # "active" | "quarantined" | "deprecated"
    source: str = "manual"  # "manual" | "llm_seed" | "llm_learned" | "graph_composed"
    spatial_tag: str = "概念"  # "人" | "概念" | "物語" | "制度" | "身体"
    counterexamples: List[Dict] = field(default_factory=list)  # 否定/言い換えの証跡
    approval_count: int = 0  # ユーザーが同意(y)した回数。出自に関わらず「自分で検証した経験」の指標
    created_at: str = field(init=False)
    last_used: str = field(init=False)

    def __post_init__(self):
        self.id = str(uuid.uuid4())
        self.created_at = datetime.now().isoformat()
        self.last_used = datetime.now().isoformat()

    def touch(self, ttl_refresh: int = 100):
        self.last_used = datetime.now().isoformat()
        # 実使用があったノードはTTLを更新し、経過ターン数だけで
        # 死滅しないようにする（不使用ノードとの区別のため）。
        self.ttl = max(self.ttl, ttl_refresh)

    def increment_usage(self, promotion_threshold: int = 3):
        self.usage_count += 1
        if self.phase == "M_lat" and self.usage_count >= promotion_threshold:
            self.phase = "M_act"
            # print(f"[INFO] Node {self.id} promoted to M_act") # デバッグ用

    def record_counterexample(self, user_input: str, reason: str):
        self.counterexamples.append({
            "input": user_input,
            "reason": reason,  # "deny" | "rephrase"
            "timestamp": datetime.now().isoformat(),
        })
        if len(self.counterexamples) > 50:
            self.counterexamples = self.counterexamples[-50:]

    def decay_confidence(self):
        # 設計書 v0.3 の M_Δ相 にある「低confidence・低使用頻度ノードのTTL減算と削除」を反映
        # TTLが0になったら confidence を急激に減衰させる
        if self.ttl > 0:
            self.ttl -= 1
        else:
            self.confidence *= 0.9  # TTLが切れたら徐々に減衰

    def to_dict(self):
        return {
            "id": self.id,
            "inputs": self.inputs,
            "rdl_type": self.rdl_type,
            "relations": self.relations,
            "response": self.response,
            "confidence": self.confidence,
            "ttl": self.ttl,
            "usage_count": self.usage_count,
            "phase": self.phase,
            "status": self.status,
            "source": self.source,
            "spatial_tag": self.spatial_tag,
            "counterexamples": self.counterexamples,
            "approval_count": self.approval_count,
            "created_at": self.created_at,
            "last_used": self.last_used,
        }

    @classmethod
    def from_dict(cls, data: Dict):
        node = cls(
            inputs=data.get("inputs", []),
            rdl_type=data.get("rdl_type", "未分類"),
            relations=data.get("relations", []),
            response=data.get("response"),
            confidence=data.get("confidence", 1.0),
            ttl=data.get("ttl", 100),
            usage_count=data.get("usage_count", 0),
            phase=data.get("phase", "M_lat"),
            status=data.get("status", "active"),
            source=data.get("source", "manual"),
            spatial_tag=data.get("spatial_tag", "概念"),
            counterexamples=data.get("counterexamples", []),
            approval_count=data.get("approval_count", 0),
        )
        node.id = data.get("id", str(uuid.uuid4()))
        node.created_at = data.get("created_at", datetime.now().isoformat())
        node.last_used = data.get("last_used", datetime.now().isoformat())
        return node


class NodeGraph:
    def __init__(self, filepath: str = "data/graph.json"):
        self.filepath = filepath
        self.nodes: Dict[str, Node] = {}
        self._load()

    def _load(self):
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                for node_data in data:
                    node = Node.from_dict(node_data)
                    self.nodes[node.id] = node
        except FileNotFoundError:
            # print(f"[INFO] Graph file not found: {self.filepath}. Starting with empty graph.")
            pass
        except json.JSONDecodeError:
            # 壊れたファイルを問答無用で空にすると全学習内容を失う。
            # 破損ファイルは退避して残し、空グラフで起動する。
            backup_path = self.filepath + ".corrupt"
            print(f"[ERROR] Could not decode JSON from {self.filepath}. Backing up to {backup_path} and starting with empty graph.")
            try:
                os.replace(self.filepath, backup_path)
            except OSError as e:
                print(f"[ERROR] Failed to back up corrupt graph file: {e}")
            self.nodes = {}

    def save(self):
        # dataディレクトリが存在しない場合は作成
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        # 直接書き込みだと途中で落ちた場合にJSONが壊れる。
        # 一時ファイルに書いてから os.replace() で原子的に差し替える。
        tmp_path = f"{self.filepath}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump([node.to_dict() for node in self.nodes.values()], f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self.filepath)

    def add(self, node: Node):
        self.nodes[node.id] = node

    def get_by_id(self, node_id: str) -> Optional[Node]:
        return self.nodes.get(node_id)

    def _resolve_active(self, node: Node, max_hops: int = 5) -> Optional[Node]:
        """
        deprecated（修正済みで後継ノードあり）は relations 経由で
        後継ノードへ透過的にリダイレクトする。
        quarantined（否定されたが後継未生成）は応答対象として使わず、
        None を返して miss 相当の扱いにフォールバックさせる。
        """
        seen = {node.id}
        current = node
        hops = 0
        while current.status == "deprecated" and current.relations and hops < max_hops:
            nxt = self.get_by_id(current.relations[-1])
            if not nxt or nxt.id in seen:
                break
            current = nxt
            seen.add(current.id)
            hops += 1
        # ループを抜けた時点でまだ active に到達していない場合
        # （relationsが無い/壊れている、hop上限に達した等）は、
        # quarantinedと同様に応答対象から外し miss 相当にする。
        if current.status != "active":
            return None
        return current

    def search(self, user_input: str) -> Tuple[Optional[Node], str, Optional[Node]]:
        """
        ユーザー入力に最も一致するノードを検索する。
        返り値: (node, match_type, nearest_node)
        match_type: "exact", "partial", "miss"
        """
        text_lower = user_input.lower()
        best_exact_node = None
        best_partial_node = None
        best_exact_score = 0.0
        best_partial_score = 0.0

        # nearest_node は HState の on_miss で使われるため、常に返す
        nearest_node = None
        max_similarity = -1.0
        text_grams = _char_ngrams(text_lower)

        for node in self.nodes.values():
            for pattern in node.inputs:
                pattern_lower = pattern.lower()
                # 完全一致に近いものを優先
                if text_lower == pattern_lower:
                    if node.confidence > best_exact_score:
                        best_exact_score = node.confidence
                        best_exact_node = node
                # 部分一致
                elif pattern_lower in text_lower or text_lower in pattern_lower:
                    # 部分一致のスコア = 短い方/長い方 * confidence。
                    # 以前は pattern/text だったため、長い登録パターンほど
                    # 過剰に高得点になる逆転現象があった。
                    shorter = min(len(pattern_lower), len(text_lower))
                    longer = max(len(pattern_lower), len(text_lower), 1)
                    score = (shorter / longer) * node.confidence
                    if score > best_partial_score:
                        best_partial_score = score
                        best_partial_node = node

                # 最近傍ノードの特定：文字N-gramのJaccard類似度で測る
                # （空白split()は日本語では機能しないため）
                similarity = _ngram_similarity(text_grams, _char_ngrams(pattern_lower))
                if similarity > max_similarity:
                    max_similarity = similarity
                    nearest_node = node

        # llm_seed の置換ロジックを考慮
        # ユーザー由来のノード（manual, llm_learned, graph_composed）を優先
        if best_exact_node:
            candidate = best_exact_node
            if candidate.source == "llm_seed":
                for node in self.nodes.values():
                    if (node.id != candidate.id and node.source != "llm_seed"
                            and user_input.lower() in [p.lower() for p in node.inputs]
                            and node.confidence > candidate.confidence):
                        candidate = node
                        break
            resolved = self._resolve_active(candidate)
            if resolved is not None:
                return resolved, "exact", resolved

        if best_partial_node:
            candidate = best_partial_node
            if candidate.source == "llm_seed":
                for node in self.nodes.values():
                    if (node.id != candidate.id and node.source != "llm_seed"
                            and (user_input.lower() in [p.lower() for p in node.inputs]
                                 or any(p.lower() in user_input.lower() for p in node.inputs))
                            and node.confidence > candidate.confidence):
                        candidate = node
                        break
            resolved = self._resolve_active(candidate)
            if resolved is not None:
                return resolved, "partial", resolved

        return None, "miss", nearest_node

    def top_k_similar(self, user_input: str, k: int = 3) -> List[Tuple[Node, float]]:
        """
        文字N-gram類似度で上位k件のアクティブノードを返す（類似度降順）。
        単一の最近傍ノードだけでドメイン判定などをすると、たまたま
        登録順が早いノードに引っ張られやすいため、複数件の投票に使う。
        """
        text_grams = _char_ngrams(user_input.lower())
        scored: List[Tuple[Node, float]] = []
        for node in self.nodes.values():
            if node.status != "active":
                continue
            best_sim = 0.0
            for pattern in node.inputs:
                sim = _ngram_similarity(text_grams, _char_ngrams(pattern.lower()))
                if sim > best_sim:
                    best_sim = sim
            if best_sim > 0:
                scored.append((node, best_sim))
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:k]

    def stats(self) -> Dict[str, int]:
        total = len(self.nodes)
        by_source = {}
        by_phase = {}
        for node in self.nodes.values():
            by_source[node.source] = by_source.get(node.source, 0) + 1
            by_phase[node.phase] = by_phase.get(node.phase, 0) + 1
        return {"total": total, "by_source": by_source, "by_phase": by_phase}

    def retire_dead_nodes(self):
        # 設計書 v0.3 の M_Δ相 にある「低confidence・低使用頻度ノードのTTL減算と削除」を反映
        # TTLが0かつconfidenceが低いノードは source を問わず削除する。
        initial_count = len(self.nodes)
        self.nodes = {nid: node for nid, node in self.nodes.items() if not (node.ttl <= 0 and node.confidence < 0.1)}

        if len(self.nodes) < initial_count:
            print(f"  [M_Δ相] {initial_count - len(self.nodes)} 個のノードを退場させました。")

    def update_relations(self, active_node_id: str, related_node_ids: List[str]):
        """
        W_ijエッジの張り直し（実使用パターンに基づく）のプレースホルダー。
        設計書 v0.3 §3.6 M_Δ相 に基づく。
        """
        # 現時点では単に relations リストを更新するのみ。複雑なロジックは今後の課題。
        active_node = self.get_by_id(active_node_id)
        if active_node:
            for rid in related_node_ids:
                if rid not in active_node.relations:
                    active_node.relations.append(rid)
            # 逆方向のエッジも考慮する場合はここに追加

    def merge_or_split_nodes(self):
        """
        類似ノード群のマージまたは分割のプレースホルダー。
        設計書 v0.3 §3.6 M_Δ相 に基づく。
        """
        # 複雑なロジックのため、現時点では実装しない。今後の課題。
        pass
