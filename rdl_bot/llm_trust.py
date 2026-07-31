"""
llm_trust.py
ドメイン（spatial_tag）ごとのLLM信用度モデル。

若いAIほど外部LLMへの信用度を高くしたほうが立ち上がりが速いが、
「若さ」はAI全体で一様に進むのではなく、空間ごとに内部経験が
蓄積した分だけ局所的に下がっていく、という考え方にもとづく。

    trust = trust_decay_scale / (trust_decay_scale + internal_experience)

internal_experience は「そのドメインでどれだけ内部知識が自力で
育っているか」の指標。単にノード数・使用頻度・confidenceを合算するだけだと、
LLMからただ教わっただけのseedを大量に入れた場合にも「経験豊富」と
誤判定してしまう（＝親から聞いた知識が増えただけで親を信用しなくなる）。
そのため、ノードのsource（教わっただけか、自分の相互作用で承認された
ものか）で重みを変え、ユーザー承認(approval_count)が増えるほど
出自に関わらず「自分で検証した経験」に近づくようにしてある。

すべて初期変数として外から変更できる
（data/llm_trust_config.json があれば起動時に上書きされる）。
"""

from dataclasses import dataclass, asdict, field, fields
from typing import Dict, Iterable, Optional


DEFAULT_SOURCE_WEIGHTS = {
    "llm_seed": 0.1,       # LLMに種まきされただけ。最も「教わっただけ」
    "llm_learned": 0.3,    # leap時にLLMが生成。まだ検証は薄い
    "graph_composed": 0.6, # 既存の内部知識同士の合成
    "manual": 0.8,         # 手動seed。最初から内部知識として与えられたもの
}


@dataclass
class LLMTrustConfig:
    # internal_experience=0 のとき trust は実質この値になる
    # （分母のスケールに過ぎない値を初期信用度と誤解しないよう、
    #  external_prior ではなく trust_decay_scale と呼ぶ）。
    max_trust: float = 0.95
    min_trust: float = 0.05
    trust_decay_scale: float = 0.9  # 大きいほど経験蓄積による信用度低下が緩やか

    node_weight: float = 1.0
    usage_weight: float = 0.3
    confidence_weight: float = 1.0

    # ノードのsourceごとの「内部経験としての重み」。0〜1。
    source_weights: Dict[str, float] = field(default_factory=lambda: dict(DEFAULT_SOURCE_WEIGHTS))
    default_source_weight: float = 0.5  # 未知sourceのフォールバック

    # ユーザー承認(y)の蓄積で、出自の重みから1.0（自分で検証済み）へ
    # 近づいていく速さ。approval_saturation回の承認でほぼ満額になる。
    approval_weight: float = 1.0
    approval_saturation: float = 5.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "LLMTrustConfig":
        known_fields = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)


class LLMTrust:
    def __init__(self, config: Optional[LLMTrustConfig] = None):
        self.config = config or LLMTrustConfig()

    def _node_experience_weight(self, node) -> float:
        """
        そのノードの内容が、どれだけ「自分で検証した経験」に
        近いかを0〜1で返す。出自(source)の基礎重みから始まり、
        ユーザー承認の蓄積で1.0に近づく。
        """
        cfg = self.config
        base = cfg.source_weights.get(node.source, cfg.default_source_weight)
        if cfg.approval_saturation > 0:
            approval_progress = min(1.0, node.approval_count / cfg.approval_saturation)
        else:
            approval_progress = 0.0
        return base + (1.0 - base) * cfg.approval_weight * approval_progress

    def internal_experience(self, graph, spatial_tag: str) -> float:
        """
        そのspatial_tagに属するアクティブノードから内部経験量を合成する。
        quarantined/deprecatedノードは「否定され続けている経験」なので
        カウントしない。
        """
        cfg = self.config
        exp = 0.0
        for node in graph.nodes.values():
            if node.spatial_tag != spatial_tag or node.status != "active":
                continue
            weight = self._node_experience_weight(node)
            exp += weight * (
                cfg.node_weight
                + cfg.usage_weight * node.usage_count
                + cfg.confidence_weight * node.confidence
            )
        return exp

    def trust_for(self, graph, spatial_tag: str) -> float:
        cfg = self.config
        exp = self.internal_experience(graph, spatial_tag)
        trust = cfg.trust_decay_scale / (cfg.trust_decay_scale + exp)
        return max(cfg.min_trust, min(cfg.max_trust, trust))

    def trust_by_domain(self, graph, spatial_tags: Iterable[str]) -> Dict[str, float]:
        return {tag: self.trust_for(graph, tag) for tag in spatial_tags}
