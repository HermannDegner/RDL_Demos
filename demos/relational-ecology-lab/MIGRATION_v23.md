# Living Field v2.3 migration checkpoint

2026-09-15。現行 `main` の Core / Functions v2.3 参照実装を基準に、Living Field を実際の観測経路から段階移行する。
この作業は Bot / Village の migration branch に依存せず、`main` から独立して進める。

## 先に Living Field を扱う理由

Living Field では Rabbit / Predator が共通の `evaluateDecision` 経路を持ち、正規化済み観測値を reliability 更新前に取得できる。
そのため、既存の行動runtimeを変えずに、実際の相互作用から有限な観測断面を形成し、同じ有限評価器で F / F' / E を比較できる。

既存runtimeには prediction error、local load、legacy leap 等があるが、それらをそのまま Core v2.3 の E / H / ξ と読み替えない。
sidecar は既存行動から読み取るだけで、policy、memory、reliability、local load、legacy leap の authority を変更しない。

## 現在の接続

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
explicit assessment gate
    ├─ zero-difference
    ├─ pending-assessment
    ├─ ordinary-temporal-change
    ├─ boundary-or-coverage-change
    ├─ resolved-difference
    └─ unresolved-mismatch
             ↓ only this status is eligible
           future H_vec
```

- `evaluateDecision` が作る正規化済み `observed` を有限作用断面の実装近似として取得する。
- `decision.prediction` や legacy H を RIB_B へ流用しない。
- 有限評価器は取得時の reliability 係数をコピーした重み付き変換であり、個体全体の `M_B` そのものではない。
- 前時刻で凍結した同じ係数を使い、二つの断面から F / F' を形成する。
- ここでの E は隣接する観測窓の重み付き解釈差であり、予測失敗、損失、未解消残差、再編必要性を自動的には意味しない。
- 非ゼロ E は、判定根拠が無ければ `pending-assessment` のまま保持する。
- 明示分類には `basis` を必須とする。`unresolved-mismatch` も根拠なしには形成できない。
- `unresolved-mismatch` だけが `eligibleForH=true`。それ以外の分類は H 候補にしない。
- `pending-assessment` のまま H 更新を試みると拒否する。E 全体から H への暗黙短絡を許さない。
- 実働 Rabbit / Predator では prediction-check による `resolved-difference` まで自動形成しうるが、prediction residual から `unresolved-mismatch` は自動生成しない。
- この段階では H_vec への加算、scalar H、θ 判定、M_Δ、行動変更を接続しない。
- 欠測・非有限値があれば比較窓を切り、ゼロで補完しない。
- 最新比較と分類件数だけを保持し、履歴を無制限に蓄積しない。
- 個体間で observer を共有せず、episode 再生成時は新しい比較窓にする。
- 既定は無効。ブラウザUIと既存snapshot schemaは変更しない。

## assessment の意味

Core v2.3 では H は E 全体ではなく、現在構造で吸収・解消されず残った不整合である。
そのため Living Field では、E の大きさだけで unresolved を決めない。

```text
E != 0
  ↓
根拠がまだ無い
  → pending-assessment

明示的な有限判定根拠がある
  ├─ 通常の時間変化                 → ordinary-temporal-change
  ├─ B / coverage の変更            → boundary-or-coverage-change
  ├─ 現在構造で吸収・説明できた差   → resolved-difference
  └─ 吸収を試みても残った不整合     → unresolved-mismatch
                                      ↓
                                 H_vec候補
```

この `basis` は終端的真理ではなく、その B・Purpose・取得条件のもとでの有限な判定根拠である。
後続の情報で分類が変わりうることを排除しない。

## prediction-check evidence

legacy `error = |observed - decision.prediction|` を canonical E として流用しない。
代わりに、予測が形成された時点の有限な prediction と reliability をコピーし、後続観測時に別の検査断面として再比較する `beginPredictionWindow()` / prediction-check を sidecar に接続する。

```text
Rabbit / Predator plan()
    ↓ decision prediction formed
beginPredictionWindow()
    ↓ copy selected prediction + coefficients
finite prediction snapshot
    ↓ later observed window
same copied coefficients
    ↓
weighted prediction / weighted observation
    ↓
prediction-check residual
```

実働配線では Rabbit / Predator の `this.decision` 形成直後に prediction とその時点の reliability を observer 内へコピーする。
後続 `evaluateDecision()` では、legacy `recordPredictionErrors()` が reliability を更新する前に既存 `capture()` が prediction window を消費する。
したがって prediction-check は、後から更新された係数へ追随せず、形成時点の有限な係数を保持する。

この residual は Core E ではなく、E を assessment するための有限な補助証拠である。
したがって次の非対称な規則だけを現段階で許す。

- prediction-check residual が **0** で、同じ選択次元・凍結係数の予測が後続観測と一致した場合、非ゼロ temporal E を `resolved-difference` とする有限根拠になりうる。
- prediction-check residual が非ゼロであっても、その大きさだけでは `unresolved-mismatch` に昇格させない。`pending-assessment` のまま残す。
- prediction または必要係数が欠ける場合、検査は `not-formed-missing-prediction` として保持し、ゼロや unresolved を捏造しない。
- prediction-check は legacy H / xi / thetaEffective を参照しない。
- prediction-check 自体は H を作らず、行動を変えない。
- observer は decision object を保持せず、選択次元の prediction と reliability のコピーだけを保持する。

この配線は `observeV23=true` の場合だけ有効であり、observer の返値は policy から読まれない。
したがって watched / unwatched simulation の seeded evolution、decision、memory、reliability、legacy local load、event、RNG は一致し続ける必要がある。

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

assessment / prediction-check については追加で次を固定する。

- 非ゼロ E は根拠なしで `pending-assessment` に留まる
- 明示分類は basis を要求する
- zero E を unresolved に分類できない
- pending のまま H 更新できない
- resolved / temporal / boundary-coverage は H に入らない
- 明示的な `unresolved-mismatch` のみ H 候補になれる
- prediction-check は開始時の係数をコピーし、後続の live reliability 変更に追随しない
- prediction と後続観測が一致した場合だけ、自動 `resolved-difference` の根拠として使える
- prediction residual は大きくても自動 unresolved にしない
- prediction の欠測をゼロ扱いしない
- 実働 Rabbit / Predator で prediction-check が発生する
- 実配線後も自動 `unresolved-mismatch` は発生せず、seeded evolution は不変

## 次段階

次に必要なのは、prediction residual が存在するとき、**現在の有限構造がその差を局所的に吸収・解消しようとしたか、その試行後にも何が残ったか**を示す別の有限証拠である。
prediction residual 自体や legacy local load をその証拠へ昇格させてはいけない。

候補となる証拠は、同じ B・Purpose・対象次元・更新前モデルとの対応を保持しながら、局所更新前後を明示的に区別できなければならない。
その証拠が固定できた場合にだけ、`unresolved-mismatch → H_vec → H = ||H_vec|| → θ` の読み取り専用 sidecar へ進む。
canonical H / θ が安定するまでは既存 local leap の authority を置き換えない。
