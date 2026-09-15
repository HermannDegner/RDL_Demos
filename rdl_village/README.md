# RDL_village

RDL的NPCによる簡易村シミュレーター。Python実装、外部依存なし。

> **Migration status:** Core v2.3 の canonical 経路は、finite B / RIB_B / F-F' / E / explicit review / H / θ / M_Δ / T1 Probe-Selection-Reconstruction / shadow re-entry / finite-context authority install / live re-entry まで実装済み。既存の `LocalLoadVector / ExplorationState / LeapEngine` は互換・村固有機構として残すが、移行済み finite context 内では canonical authority が再編権限を持つ。未移行 context では legacy authority を維持する。

旧設計の参照元:

- `RDL_簡易村シミュレーター`（T4 / DRAFT v0.1）
- `RDL_NPC行動決定システム`（T4 / DRAFT v0.3）

これらは形成史・実験設計として保持するが、Core v2.3 の定義根拠として直接使用しない。係数は demo-local な具体化であり、Core 必須定数ではない。

---

## Canonical v2.3 path

```text
selected village interaction
  ↓ finite B / Purpose / dimensions / conditions
RIB_B(t)
  ↓ same frozen pre-update M_B evaluator
F(t)

RIB_B(t+Δ)
  ↓ same frozen evaluator
F'(t+Δ)
  ↓
E = Δ(F,F')
  ↓
zero | pending
  ↓ separately audit bounded local absorption attempt
finite review candidate
  ↓ explicit review only
unresolved dimensions
  ↓
H_vec → H → explicit θ
  ↓ H >= θ
provenance-checked M_Δ request
  ↓
current M_B → SILN_SELF
  ↓
finite Probe evidence
  ↓
Selection = retain / reject / defer
  ↓ retain only
explicit M_B' proposal
  ↓
fresh shadow RIB_B' validation
  ↓ multiple stable windows
finite-context authority install
  ↓
fresh live re-entry validation
  ↓
normal operation for that finite context
```

非ゼロ `E` の大きさだけから `unresolved`、`H`、再構成へ進む経路は持たない。

---

## Stage 1 — finite comparison boundary

`v23_boundary.py` は次を固定する。

- finite B は `boundary_id / Purpose / selected dimensions / conditions` を明示する
- selected dimension の欠測を `0` に置換しない。欠測時は F/F' を形成しない
- F と F' は同じ pre-update `model_ref` と係数を使う
- place / band 等の finite conditions が変われば比較窓を切る
- 非ゼロ E は既定で `pending-assessment`
- `unresolved-mismatch` は unresolved dimension を明示する
- mismatch は finite conditions を provenance として保持する
- `VillageUnresolvedH` は reviewed unresolved component だけを受ける

Village の `H = max(H_vec)` と θ は demo-local な有限具体化であり、Core 唯一の norm / 定数ではない。

---

## Stage 2 — live read-only observer

`v23_live_observer.py` は実際の `VillageSimulation.step()` がNPCへ渡す知覚を opt-in で観測する。

初期 selected dimensions:

- `body_crisis`
- `discomfort`
- `visible_agents`
- `visible_resources`

observer 作成時に係数を固定し、place / band が変われば comparison window を切る。`LocalLoadVector / ExplorationState / LeapEngine` を canonical E/H/ξ/θ の根拠として読まない。

```python
from rdl_village import VillageSimulation, attach_v23_observer

simulation = VillageSimulation(seed=7)
observer = attach_v23_observer(simulation, theta=0.5)
simulation.run(480)
print(observer.snapshot())
```

固定seedテストでは observer ON/OFF で world log / village log / agent state / RNG state が一致することを要求する。

---

## Stage 3 — bounded local absorption + finite review + H

Village 既存の `PredictionField.integrate()` にある一回分の場所モデル更新を、Core の普遍則ではなく **Village-local absorption-attempt evidence** として監査する。

対応軸:

- `comfort` ← `discomfort`
- `social_expectation` ← `visible_agents`
- `resource_expectation` ← `visible_resources`

前tick snapshotと現在知覚から既存の一回分更新則を再計算し、実値と一致した場合だけ `bounded-local-adjustment-observed` とする。別経路の変更が混ざれば `confounded-structural-change`。`body_crisis` にはこの経路を捏造しない。

自動観測が作るのは review candidate まで。`unresolved-mismatch` には少なくとも以下を明示する。

- reviewer
- finite basis
- ordinary temporal change を除外したこと
- boundary / coverage change を除外したこと
- unresolved dimensions

reviewed unresolved dimensions だけが H に入る。

---

## Stage 4 — M_Δ and T1 shadow reconstruction

`v23_mdelta_t1.py` は T0/T1 境界を実装する。

### M_Δ request

`request_village_mdelta()` は `H >= θ` に加えて、review provenance から current `H_vec` を再計算できることを要求する。元の review candidate / evidence refs が欠ける、finite context が混在する、再計算Hがsidecar Hと一致しない場合は拒否する。

request 時点では `M_B'` や reconstruction target を生成しない。Core ξ は数値化せず `unrecovered-relations-remain` として保持する。

### SILN_SELF / Probe / Selection

`bind_village_mdelta_subject()` は current `M_B` を `SILN_SELF` として束縛する。実装上取得できる place model は **finite subject slice** であり whole M_B と同一視しない。

Probe は有限条件を変えて得られる `RIB_B` 相当の観測・解釈証拠を保持する。RIB 全体や ξ を取得したとはみなさない。

Selection は `retain / reject / defer`。retain は retained relations、defer は unresolved items を必須とする。H vector は candidate update vectorにしない。

### M_B' proposal / shadow re-entry

`propose_village_reconstruction()` は retain の場合だけ、呼出側が明示した candidate structure から `M_B'` proposal を作る。Bを変える場合は target B/Purpose/dimensions/conditions を明示する。

`validate_village_reentry()` は fresh `RIB_B'` で F_new/F_new'/E_new を形成する。非ゼロ fresh E は既定で pending であり、直接 H_new にしない。unresolved が疑われる場合は full review gate へ戻す。

---

## Stage 5 — finite-context canonical authority

`v23_authority.py` は shadow proposal を live authority へ定着させる最終 gate を提供する。

authority は agent 全体へ一括で広げず、exact finite context:

```text
B / Purpose / dimensions / place / band
```

ごとに移行する。

install 条件:

- actual `VillageReconstructionProposal`
- 複数の **distinct fresh** stable shadow re-entry windows
- explicit installer / finite basis / evidence refs
- complete finite observer coefficients
- bounded explicit `placeMeaningPatch`
- target B/Purpose/dimensions/place/band と runtime adapter の一致
- nested を含む numeric `xi / ξ` を禁止

移行済み context 内では candidate evaluator と context-local place-meaning state が有効になり、legacy `LeapEngine.check/check_basal` は再編 authority を持たない。

同じ場所でも別 band は別 finite B なので、例えば morning の `M_B'` を evening へ自動的に流用しない。context 切替時に base state と各 reconstructed state を保存・復元し、それぞれ独立に更新可能とする。

未移行 context では legacy runtime を維持する。これは universal truth への切替ではなく、有限B単位の段階的 authority migration である。

install 後は fresh model epoch を開始し、後続 live evidence で re-entry を検査する。re-entry 中に reviewed unresolved H が再び θ へ達した場合、その context は `M_delta-required` に戻る。

---

## Stage 6 — explicit canonical runtime driver

`v23_runtime.py` は test harness の手配を減らし、canonical object を一つの state machine で運ぶ。

```text
explicit review
 → context-local H
 → M_Δ
 → SILN_SELF
 → explicit Probe
 → explicit Selection
 → explicit candidate M_B'
 → shadow validation
 → finite-context install
 → live re-entry
```

重要なのは、この driver が **判定責任を自動化しない**こと。

- pending E を自動 unresolved にしない
- Probe evidence を捏造しない
- Selection を捏造しない
- candidate structure を H から自動生成しない
- ξ を数値化しない

つまり runtime driver は orchestration であり、有限reviewそのものの代替ではない。

```python
from rdl_village import VillageSimulation, install_village_canonical_runtime

simulation = VillageSimulation(seed=7)
runtime = install_village_canonical_runtime(simulation, theta=0.5)
```

runtime を install しただけでは挙動を変更しない。actual proposal が authority gate を通った finite context だけが canonical authority へ移行する。

---

## Core ξ and demo-local exploration

既存 `ExplorationState` は探索圧と未確定結果キューを持つ有用な村状態だが、Core ξ ではない。

```text
ExplorationState != Core ξ
ExplorationState != Core H
LocalLoadVector != Core H
boredom / fear / dialogue load != Core H by identity
all prediction error != H
ActionBoundary.theta_effective(...) != canonical θ law
```

旧名 `XiPool / HVec / Boundary` は固定seed互換のため alias として残すが、Core定義根拠にはしない。

---

## Authority scope

default の `VillageSimulation` は歴史的/村固有 runtime を保持する。

```text
no canonical runtime installed
  → legacy/local authority

canonical runtime installed, no context activated
  → behavior-equivalent legacy/local authority

activated finite B
  → canonical M_B' authority
  → legacy Leap reconstruction suppressed in that B

outside activated B
  → legacy/local authority until separately migrated
```

この分離により、移行途中でも finite context を越えて authority を過剰一般化しない。

---

## 実行・テスト

```bash
python -m rdl_village 640 7
python -m rdl_village.test_regression
python -m unittest \
  rdl_village.test_v23_boundary \
  rdl_village.test_v23_mdelta_t1 \
  rdl_village.test_v23_authority \
  rdl_village.test_v23_runtime -v
```

固定seed回帰を維持し、canonical managerを入れただけで既存挙動が変わらないことも検査する。

---

## 構成

| モジュール | 内容 |
|---|---|
| `v23_boundary.py` | finite B / RIB_B / F/F' / E / context provenance / assessment / H |
| `v23_live_observer.py` | actual perception / local-update audit / review candidates / H sidecar |
| `v23_review.py` | bounded local absorption evidence / explicit finite review gate |
| `v23_mdelta_t1.py` | M_Δ / SILN_SELF / Probe / Selection / M_B' proposal / shadow re-entry |
| `v23_authority.py` | finite-context authority gate / state isolation / live re-entry |
| `v23_runtime.py` | explicit canonical orchestration state machine |
| `core.py` | historical/local load・exploration・Leap compatibility runtime |
| `profiles.py` | demo coefficient profiles |
| `world.py` | clock / places / resources / physical environment |
| `perception.py` | individual perception and prediction field |
| `relations.py` | directed multi-axis relations |
| `dialogue.py` | vocabulary nodes / structured dialogue events |
| `action.py` | action candidates / movement / physical gates |
| `npc.py` | VillageNPC decision cycle |
| `simulation.py` | tick progression / event resolution / observation integration |
| `test_v23_boundary.py` | finite comparison / review / observer tests |
| `test_v23_mdelta_t1.py` | M_Δ and T1 shadow tests |
| `test_v23_authority.py` | finite-context cutover / isolation / non-intervention tests |
| `test_v23_runtime.py` | end-to-end explicit canonical runtime path |
| `test_regression.py` | fixed-seed historical behavior regression |

---

## 現在保持している実験機構

以下は村モデルとして有用なので、Core記号から分離しながら保持する。

- 物理世界と個体予測場の分離
- 同時解決と個体別乱数列
- 説明つき予測差
- 固着・再前景化
- 退屈・自発探索
- 思考的探索
- 繁殖動機・備蓄

これらを `ξ / H / M_Δ` と自動的に同一視しない。

---

## Migration status

1. **DONE** — finite B / coverage / same frozen evaluator / assessment boundary
2. **DONE** — actual perception read-only observer
3. **DONE** — bounded local absorption evidence
4. **DONE** — explicit finite unresolved review
5. **DONE** — reviewed unresolved `H_vec → H → explicit θ`
6. **DONE** — provenance-checked `M_Δ → SILN_SELF → Probe → Selection → M_B' proposal`
7. **DONE** — fresh shadow re-entry validation
8. **DONE (finite-context / opt-in)** — canonical authority cutover and legacy Leap suppression inside migrated B
9. **DONE** — explicit runtime orchestration from review through live re-entry
10. **NEXT / optional operational layer** — repeated finite evidenceからreview提案を支援する場合も、automatic unresolved promotionとは分離する
11. **NEXT** — sufficient finite-context coverage が得られた後に default runtime coverage を検討する
12. **NEXT** — legacy Core-like symbol aliases を compatibility layer へさらに閉じ込める

現時点で migration infrastructure はほぼ完成しているが、**全 place / band を一括で canonical authority にしたわけではない**。未観測・未検査の finite context は未移行として残す。

---

## 現状と限界

この村には環境過酷性が薄く、捕食者・致死的天候・季節・病気などの外圧が限定的。そのため生存率だけではモデル評価にならない。

短期simulationに対して個体側には長い時間スケールの仮説も含まれる。世界側に対応する変化が無い場合、その層の形成を実証したことにはならない。

既存の未解決事項:

- 破断・負荷が特定チャネルへ偏る可能性
- `gather` がほとんど駆動しない条件
- 夜に留まるコストが弱く、生活相として立ちにくい
- demo-local exploration と Core ξ の旧語彙を compatibility layer へ完全隔離する必要
