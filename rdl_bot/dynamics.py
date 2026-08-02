"""
dynamics.py
動態係数の一元管理。

θ_eff・整合側 dM_B/dt・κ(M_B)・散逸行列 A の係数は、Core にも借用実装層にも
具体的な決定則が無い（NN借用 v0.1 の残課題「η・λ・α・β・γ・M_0 の具体的な
決定則」がまさにこれ）。つまり**実際に動かした感触でしか決まらない**。

そのためコード中に散らさず、ここに集約して data/dynamics_config.json から
上書きできるようにしてある。調整のたびにコードを触る必要はない。

    {"dissipation_gamma": 0.02, "kappa_m0": 8.0}

のように、変えたいキーだけ書けばよい（未知のキーは無視される）。
"""

import json
from dataclasses import dataclass, asdict, fields
from typing import Optional


@dataclass
class DynamicsConfig:
    # --- 跳躍閾値 θ と θ_eff = θ + g(ξ)（Core §6.2）---
    theta_initial: float = 2.0          # 初期閾値。theta_base（緩和の下限）も兼ねる
    theta_max: float = 5.0              # leap による上昇の上限
    theta_raise_on_leap: float = 1.05   # leap 1回あたりの上昇率
    theta_relax: float = 0.97           # M_Δ相での初期値へ向けた緩和率

    xi_saturation: float = 10.0         # ξプールがこの件数でξ圧1.0に飽和
    xi_drop_ratio: float = 0.25         # ξ圧最大のとき θ を何割下げるか（再編圧）
    xi_jitter_ratio: float = 0.10       # ξ圧最大のときの境界の揺れ幅

    # --- 整合側の dM_B/dt（Core §6.1）---
    align_rate_exact: float = 0.04      # 完全一致で V_B に沿って動く量
    align_rate_partial: float = 0.02    # 部分一致（V_B に部分的に沿う）
    alignment_ceiling: float = 0.9      # 整合だけで到達できる confidence の上限

    # --- κ(M_B) = exp(-‖M_B‖/M_0)（NN借用 v0.1 §5）---
    kappa_m0: float = 5.0               # 基準慣性スケール。小さいほど早く固まる
    kappa_hitl_threshold: float = 0.15  # これ未満で「自力修正不能」と判定
    inertia_usage_weight: float = 0.3   # ‖M_B‖ への使用回数の寄与
    inertia_approval_weight: float = 0.5  # ‖M_B‖ への承認回数の寄与

    # --- 散逸行列 A の対角成分 a_k = γ·λ_k（NN借用 v0.1 §4）---
    dissipation_gamma: float = 0.01     # 慣性あたりの散逸速度
    dissipation_cap: float = 0.15       # 1ターンで冷める割合の上限

    # --- E = F(t+Δ) − M_B·F(t)（Core §2.3）---
    # H への注入利得 gain_i。H_i = decay_i·H_i + gain_i·E_i の gain 側。
    # decay 側は散逸行列 A（上）が担うので、ここには置かない。
    e_gain_match: float = 0.8           # 「入力を捉えられる」予測が外れた分
    e_gain_acceptance: float = 1.4      # 「応答が受け入れられる」予測が外れた分

    # 次に来る入力を捉えられるかの予測（EMA）の追従速度
    match_prediction_smoothing: float = 0.12
    # 次元ごとの予測信頼度の追従速度（Living Field と同じ 0.035）
    reliability_smoothing: float = 0.035

    # 応答を担うノードが無い場合（グラフ内合成・LLM生応答・危機モード）の
    # 受容予測。内部に根拠が無いので低めに置く。
    fallback_predicted_acceptance: float = 0.3

    # ユーザー反応の観測値。E = |observed − predicted| の observed 側。
    observed_agree: float = 1.0
    observed_rephrase: float = 0.5
    observed_deny: float = 0.0
    observed_silence: float = 0.25      # 弱い否定シグナル

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "DynamicsConfig":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})


# 実行時に参照される現在の係数。load_dynamics_config() で差し替える。
CONFIG = DynamicsConfig()


def configure(config: DynamicsConfig) -> None:
    """現在の係数を差し替える。"""
    global CONFIG
    CONFIG = config


def load_dynamics_config(path: str) -> DynamicsConfig:
    """
    動態係数を読み込む。ファイルが無い/壊れていれば既定値。
    コードを触らずに data/dynamics_config.json を置くだけで調整できる。
    """
    try:
        with open(path, encoding="utf-8") as f:
            return DynamicsConfig.from_dict(json.load(f))
    except FileNotFoundError:
        return DynamicsConfig()
    except json.JSONDecodeError:
        print(f"  [ERROR] 動態係数のJSONが壊れています ({path})。既定値を使います。")
        return DynamicsConfig()


def resolve(value: Optional[float], field_name: str) -> float:
    """引数が None なら現在の係数から解決する。"""
    return getattr(CONFIG, field_name) if value is None else value
