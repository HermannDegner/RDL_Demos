# rdl_system/core

RDL（関係力学言語）Core v2.3 の役割分離を、デモ用の小さな離散モデルで追うための参照実装。
特定の生態系、チャットボット、ゲームルールには依存しない。

規範定義はこのディレクトリではなく、`Aporapeiron/RDL_Core` の T0 BASE / SPEC v2.3 にある。
ここはその完全実装ではなく、有限なシミュレーション用の実装例である。

## 現在の標準経路

```text
{RIB_i}
  ↓ Purpose / B / acquisition
RIB_B(t)      -> F(t)   = interp(M_B, RIB_B(t))
RIB_B(t+Δ)    -> F'(t+Δ)= interp(M_B, RIB_B(t+Δ))
                  ↓
             E = Δ(F, F')
                  ↓ unresolved only
                  H
                  ↓ H >= θ
             M_Δ -> M_B'
```

`F` と `F'` は同じ pre-update `M_B` で解釈する。参照コードでは `MBNode.compareSections()` が、二つの `RIBSection` を同じ frozen reliability で解釈した後に、必要なら局所適応を行う。

## 構成

| コード | 役割 | 注意 |
|---|---|---|
| `Boundary` | Purpose / `B` の有限条件 | SILNを生成するものではない |
| `RIBSection` | デモ上の `RIB_B` 表現 | raw world / 全RIB / `F` ではない |
| `MBNode` | `M_B` の小さな実装断面 | 人格・個体・SILNそのものではない |
| `HVector` | unresolved mismatch の保持 | 全ての `E` を自動蓄積しない |
| `LeapEngine` | `H >= θ` 時の再編候補 | `M_Δ -> M_B'` の簡易デモ |
| `MBGraph` | 実装断面どうしの有限な関係 | 世界全体の関係ネットワークではない |

## 最小例

```js
import { Boundary, MBNode } from "./index.mjs";

const boundary = new Boundary({
  id: "rabbit-B",
  dimensions: ["resource", "danger", "motion"],
  thetaBase: 0.8,
});

const model = new MBNode({
  id: "rabbit-model",
  boundary,
  reliability: { resource: 0.7, danger: 0.6, motion: 0.8 },
});

const current = boundary.section(
  { resource: 1, danger: 0.2, motion: 0.9 },
  { id: "rib-current" },
);
const later = boundary.section(
  { resource: 0.4, danger: 0.8, motion: 0.3 },
  { id: "rib-later" },
);

const result = model.compareSections({
  currentSection: current,
  laterSection: later,
  unresolved: true,
  tick: 1,
});

console.log(result.F, result.FPrime, result.E, result.H, result.leap);
```

## `ξ` とデモ固有状態

Core `ξ` は、有限な `B` で未回収となる関係であり、数値runtime state、noise、missing rate、unknown count、予測誤差、探索圧ではない。

旧参照実装にあった `xiGain / xiDecay / xiMax / xiThetaWeight` は廃止した。

シミュレーション上「誤差が続いている度合い」を観察する用途は残るため、この参照実装では別概念として `adaptationPressure` を持つ。

```text
adaptationPressure
!= Core ξ
!= Core H
!= Core E
```

`adaptationPressure` は診断・係数探索用のデモ固有量であり、Core `θ` を変更しない。

## H と局所適応

`E = Δ(F,F')` が観測されても、それが解決済みなら `H` へ保持する必要はない。`compareSections({ unresolved: false })` では `E` を返す一方、Hには追加せず既存Hを散逸させる。

`reliability` の微小更新は Core の唯一の更新則ではない。この参照実装が採用する Standard Model / demo-local adaptation であり、`F/F'` 比較の後にのみ行う。

## 方針

- Core記号とデモ固有量を同一視しない。
- raw inputをそのまま `RIB_B` と呼ばない。
- `RIB_B != F` を維持する。
- `ξ` を乱数・誤差・蓄積量として実装しない。
- 係数は `profiles/` に置き、Core必須定数として扱わない。
- 耐久・係数探索は `experiment/` で行い、結果を普遍則へ昇格させない。
