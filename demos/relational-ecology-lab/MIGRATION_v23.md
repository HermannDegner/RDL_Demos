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
             ↓ explicit finite post-adjustment review only
           H_vec
             ↓ demo-local L2 finite concretization
           H = ||H_vec||
             ↓ explicit diagnostic θ
          H >= θ ?
             ↓ yes
        M_Δ request
             ↓ explicit current M_B binding only
        T1 handoff (read-only)
             ↓
        Probe / Selection / Reconstruction are still not executed
```

- `evaluateDecision` が作る正規化済み `observed` を有限作用断面の実装近似として取得する。
- `decision.prediction` や legacy H を RIB_B へ流用しない。
- 有限評価器は取得時の reliability 係数をコピーした重み付き変換であり、個体全体の `M_B` そのものではない。
- 前時刻で凍結した同じ係数を使い、二つの断面から F / F' を形成する。
- ここでの E は隣接する観測窓の重み付き解釈差であり、予測失敗、損失、未解消残差、再編必要性を自動的には意味しない。
- 非ゼロ E は、判定根拠が無ければ `pending-assessment` のまま保持する。
- 明示分類には `basis` を必須とする。
- 欠測・非有限値があれば比較窓を切り、ゼロで補完しない。
- 個体間で observer を共有せず、episode 再生成時は新しい比較窓にする。
- 既定は無効。ブラウザUIと既存snapshot schemaは変更しない。

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

- prediction-check residual が **0** で、同じ選択次元・凍結係数の予測が後続観測と一致した場合、非ゼロ temporal E を `resolved-difference` とする有限根拠になりうる。
- prediction-check residual が非ゼロであっても、その大きさだけでは `unresolved-mismatch` に昇格させない。
- prediction または必要係数が欠ける場合、ゼロや unresolved を捏造しない。
- prediction-check は legacy H / xi / thetaEffective を参照せず、行動を変えない。

## 局所吸収試行 evidence

prediction residual 自体を「吸収失敗」とみなさない。
`capture()` 後の選択次元 reliability を凍結し、次の `beginPredictionWindow()` で再取得した reliability と比較する。

現在のデモ局所 reliability 更新は `rate=0.035`, clamp `[0.18, 0.98]` なので、その1回の有限更新で到達可能な範囲だけを監査契約 `bounded-reliability-step-v1` とする。

```text
capture時 reliability
    ↓ freeze
次plan時 reliability
    ↓ finite transition audit
    ├─ no-observed-local-adjustment
    ├─ bounded-local-adjustment-observed
    ├─ confounded-structural-change
    └─ not-formed-missing-local-coefficient
```

- `bounded-local-adjustment-observed` は、このデモの局所更新が実際に起きたことを示す有限証拠であり、Core一般則ではない。
- 1回の局所更新包絡を超える変化は、legacy leap その他の構造変化が混ざりうるため `confounded-structural-change` として除外する。
- bounded local adjustment 後に prediction residual が残れば `prediction-residual-after-bounded-local-adjustment` と記録するが、それだけでは unresolved にしない。

## unresolved の有限 review 条件

Living Field で H へ入れる `unresolved-mismatch` は、`v23_post_adjustment_review.mjs` の専用 review gate を通したものに限定する。

```text
post-adjustment residual
    ↓ explicit finite review
  1. same B
  2. same Purpose
  3. same selected dimensions
  4. bounded local absorption-attempt evidence exists
  5. coverage change is not the explanation
  6. ordinary temporal change is explicitly excluded
  7. reviewer + finite evidenceRefs + basis are present
    ↓
unresolved-mismatch
```

coverage change が観測された場合は `boundary-or-coverage-change`、通常時間変化で説明する場合は `ordinary-temporal-change` とする。
上記 review は終端的真理判定ではなく、その B・Purpose・取得条件における有限な措定であり、後続情報で再検査されうる。

## read-only H sidecar

`v23_h_sidecar.mjs` は `PostAdjustmentResidualReview` 以外を受け付けない。
generic assessment 風オブジェクト、prediction residual magnitude、legacy `H / xi / thetaEffective` は入力経路を持たない。

```text
reviewed unresolved mismatch only
    ↓
H_vec[dimension] += |E_dimension|
    ↓
H = ||H_vec||_2
    ↓
explicit θ
    ↓
shouldReconstruct (diagnostic only)
```

- L2 はこのデモ局所の有限具体化 `l2-demo-local-v1` であり、Core唯一の norm と主張しない。
- θ は sidecar 作成時に明示指定し、legacy thetaEffective から取得しない。
- 異なる B / Purpose / dimensions の review を同じ H に蓄積しない。
- context 不一致による拒否は atomic で、H・count・last review を変更しない。
- `shouldReconstruct` は診断値であり、それ自体では policy を起動しない。
- Core ξ を数値化しない。

## M_Δ request / T1 handoff

T0 の最低動作では `H >= θ` が再編相 `M_Δ` への移行条件になる。一方、既存 `M_B` の対象化、Probe、Selection、`M_B'` 再構成は T1 の責務である。
Living Field ではこの境界を `v23_mdelta_request.mjs` に分離する。

```text
LivingFieldHSidecar
    ↓ H >= θ
requestMDelta()
    ↓
MDeltaRequest
    ├─ same finite context
    ├─ H_vec / H / θ / normRef
    ├─ finite unresolved review provenance
    ├─ subjectRef = null
    ├─ reconstructionTargetRef = null
    └─ reconstructedModelRef = null
          ↓ explicit binding only
bindMDeltaSubject()
          ↓
MDeltaT1Handoff
    ├─ explicit current M_B subjectRef
    ├─ subjectRole = SILN_SELF-current-M_B
    ├─ reconstructionTargetRef = null
    ├─ selectionStatus = not-performed
    └─ authority = T1-handoff-only
```

- `requestMDelta()` は `H < θ` では形成できない。
- request に渡す unresolved review 集合は H sidecar の `unresolvedReviews` 件数と一致し、同じ有限 context でなければならない。
- review から再構成した `H_vec` が sidecar の現在 `H_vec` と一致しない場合、request を拒否する。これにより provenance の欠落した threshold claim を作らない。
- request 自体は現在 `M_B` の具体参照を推測しない。`subjectRef` は `null` のまま保持する。
- T1へ渡すときだけ `bindMDeltaSubject()` で現在の `M_B` を明示的に `SILN_SELF` として束縛する。
- `M_B'`、再構成 target、Selection 結果は一切発明しない。これらは T1 の Probe / Selection / Reconstruction が別途形成する。
- request / handoff は policy を変えず、legacy leap の authority を持たない。
- numeric ξ フィールドを作らない。

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

追加で次を固定する。

- Rabbit / Predator の両方で prediction-check が実発生する
- bounded local adjustment evidence が実働で形成される
- out-of-envelope structural change を absorption-attempt と誤認しない
- residual magnitude だけでは unresolved にならない
- coverage / temporal disposition を review で明示しないと unresolved review は成立しない
- bounded local absorption-attempt evidence がない residual は unresolved review に入れない
- review は reviewer / basis / finite evidenceRefs を要求する
- coverage change / ordinary temporal change は H に入らない
- generic assessment / legacy numeric state は Living Field H sidecar に入らない
- reviewed unresolved だけが H_vec を更新する
- H sidecar は異なる有限 context を混合しない
- sidecar の `shouldReconstruct` は policy を変えない
- `H < θ` では M_Δ request を作れない
- M_Δ request の review provenance が H_vec を再現できなければ拒否する
- M_Δ request は `M_B'` や reconstruction target を作らない
- T1 handoff は current M_B の明示 subject binding だけを許し、Selection / Reconstruction を実行しない

## 次段階

T0側の canonical 経路は、実観測から `E → reviewed unresolved → H_vec → H → θ → M_Δ request → T1 handoff` まで read-only で接続した。

残る Living Field 本体の大工程は **authority cutover** である。ただし、その前に T1 側で `MDeltaT1Handoff` から Probe / Selection / Reconstruction proposal を形成し、`M_B'` を有限根拠付きで返せる経路を独立検証する必要がある。
その経路が安定するまで既存 local leap の authority は置き換えない。
