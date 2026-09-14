# Living Field v2.3 migration checkpoint

2026-09-14。現行 `main` の Core / Functions v2.3 参照実装を基準に、Living Field を実際の観測経路から段階移行する。
この差分は Bot / Village の migration branch に依存せず、`main` から独立している。

## 先に Living Field を扱う理由

Living Field では Rabbit / Predator が共通の `evaluateDecision` 経路を持ち、正規化済み観測値を reliability 更新前に取得できる。
そのため、既存の行動runtimeを変えずに、実際の相互作用から有限な観測断面を形成し、同じ有限評価器で F / F' / E を比較できる。

既存runtimeには prediction error、local load、legacy leap 等があるが、それらをそのまま Core v2.3 の E / H / ξ と読み替えない。
今回の sidecar は既存行動から読み取るだけで、policy、memory、reliability、local load、legacy leap の authority を変更しない。

## 今回の接続

```js
const simulation = new Simulation({ seed: 2401, observeV23: true });
simulation.step(720);
const diagnostics = simulation.v23Snapshot();
```

```text
actual interaction
    ↓
evaluateDecision.observed
    ↓ finite selected dimensions
RIB_B approximation
    ↓ same frozen finite evaluator
F(t) / F(t+Δ)
    ↓
E = Δ(F, F')
    ↓
pending-assessment / zero-difference
```

- `evaluateDecision` が作る正規化済み `observed` を有限作用断面の実装近似として取得する。
- `decision.prediction` や legacy H を RIB_B へ流用しない。
- 有限評価器は取得時の reliability 係数をコピーした重み付き変換であり、個体全体の `M_B` そのものではない。
- 前時刻で凍結した同じ係数を使い、二つの断面から F / F' を形成する。
- ここでの E は隣接する観測窓の重み付き解釈差であり、予測失敗、損失、未解消残差、再編必要性を自動的には意味しない。
- 非ゼロ差は `pending-assessment`、ゼロ差は `zero-difference` とする。
- この段階では H_vec への加算、scalar H、θ 判定、M_Δ、行動変更を接続しない。
- 欠測・非有限値があれば比較窓を切り、ゼロで補完しない。
- 最新比較と件数だけを保持し、履歴を無制限に蓄積しない。
- 個体間で observer を共有せず、episode 再生成時は新しい比較窓にする。
- 既定は無効。ブラウザUIと既存snapshot schemaは変更しない。

## attack を分離する理由

Predator の `attack` は今回の比較次元から除外する。
攻撃未試行を「失敗ゼロ」と扱うと、未観測と成功を混同するためである。
attack は今後、試行した / していない、接触した / 逸脱した、成功 / 失敗を分けられる試行単位の別境界 `B_attack` として設計する。

## 検証

固定 seed 41 / 2401 について、観測あり・なしを同じtickで走らせ、次が一致することを要求する。

- world snapshot
- agent memory
- reliability
- local load
- decision
- causal events
- RNG state

Rabbit / Predator の両方で実比較が発生すること、欠測時に比較窓が切れること、以前の係数が凍結されること、snapshot が読み取り専用であることも検証する。

## 次段階

次に必要なのは `E` の身分判定である。

```text
E
├─ ordinary temporal change
├─ boundary / coverage change
├─ resolved or explainable difference
└─ unresolved mismatch
        ↓ only here
      H_vec
        ↓
      H = ||H_vec||
        ↓
      H >= θ ?
```

時間変化そのものを prediction mismatch と扱わない。
また、canonical H / θ が安定するまでは既存 local leap の authority を置き換えない。
