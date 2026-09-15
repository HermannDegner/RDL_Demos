# Living Field v2.3 canonical migration — complete

2026-09-15。Living Field の canonical 経路を、T0 BASE / SPEC v2.3 と T1 SILN操作層に合わせて完結させた。

この文書でいう「complete」は、有限境界のもとで次の経路が実装・検査され、ブラウザ起動時にも canonical authority が実際の再編 authority になることを指す。

```text
actual interaction
  ↓
finite B / RIB_B approximation
  ↓ same frozen finite evaluator
F / F'
  ↓
E
  ↓ explicit finite assessment
resolved / temporal / coverage / unresolved
  ↓ reviewed unresolved only
H_vec
  ↓ demo-local finite norm
H = ||H_vec||
  ↓ explicit θ
H >= θ
  ↓
M_Δ
  ↓ current M_B objectified as SILN_SELF
T1 Probe
  ↓
Inspection / Selection = retain | reject | defer
  ↓ retain only
Reconstruction
  ↓
M_B'
  ↓ fresh finite observation
F_new / E_new / H_new
  ↓ finite re-entry validation
normal operation
```

`ξ` はこの経路のどこでも数値誤差・prediction residual・探索圧へ変換しない。各 `M_B` / `M_B'` は有限であり、未回収関係が残ることを `xiStatus = unrecovered-relations-remain` としてのみ保持する。

---

## 1. 一般観測境界

Rabbit は `resource / danger / motion`、Predator は一般境界で `prey / motion` を扱う。

`evaluateDecision.observed` を有限 interaction section の実装近似として取得し、取得時 reliability をコピーした同じ有限評価器で二つの窓を解釈する。

```text
observed(t)   ── frozen evaluator ──> F
observed(t+Δ) ── same evaluator   ──> F'
                                   ↓
                                   E
```

- raw temporal `E` は prediction failure、unresolved、H、再編必要性と同一視しない。
- 欠測・非有限値は窓を切り、ゼロを捏造しない。
- observer は policy から読み取られない段階を経て検証され、canonical cutover 後も acquisition / evidence role を保つ。

---

## 2. prediction-check と局所吸収試行

予測形成時に selected prediction と reliability をコピーし、後続観測時に別の finite evidence として再検査する。

```text
decision prediction
  ↓ freeze prediction + coefficients
later observed
  ↓
prediction-check
```

prediction が later observed と一致した場合、非ゼロ temporal E を `resolved-difference` とする有限根拠になりうる。

prediction residual は、どれほど大きくてもそれだけでは unresolved にならない。

さらに、capture 後の reliability と次 plan 時の reliability を比較し、現在デモの1回の bounded local updater で到達可能な変化だけを局所吸収試行 evidence とする。

```text
no-observed-local-adjustment
bounded-local-adjustment-observed
confounded-structural-change
not-formed-missing-local-coefficient
```

legacy leap 等が混ざりうる大きな変化は `confounded-structural-change` として除外する。

---

## 3. unresolved の成立条件

`unresolved-mismatch` は magnitude 閾値では作らない。

専用 finite review gate は少なくとも次を要求する。

1. same finite B
2. same Purpose
3. same selected dimensions
4. bounded local absorption-attempt evidence
5. stable selected coverage
6. ordinary temporal change の明示的除外
7. non-empty basis
8. reviewer identity
9. finite evidence references

coverage change が説明になる場合は `boundary-or-coverage-change`、ordinary temporal change で説明する場合は `ordinary-temporal-change` とし、Hへ入れない。

review はその B / Purpose / evidence における有限措定であり、終端真理ではない。

---

## 4. H sidecar

`v23_h_sidecar.mjs` は completed `PostAdjustmentResidualReview` だけを受け付ける。

generic assessment-shaped object、prediction residual magnitude、historical `H / xi / thetaEffective` には入力経路がない。

```text
reviewed unresolved E
  ↓
H_vec[dimension] += |E_dimension|
  ↓
H = ||H_vec||₂
  ↓
explicit θ
```

L2 は Living Field の demo-local finite concretization `l2-demo-local-v1` であり、Core唯一の norm ではない。

異なる B / Purpose / dimensions は同じ H に蓄積しない。context mismatch の拒否は atomic である。

---

## 5. M_Δ request と T0 / T1 handoff

`H >= θ` だけの裸のフラグから再構成対象を発明しない。

`requestMDelta()` は、現在 H を支える unresolved review 集合が同じ有限 context にあり、その集合から現在 `H_vec` を再生成できることを要求する。

request は次を保持する。

- B / Purpose / dimensions
- H_vec / H / θ / normRef
- review provenance
- request basis / requester

request 時点では `M_B'` を作らない。

`bindMDeltaSubject()` が別工程として current `M_B` を `SILN_SELF` として明示的に対象化し、T1へ渡す。

---

## 6. T1 Probe / Selection / Reconstruction

T1 実装は `v23_t1_reconstruction.mjs` に分離する。

```text
MDeltaT1Handoff
  ↓
finite current M_B capture
  ↓
candidate expansion
  ↓
future finite shadow Probe windows
  ↓
Selection
  ├─ retain
  ├─ reject
  └─ defer
       ↓ retain only
ReconstructedFiniteModel (M_B' proposal)
```

候補生成規則は Living Field の demo-local rule であり Core law ではない。

Probe は world / RIB / ξ の全体取得ではなく、後続 finite prediction/observation evidence による selected dimension の有限検査である。

Selection は現在の有限 scope で `retain / reject / defer` を明示する。Probe coverage 不足は `defer`、改善しない candidate は `reject` する。

retain された再構成は、valid conditions、break conditions、unresolved items、provenance を保持して `M_B'` proposal となる。

適用後も `xiStatus = unrecovered-relations-remain` であり、終端閉包しない。

---

## 7. 再構成後の通常運転復帰

`M_B'` 適用時に pre-reconstruction observer / H を持ち越さない。

fresh observer と fresh H sidecar で後続有限窓を取得する。

```text
M_B'
  ↓ fresh RIB_B'
F_new
  ↓
E_new → reviewed unresolved → H_new
```

re-entry completion は、

- H < θ
- 必要数の post-reconstruction finite comparisons / reviews
- explicit basis
- validator identity
- finite evidenceRefs

を要求する。

成立した場合だけ `normal-operation-restored` とする。

---

## 8. Predator B_attack

attack を一般 `prey / motion` 境界へ混ぜない。

`v23_attack_boundary.mjs` は attempt-specific boundary を形成する。

```text
beginAttack
  ↓ attempted=true
frozen capture prediction / reliability
  ↓
actual attempt outcome
  ├─ capture-success
  ├─ contact-escape
  ├─ obstacle-failure
  └─ timeout-or-range-failure
```

**unattempted attack は failure zero ではない。**

attempt が存在しない場合、B_attack section 自体を形成しない。

contact / escape / obstacle / success を provenance に保持する。

attack reliability の bounded local adjustment 後にも attempted-outcome residual が残り、finite review を通った場合だけ B_attack H に入る。

B_attack は一般Hと別 context / sidecar を持ち、T1では attack-specific candidate / Probe / Selection / Reconstruction を行う。

---

## 9. Complete canonical authority

`v23_complete_authority.mjs` は一般経路と B_attack を統合する。

install 後は historical `maybeLeap` の legacy H / xi / thetaEffective が再構成を起動しない。

historical fields は regression / compatibility diagnostics として更新されうるが authority ではない。

canonical reconstruction のみが `M_B'` を適用する。

`leapCount` は既存UI互換の表示カウンタとして更新するだけで、判定 source ではない。

---

## 10. operational reviewer

`v23_live_runtime.mjs` は手動 review を不要にする demo-local finite reviewer を提供する。

ただし residual を1回見ただけで unresolved にしない。

標準 rule は、

> same finite B / Purpose / dominant dimension のもとで、bounded local adjustment 後の residual が複数の**異なる**有限窓に連続して残った場合にのみ、ordinary temporal change を operationally excluded と措定する

である。

デフォルト browser rule は2窓。これは終端真理規則ではなく `persistent-post-adjustment-residual-v1` という明示的な demo-local review contract である。

同一 evidence を繰り返し読むことでは persistence count を増やさない。

一般経路と B_attack が同時に Predator の再編 authority を競合しないよう、一方が M_Δ / re-entry 中は他方の operational review を開始しない。

---

## 11. browser cutover

既存 `app.mjs` はUIコードを維持する。

先に評価される `local_aliases.mjs` がブラウザ時だけ bootstrap を行う。

1. `Simulation` episode creation 前に `observeV23=true` を成立させる
2. 最初の physical tick 前に live complete canonical runtime を install する
3. UIの `localLoad` は canonical H_vec を読む
4. UIの local threshold は canonical general θ を読む
5. demo-local adaptationPressure は compatibility scalar のままで Core ξ としない

Node環境では `window` が存在しないため browser bootstrap は実行されず、alias regression のみ維持する。

browser default は明示的な demo-local値として、

```text
theta = 1
attackTheta = 1
reviewWindows = 2
attackReviewWindows = 2
probeWindows = 2
reentryWindows = 2
```

を使う。URL query で有限設定を変更できる。

これらの値は Core定数ではない。

---

## 12. programmatic runtime

完全経路を直接生成する場合は `v23_live_runtime.mjs` の factory を使う。

```js
import { createLiveCanonicalLivingFieldSimulation } from "./v23_live_runtime.mjs";

const runtime = createLiveCanonicalLivingFieldSimulation({
  seed: 2401,
  theta: 1,
  attackTheta: 1,
  reviewWindows: 2,
  probeWindows: 2,
  reentryValidationWindows: 2,
});

runtime.simulation.step(720);
const snapshot = runtime.snapshot();
```

programmatic factory は θ / attackTheta を暗黙推定せず、明示値を要求する。

---

## 13. completion conditions

Living Field v2.3 migration は次を満たした状態を completion とする。

- actual Rabbit / Predator observation が finite v2.3 path へ入る
- raw E が automatic H にならない
- local absorption attempt が別 evidence として存在する
- unresolved は finite review を要求する
- reviewed unresolved only が H_vec へ入る
- H / θ から provenance-preserving M_Δ request が形成される
- current M_B が SILN_SELF として明示対象化される
- T1 Probe / Selection retain-reject-defer が実在する
- retained candidate only が M_B' proposal / apply へ進む
- M_B' 後に fresh finite validation が必要
- Predator attack は separate B_attack で attempt-specific に扱う
- unattempted != failure zero
- browser runtime で canonical authority が legacy leap authority を置換する
- legacy numeric xi は Core ξ ではない
- ξ / ξ' は未回収関係を残したまま閉じない

この境界で canonical Living Field migration は完了する。

今後の変更は「移行の残作業」ではなく、Probe候補の拡張、Selection道具の高度化、θやreview contractの実験的較正、UI診断表示の改善など、完成した有限経路上の発展として扱う。
