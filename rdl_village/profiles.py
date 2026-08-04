"""係数プロファイル。

RDL_Demos/rdl_system/profiles の reference profile を Python へ移植したもの。
係数をコードへ直接埋め込まず、個体・用途ごとに差し替え可能にする。
"""

from dataclasses import dataclass, field, replace


def clamp(value, low, high):
    return max(low, min(high, value))


@dataclass(frozen=True)
class BoundaryCoeffs:
    theta_base: float = 0.8
    theta_min: float = 0.28
    theta_max: float = 2.0
    xi_theta_weight: float = 0.26


@dataclass(frozen=True)
class NodeCoeffs:
    reliability: float = 0.7
    align_rate: float = 0.035
    reliability_min: float = 0.18
    reliability_max: float = 0.98
    xi_decay: float = 0.94
    xi_gain: float = 0.12
    xi_max: float = 1.2


@dataclass(frozen=True)
class HCoeffs:
    """H_i(t) = decay_i × H_i(t-1) + gain_i × E_i(t)（村§12.1）。

    gain は reference profile の 1.0 ではなく 0.3 を既定にしている。
    gain=1.0 / decay=0.9 では定常Hが誤差の10倍になり、θ（0.28〜0.8）を常時超えて
    Leapが飽和する。gain=3×(1-decay) とすると定常Hが誤差の約3倍に収まり、
    「持続的に3割以上外している構造」でLeapが立つ、という解釈可能な水準になる。
    """

    decay: float = 0.9
    gain: float = 0.3
    residual_after_leap: float = 0.28
    ceiling: float = 2.5
    channel_decay: dict = field(default_factory=dict)
    channel_gain: dict = field(default_factory=dict)

    def decay_for(self, channel):
        return self.channel_decay.get(channel, self.decay)

    def gain_for(self, channel):
        return self.channel_gain.get(channel, self.gain)


@dataclass(frozen=True)
class LeapCoeffs:
    cooldown_ticks: int = 10


@dataclass(frozen=True)
class DialogueCoeffs:
    node_ttl: int = 240
    ttl_recovery: int = 60
    confidence_gain: float = 0.06
    confidence_loss: float = 0.09
    activation_threshold: float = 0.62
    repetition_penalty: float = 0.22
    max_turns: int = 6


@dataclass(frozen=True)
class NeuroProfile:
    """基層パラメータの操作的近似（神経力学的基層構造 §1）。

    神経物質ラベルは生物学的実在の再現ではなく、個体の評価傾向・反応特性・
    重み付け機構を設計するための操作的近似として使う。
    """

    # ドーパミン系（探索・報酬）
    d1: float = 1.0  # 行動の実行促進
    d2: float = 1.0  # 行動の抑制・ブレーキ
    d3: float = 1.0  # 再現性確認・反復固定ループ
    d4: float = 1.0  # 退屈：誤差が少ない状態での仮想熱生成

    # セロトニン系（誤差許容度）。高いほど誤差熱が立ちにくい＝鈍感。
    serotonin: float = 1.0
    ht1: float = 1.0  # 5-HT1 誤差の減衰・鎮静
    ht3: float = 1.0  # 5-HT3 強制割り込み反応（緊急処理の入りやすさ）

    # オキシトシン系（自己拡張的重み付け）。B_self をどこまで広げるか。
    oxytocin: float = 0.5

    # ノルアドレナリン系（危険検知・優先度増幅）
    noradrenaline: float = 1.0

    @property
    def boredom_threshold(self):
        """この水準を下回る誤差が続くと退屈が立ちはじめる。

        誤差許容度が高い個体ほど「静かだ」と感じる帯が広い。
        """
        return clamp(0.14 * self.serotonin, 0.05, 0.35)


# 神経力学的基層構造 §2「個体差の設計」の類型に対応させたプリセット。
NEURO_PRESETS = {
    # 安定型。誤差熱が立ちにくく、退屈もしにくい。
    "farmer": NeuroProfile(d1=1.0, d4=0.8, serotonin=1.15, oxytocin=0.6, noradrenaline=0.9),
    # 繊細で探索的：ドーパミン高 × セロトニン低。小さな誤差にも反応し消耗しやすい。
    "forager": NeuroProfile(d1=1.2, d4=1.3, serotonin=0.75, ht1=0.9, oxytocin=0.4, noradrenaline=1.1),
    # 安定・群れ維持型：オキシトシン高 × ノルアドレナリン低。
    "keeper": NeuroProfile(d1=0.95, d4=0.7, serotonin=1.1, oxytocin=1.3, noradrenaline=0.7),
    # 鈍感・低探索。ブレーキが強い。
    "quiet": NeuroProfile(d1=0.85, d2=1.3, d4=0.6, serotonin=1.4, ht1=1.15, oxytocin=0.35, noradrenaline=0.85),
    # 群れ維持＋社交。
    "social": NeuroProfile(d1=1.05, d3=1.2, d4=1.0, serotonin=0.95, oxytocin=1.2, noradrenaline=0.8),
    # 危険大好き：ドーパミン高 × セロトニン高（多少の誤差では快が少ない）。
    "wanderer": NeuroProfile(d1=1.3, d2=0.8, d4=1.4, serotonin=1.25, oxytocin=0.3, noradrenaline=0.6),
}


def profile_for(base, neuro):
    """基層パラメータを係数プロファイルへ反映する。

    セロトニン＝誤差許容度は H のゲイン（誤差熱の立ちやすさ）へ、
    5-HT1＝鎮静は H の減衰（熱の抜けやすさ）へ写す。
    θ は共有のままにし、個体差は「熱の立ち方」から出す。
    """
    return base.merged(
        h={
            "gain": base.h.gain / clamp(neuro.serotonin, 0.4, 2.2),
            "decay": clamp(base.h.decay ** clamp(neuro.ht1, 0.5, 2.0), 0.6, 0.98),
        }
    )


@dataclass(frozen=True)
class Profile:
    id: str = "reference"
    boundary: BoundaryCoeffs = field(default_factory=BoundaryCoeffs)
    node: NodeCoeffs = field(default_factory=NodeCoeffs)
    h: HCoeffs = field(default_factory=HCoeffs)
    leap: LeapCoeffs = field(default_factory=LeapCoeffs)
    dialogue: DialogueCoeffs = field(default_factory=DialogueCoeffs)

    def merged(self, **sections):
        """セクション単位の上書き。profile.merged(boundary={"theta_base": 1.0}) の形で使う。"""
        updates = {}
        for name, overrides in sections.items():
            current = getattr(self, name)
            updates[name] = replace(current, **overrides)
        return replace(self, **updates)


REFERENCE_PROFILE = Profile()

# θ は reference の 0.8 より高い。H_vec が7チャネルあるため max(H) が θ を跨ぐ機会が
# 単一チャネルより多く、reference値のままでは跳躍が常態化して「再編」の意味を失う。
# cooldown も 10 → 16 に伸ばし、1個体あたり半日に1回程度の再編に収めている。
VILLAGE_PROFILE = REFERENCE_PROFILE.merged(
    boundary={"theta_base": 1.4, "theta_min": 0.6},
    leap={"cooldown_ticks": 16},
    # 身体と環境は変動が緩いので減衰を強め、破断位置が身体側へ偏らないようにする。
    h={
        "channel_decay": {"body": 0.94, "environment": 0.93},
        "channel_gain": {"body": 0.16, "environment": 0.2},
    },
)
VILLAGE_PROFILE = replace(VILLAGE_PROFILE, id="village")
