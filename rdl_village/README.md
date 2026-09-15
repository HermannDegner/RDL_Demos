# RDL_village

RDL的NPCによる簡易村シミュレーター。Python実装、外部依存なし。

> **Migration status:** 既存simulation本体は pre-v2.3 の歴史的実装を含む。現行Coreの意味基準は `Aporapeiron/RDL_Core` T0 BASE / SPEC v2.3。`v23_boundary.py` にcanonical有限比較境界、`v23_live_observer.py` に実runtimeへ非介入で接続するread-only sidecar、`v23_review.py` に局所吸収証拠と有限review gateを置く。legacy `LocalLoadVector / ExplorationState / LeapEngine` は現段階では行動authorityを維持する。

旧設計の参照元:

- `RDL_簡易村シミュレーター`（T4 / DRAFT v0.1）
- `RDL_NPC行動決定システム`（T4 / DRAFT v0.3）

これらは形成史・実験設計として保持するが、Core v2.3の定義根拠として直接使用しない。

係数の出発点は [rdl_system/profiles](../rdl_system/profiles/) の demo profile。係数はCore必須定数ではない。

---

## Core v2.3 migration boundary

現在のcanonical sidecarは次の役割分離を固定する。

```text
selected village observations
        ↓ Purpose / finite B / selected dimensions
VillageRIBSection(t)
        ↓ same frozen pre-update model_ref + coefficients
        F

later selected observations
        ↓ same B / Purpose / dimensions / conditions
VillageRIBSection(t+Δ)
        ↓ same frozen evaluator
        F'
        ↓
E = Δ(F, F')
        ↓
zero-difference | pending-assessment
        ↓ separately audit current finite local model
bounded local absorption evidence
        ↓ review candidate only
explicit finite review
        ├ ordinary-temporal-change
        ├ boundary-or-coverage-change
        ├ resolved-difference
        └ unresolved-mismatch (explicit dimensions only)
                    ↓
              H_vec → H → explicit θ
                    ↓
          diagnostic-only threshold state
```

### Stage 1: hardened finite comparison boundary

`v23_boundary.py` は次を要求する。

- finite B は `boundary_id / Purpose / selected dimensions / conditions` を明示する
- selected dimension が欠測なら F/F' を形成しない。欠測を `0` に置換しない
- F と F' は同じ pre-update `model_ref` と明示係数を使う
- place / band 等のfinite conditionsが変わった場合は比較窓を切り、Eを形成しない
- 非ゼロEは大きさだけでは `unresolved` にならず、既定は `pending-assessment`
- `unresolved-mismatch` は未吸収dimensionを明示し、zero dimensionや範囲外dimensionをHへ入れない
- `VillageUnresolvedH` は finite assessment objectだけを受け、reviewed unresolved componentだけを蓄積する

`VillageUnresolvedH.magnitude` の max norm と `theta` はVillage demo-localな有限具体化であり、Core唯一のnorm/定数とはしない。

### Stage 2: live read-only observer

`v23_live_observer.py` は既存 `VillageSimulation.step()` がNPCへ渡している実知覚を opt-in で観測する。

```python
from rdl_village import VillageSimulation, attach_v23_observer

simulation = VillageSimulation(seed=7)
observer = attach_v23_observer(simulation)
simulation.run(480)
print(observer.snapshot())
```

初期の有限観測次元は demo-local に次の4つを選ぶ。

- `body_crisis`
- `discomfort`
- `visible_agents`
- `visible_resources`

係数はobserver生成時にコピーして固定する。place / band が変わればwindowを切る。observerは `LocalLoadVector / ExplorationState / LeapEngine` を読んでcanonical判定を作らず、policyにも書き戻さない。

固定seedテストではobserver有無で world log / village log / agent state / RNG state が一致することを要求する。

### Stage 3: bounded local absorption evidence + finite review + diagnostic H

Villageには `PredictionField.integrate()` が現在地の有限な場所モデルを局所更新する既存経路がある。sidecarは次の3軸だけを監査する。

- `comfort` ← `discomfort` に対応するVillage-local update
- `social_expectation` ← `visible_agents` に対応するVillage-local update
- `resource_expectation` ← `visible_resources` に対応するVillage-local update

前tickの有限snapshotと現在の知覚から、**既存runtimeの一回分の局所更新則で到達する値**を再計算し、実値と一致した場合だけ `bounded-local-adjustment-observed` とする。別経路の構造変更が混ざれば `confounded-structural-change` とし、吸収証拠にはしない。

```text
bounded local adjustment observed
+ corresponding non-zero E dimension
    ↓
review candidate
```

candidateはまだ `unresolved` ではない。`body_crisis` にはこのStageで対応する局所吸収則を立てていないため、Eが非ゼロでも自動的にcandidate dimensionへ含めない。

`unresolved-mismatch` に進むには、有限reviewで少なくとも次を明示する。

- ordinary temporal change を除外したこと
- boundary / coverage change を除外したこと
- unresolved とするdimension
- reviewer
- finite basis

reviewされた unresolved dimensionだけが sidecar `H_vec` に入り、`H >= θ` は現段階では **diagnostic-only**。legacy Leapを起動しない。

---

## Core ξ と demo-local exploration の分離

既存 `XiPool` が担ってきた「探索しやすさ」「未確定結果の保持」は有用なsimulation stateだが、現行Core `ξ` と同一ではない。

canonicalな実装名はすでに `ExplorationState` で、`XiPool` はcompatibility aliasに降格している。

```text
ExplorationState != Core ξ
ExplorationState != Core H
boredom / fear / dialogue load != Core H by identity
all prediction error != H
```

同様に、既存 `HVec` は `LocalLoadVector`、`Boundary` は `ActionBoundary` が実装上の本名であり、旧名は固定seed互換のため残している。

---

## 現行legacy/local authority

既存runtimeでは `evaluate_prediction()` が prediction residual / direct motivation / boredom 等を local load に集積し、`ExplorationState` によって局所閾値を動かし、`LeapEngine` が再編を行う。

これは村モデルとして保持するが、以下とは同一視しない。

```text
LocalLoadVector != Core H
ExplorationState.value != Core ξ
ActionBoundary.theta_effective(...) != canonical θ law
LeapEngine != canonical H >= θ -> M_Δ authority
```

canonical sidecarのH/θはこの経路へまだauthorityを持たない。

---

## 実行

```bash
python -m rdl_village 640 7        # 640tick（10日）、seed 7
python -m rdl_village.test_regression
python -m unittest rdl_village.test_v23_boundary -v
```

同じ seed・同じ tick 数から同じ snapshot を得る回帰境界を維持する。

---

## 構成

| モジュール | 内容 |
|---|---|
| `v23_boundary.py` | **CURRENT canonical boundary** — finite B / RIB_B / F / F' / E / dimension-specific assessment / unresolved H |
| `v23_live_observer.py` | **CURRENT live sidecar** — actual perception / local-update audit / review candidates / diagnostic H |
| `v23_review.py` | **CURRENT finite review gate** — bounded local absorption evidence / explicit unresolved review |
| `core.py` | pre-v2.3動態を含む既存simulation core。local canonical-name + compatibility alias |
| `profiles.py` | 係数プロファイルと NeuroProfile |
| `world.py` | 時計・場所・資源循環・物理環境 |
| `perception.py` | 個体知覚と個体予測場 |
| `relations.py` | 方向つき多軸関係 |
| `dialogue.py` | 語彙ノードと構造化 DialogueEvent |
| `action.py` | 関係作用・移動計画・物理ゲート |
| `npc.py` | VillageNPC と意思決定サイクル。legacy/local authorityを現状維持 |
| `simulation.py` | tick進行・イベント配布・結果評価・非介入観測 |
| `richness.py` | 生命らしさの測定 |
| `test_v23_boundary.py` | canonical境界 / absorption / review / live非介入テスト |
| `test_regression.py` | 固定シードの既存挙動回帰 |

---

## 現在保持している実験機構

以下は村モデルとして有用なので、Core記号から分離しながら保持する。

- **物理世界と個体予測場の分離** — NPC側モジュールは物理世界の真値を先読みしない
- **同時解決** — tick解決を複数相へ分離し、個体ごとに独立した乱数列を持つ
- **説明つき予測差** — どの差がどの条件で説明されたかを記録する
- **固着・再前景化** — 長期に残る内部負荷のHuman/demo側モデル
- **退屈・自発探索** — 低変化環境で探索を増やすsimulation-local mechanism
- **思考的探索** — 身体を動かさず候補構造を探索する
- **繁殖動機・備蓄** — 村固有の行動力学

これらを `ξ / H / M_Δ` と自動的に同一視しない。

---

## 付属文書

### `RDL_生命らしさ評価指針.md`

何を「良くなった」とみなすかを検討する実験文書。生存を単一目的関数にせず、複数軸で観察する。

### `破断検査.md`

実装がどの条件で崩れるかの記録。成功した修正だけでなく、失敗した試行列も過程として残す。

これらにもpre-v2.3語彙が残る可能性があるため、現行Core記号との対応はrole mappingとして再検査する。

---

## 次の移行順

1. **DONE** — finite B / coverage / same frozen evaluator / assessment境界を硬化
2. **DONE** — actual `simulation.step()` perceptionへread-only observerをopt-in接続
3. **DONE** — bounded local absorption attempt evidenceをlegacy H/xiから独立して監査
4. **DONE** — explicit finite reviewでordinary temporal / boundary / resolved / unresolvedを分離
5. **DONE (diagnostic-only)** — reviewed unresolved dimensionだけを `H_vec -> H -> explicit θ` へ接続
6. **NEXT** — provenance付き `M_Δ request -> T1 Probe / Selection / M_B'` をshadow実装
7. fresh re-entry validation後に、必要なauthorityだけをlegacy `LeapEngine` からcanonical経路へcutover
8. 旧Core記号名をcompatibility層へさらに閉じ込める

段階ごとに固定seed回帰を維持し、挙動変更と意味名称変更を同時に行わない。

---

## 現状と限界

この村には環境過酷性が薄く、捕食者・致死的天候・季節・病気などの外圧が限定的。そのため生存率だけではモデル評価にならない。

また短期simulationに対して、個体側にはより長い時間スケールの仮説が含まれる。世界側に対応する変化が無い場合、その層の形成を実証したことにはならない。

既存の未解決事項:

- 破断・負荷が特定チャネルへ偏る可能性
- `gather` がほとんど駆動しない条件
- 夜に留まるコストが弱く、生活相として立ちにくい
- demo-local explorationとCore ξの旧語彙をcompatibility層へ完全隔離する必要
