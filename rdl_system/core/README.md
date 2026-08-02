# rdl_system/core

RDL（関係力学言語）の参照実装を置くための最小コア。
特定の生態系、チャットボット、ゲームルールには依存せず、文書側の中核三式を
コードで追えるようにする。

```text
F(t)    = interp(M_B, EFP)
E(t)    = F(t+Δ) - M_B·F(t)
dM_B/dt = f(M_B, E, ξ)
```

この実装では、連続微分方程式を直接解くのではなく、fixed tick の離散更新として
扱う。

```js
const F = boundary.interpret(node, efp);
const predictedF = node.project(previousF);
const E = node.compare(predictedF, F);
node.h.record(E);
node.updateReliability(E);
node.leapEngine.maybeLeap(node);
```

## 構成

| コード | RDL概念 | 役割 |
|---|---|---|
| `Boundary` | `B` | 観測境界、評価関数、用途、観測者、跳躍閾値 |
| `MBNode` | `M_B` | 境界内で一時安定している整合慣性 |
| `HVector` | `H_vec` | 次元別の慣性誤差蓄積 |
| `LeapEngine` | `M_Δ -> M_B'` | 閾値超過時の再編処理 |
| `MBGraph` | `W_ij` / 入れ子 | M_B 間の関係ネットワーク |

## 既定の動態

`MBNode.update()` は、跳躍時だけでなく整合領域でも `M_B` を微小更新する。
既定では Living Field と同じ形で、予測誤差が小さい次元ほど信頼度が上がり、
誤差が大きい次元ほど下がる。

```text
reliability_i(t+1) = lerp(reliability_i(t), 1 - E_i(t), alignRate_i)
```

`ξ` は予測誤差から増え、tick ごとに散逸する。既定値は飽和して情報を失わない
ことを優先し、`xiDecay = 0.94`、`xiGain = 0.12`、`xiMax = 1.2` としている。

`LeapEngine` は既定で `cooldownTicks = 10` を持つ。これは参照実装をそのまま
走らせたとき、跳躍直後に同じ構造が再跳躍し続ける振動を避けるための安全側の
初期値である。デモ側でより速い再編を観察したい場合は明示的に上書きする。

## 最小例

```js
import { Boundary, MBNode } from "./index.mjs";

const boundary = new Boundary({
  id: "rabbit-B",
  dimensions: ["resource", "danger", "motion"],
  thetaBase: 0.8,
});

const rabbitModel = new MBNode({
  id: "rabbit-1",
  boundary,
  reliability: { resource: 0.7, danger: 0.6, motion: 0.8 },
});

const result = rabbitModel.update({
  efp: { resource: 1, danger: 0.2, motion: 0.9 },
  tick: 1,
});

console.log(result.E, result.H, result.leap);
```

## 方針

- 参照実装なので、抽象化より読みやすさを優先する。
- `EFP` や `K` のような低操作可能端の量は、シミュレーター内では直接置ける値として扱える。
- デモ固有の「兎」「捕食者」「資源」はここへ入れない。
- 既存デモは当面そのままにし、安定した部分から徐々にこのコアへ寄せる。
