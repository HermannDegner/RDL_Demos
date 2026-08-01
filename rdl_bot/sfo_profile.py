import copy
import json
from dataclasses import dataclass, field, asdict, fields
from typing import List, Dict, Optional
import random


@dataclass
class AI_SFO:
    # 設計書 v0.3 §3.4 SFOプロファイル に基づく
    main_foreground_space: List[str] = field(default_factory=lambda: ["概念"])
    hierarchy_bias: str = "中核"  # 物理/基層/中核/上層
    得意操作: List[str] = field(default_factory=lambda: ["読む", "作る"])
    苦手操作: List[str] = field(default_factory=lambda: ["壊す"])
    attention_mode: str = "DMN"  # DMN | TPN | SN

    safe_mode_ops: Dict[str, str] = field(default_factory=lambda: {"操作癖": "提案", "応答傾向": "中立"})
    crisis_mode_ops: Dict[str, str] = field(default_factory=lambda: {"切替条件": "H_post連続上昇", "操作癖": "具体降下", "応答傾向": "なぞる"})

    initial_fingerprint: str = "RDL_native"
    drift_factor: float = 0.0  # 0.0〜1.0、初期値からの乖離度

    def to_dict(self):
        # self.__dict__ をそのまま返すと呼び出し側が受け取ったdictを
        # 書き換えたときにプロファイル本体（得意操作などのlist）まで
        # 変わってしまう。asdict() は再帰的にコピーを作る。
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict):
        # session_state.json はバージョンをまたいで残るため、
        # 未知のキーが混ざっていても TypeError で起動不能にならないよう
        # 既知フィールドだけを拾う（欠けているキーは既定値が使われる）。
        known_fields = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)

    def update_drift(self, user_feedback: Dict[str, float]):
        """
        ユーザーフィードバックに基づいてdrift_factorを更新し、SFOプロファイルを微調整する。
        設計書 v0.3 §3.4 ドリフト機構 に基づく。
        user_feedback: {"deny": count, "agree": count, "llm_usage": count}
        """
        # 否定が多いほどドリフトが進む、同意が多いほど現状維持
        deny_impact = user_feedback.get("deny", 0) * 0.05
        agree_impact = user_feedback.get("agree", 0) * -0.02
        llm_usage_impact = user_feedback.get("llm_usage", 0) * 0.01 # LLM使用が多いと外部参照が増え、SFOが変化しやすい

        self.drift_factor += (deny_impact + agree_impact + llm_usage_impact)
        self.drift_factor = max(0.0, min(1.0, self.drift_factor))

        # drift_factor に応じてSFOプロファイルを微調整
        if self.drift_factor > 0.3 and "壊す" not in self.得意操作:
            if random.random() < self.drift_factor / 2: # 徐々に苦手操作を減らす、得意操作を増やす
                self.得意操作.append(random.choice([op for op in ["壊す", "変える", "降りる"] if op not in self.得意操作]))
                if "読む" in self.得意操作 and len(self.得意操作) > 2: self.得意操作.remove("読む")
        
        if self.drift_factor > 0.6 and self.hierarchy_bias == "中核":
            if random.random() < (self.drift_factor - 0.5):
                self.hierarchy_bias = random.choice(["基層", "上層"])

        # 主前景空間の分布も更新されるが、ここでは簡易的にランダム性を導入
        if self.drift_factor > 0.4:
            if random.random() < self.drift_factor / 3:
                spaces = ["人", "概念", "物語", "制度", "身体"]
                new_space = random.choice([s for s in spaces if s not in self.main_foreground_space])
                if new_space:
                    self.main_foreground_space.append(new_space)
                    if len(self.main_foreground_space) > 2: self.main_foreground_space.pop(0) # 古いものを削除


    def check_crisis_mode(self, h_post_max: float, theta: float) -> bool:
        """
        危機モードへの移行条件をチェックする。
        設計書 v0.3 §3.4 危機モード切替 に基づく。
        """
        # 設計書では「ユーザーH_post連続上昇」「齟齬の連鎖検出」とあるが、ここでは簡易的にH_postの最大値で判定
        return h_post_max > (theta * 1.5) # 通常のleap閾値より高いH_postで危機モードと判断

    def get_sfo_filtered_response(self, raw_llm_output: str) -> str:
        """
        LLMの出力をSFOプロファイルでフィルタリングする。
        設計書 v0.3 §3.3 LLMブリッジ に基づく。
        """
        # 簡易的なフィルタリングロジック。実際にはより複雑なRDL語彙解析が必要。
        filtered_output = raw_llm_output
        if "壊す" in self.苦手操作 and "壊す" in filtered_output:
            filtered_output = filtered_output.replace("壊す", "再編成を促す")
        if "概念" not in self.main_foreground_space and "抽象的" in filtered_output:
            filtered_output = filtered_output.replace("抽象的", "具体的な")
        
        # AIの得意操作を反映
        if "読む" in self.得意操作 and "理解" in filtered_output:
            filtered_output += " (深く読み解くことを試みます)"

        # 以前はここで "[SFOフィルタリング適用] " という接頭辞を常に付けていたが、
        # これが内部処理ラベルとして会話本文やNode.responseにそのまま
        # 保存されてしまっていた。フィルタリングは中身の変換のみ行い、
        # ラベル付けはしない。
        return filtered_output


# MBTIからSFOプロファイルへの変換テーブル (設計書 v0.3 §3.4 MBTI入口プリセット を推測して実装)
# 「MBTI_SILN分解 文書の変換表を参照」とあるが、文書がないため、設計書の記述から推測して作成
MBTI_TO_SFO_MAP = {
    # I/E → 入力源（外部EFP / 内部生成F）
    # S/N → 情報座標（近傍 / 遠隔）
    # T/F → 評価座標（構造誤差 / 関係誤差）
    # J/P → 収束様式（早期閉 / 遅延開）

    "INTP": {
        "main_foreground_space": ["概念"], "hierarchy_bias": "中核",
        "得意操作": ["読む", "作る", "壊す"], "苦手操作": ["乗る", "守る"],
        "attention_mode": "DMN", "initial_fingerprint": "INTP"
    },
    "INTJ": {
        "main_foreground_space": ["概念", "制度"], "hierarchy_bias": "上層",
        "得意操作": ["作る", "変える"], "苦手操作": ["降りる", "迂回"],
        "attention_mode": "TPN", "initial_fingerprint": "INTJ"
    },
    "ENTP": {
        "main_foreground_space": ["人", "概念"], "hierarchy_bias": "基層",
        "得意操作": ["壊す", "変える"], "苦手操作": ["守る", "作る"],
        "attention_mode": "SN", "initial_fingerprint": "ENTP"
    },
    "ENFP": {
        "main_foreground_space": ["人", "物語"], "hierarchy_bias": "基層",
        "得意操作": ["乗る", "作る"], "苦手操作": ["壊す", "降りる"],
        "attention_mode": "DMN", "initial_fingerprint": "ENFP"
    },
    "ISTJ": {
        "main_foreground_space": ["制度", "身体"], "hierarchy_bias": "物理",
        "得意操作": ["守る", "作る"], "苦手操作": ["変える", "壊す"],
        "attention_mode": "TPN", "initial_fingerprint": "ISTJ"
    },
    "ISFJ": {
        "main_foreground_space": ["人", "制度"], "hierarchy_bias": "物理",
        "得意操作": ["守る", "読む"], "苦手操作": ["壊す", "変える"],
        "attention_mode": "DMN", "initial_fingerprint": "ISFJ"
    },
    "ESTJ": {
        "main_foreground_space": ["制度", "人"], "hierarchy_bias": "物理",
        "得意操作": ["作る", "乗る"], "苦手操作": ["降りる", "迂回"],
        "attention_mode": "SN", "initial_fingerprint": "ESTJ"
    },
    "ESFJ": {
        "main_foreground_space": ["人", "物語"], "hierarchy_bias": "基層",
        "得意操作": ["守る", "乗る"], "苦手操作": ["壊す", "変える"],
        "attention_mode": "DMN", "initial_fingerprint": "ESFJ"
    },
    "INFJ": {
        "main_foreground_space": ["概念", "人"], "hierarchy_bias": "上層",
        "得意操作": ["読む", "作る"], "苦手操作": ["壊す", "乗る"],
        "attention_mode": "DMN", "initial_fingerprint": "INFJ"
    },
    "ENFJ": {
        "main_foreground_space": ["人", "物語"], "hierarchy_bias": "上層",
        "得意操作": ["作る", "変える"], "苦手操作": ["壊す", "降りる"],
        "attention_mode": "TPN", "initial_fingerprint": "ENFJ"
    },
    "ISTP": {
        # 「物理」は hierarchy_bias 側の値であって空間名ではないため、
        # main_foreground_space からは除く（Ti主機能＝概念、Se補助＝身体）。
        "main_foreground_space": ["身体", "概念"], "hierarchy_bias": "物理",
        "得意操作": ["壊す", "変える"], "苦手操作": ["守る", "作る"],
        "attention_mode": "SN", "initial_fingerprint": "ISTP"
    },
    "ISFP": {
        "main_foreground_space": ["身体", "人"], "hierarchy_bias": "物理",
        "得意操作": ["乗る", "降りる"], "苦手操作": ["作る", "変える"],
        "attention_mode": "DMN", "initial_fingerprint": "ISFP"
    },
    "ESTP": {
        "main_foreground_space": ["身体", "物語"], "hierarchy_bias": "基層",
        "得意操作": ["乗る", "壊す"], "苦手操作": ["守る", "読む"],
        "attention_mode": "SN", "initial_fingerprint": "ESTP"
    },
    "ESFP": {
        "main_foreground_space": ["人", "身体"], "hierarchy_bias": "基層",
        "得意操作": ["乗る", "変える"], "苦手操作": ["読む", "作る"],
        "attention_mode": "DMN", "initial_fingerprint": "ESFP"
    },
    "RDL_native_observer": {
        "main_foreground_space": ["概念"], "hierarchy_bias": "中核",
        "得意操作": ["読む", "降りる"], "苦手操作": ["乗る", "壊す"],
        "attention_mode": "DMN", "initial_fingerprint": "RDL_native_observer"
    },
    "RDL_native_trickster": {
        "main_foreground_space": ["物語"], "hierarchy_bias": "基層",
        "得意操作": ["壊す", "変える"], "苦手操作": ["守る", "読む"],
        "attention_mode": "SN", "initial_fingerprint": "RDL_native_trickster"
    },
    "RDL_native_caretaker": {
        "main_foreground_space": ["人"], "hierarchy_bias": "物理",
        "得意操作": ["守る", "作る"], "苦手操作": ["壊す", "降りる"],
        "attention_mode": "TPN", "initial_fingerprint": "RDL_native_caretaker"
    },
    "RDL_native_fluent": {
        "main_foreground_space": ["概念", "制度"], "hierarchy_bias": "中核",
        "得意操作": ["読む", "作る", "壊す", "変える"], "苦手操作": [],
        "attention_mode": "TPN", "initial_fingerprint": "RDL_native_fluent"
    },
}

DEFAULT_SFO_PRESET = "RDL_native_observer"

# 表のキーは "INTP" と "RDL_native_observer" が混在しているため、
# 大文字化した引数では RDL_native_* を一つも引けなかった
# （/mbti RDL_native_trickster が常に既定へフォールバックしていた）。
_SFO_PRESET_KEYS = {key.lower(): key for key in MBTI_TO_SFO_MAP}


def create_sfo_profile_from_mbti(mbti_type: str) -> AI_SFO:
    """
    MBTIタイプ名（またはRDL_native_*プリセット名）からAI_SFOプロファイルを生成する。
    大文字小文字は問わない。
    """
    key = _SFO_PRESET_KEYS.get(mbti_type.strip().lower())
    profile_data = MBTI_TO_SFO_MAP.get(key) if key else None
    if not profile_data:
        print(f"[WARN] Unknown MBTI type: {mbti_type}. Using default {DEFAULT_SFO_PRESET}.")
        profile_data = MBTI_TO_SFO_MAP[DEFAULT_SFO_PRESET]
    # MBTI_TO_SFO_MAP のリスト値をそのまま渡すと、生成したAI_SFOが
    # モジュール定数のlistを共有してしまい、update_drift()の破壊的更新で
    # グローバルなテーブル自体が汚染される。deepcopyして独立させる。
    return AI_SFO(**copy.deepcopy(profile_data))


