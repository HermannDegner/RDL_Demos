# rdl_bot — Core v2.3 migration boundary

Status: **migration in progress / reviewed durable shadow path operational**  
Normative semantic reference: `Aporapeiron/RDL_Core` T0 BASE / SPEC v2.3.

`rdl_bot` は旧RDL世代から継続する会話実験であり、`EFP`、`xi_pool`、`H_pre/H_post` 等のpre-v2.3名がまだ残る。これらを現行Core記号と同一視しない。

## 1. Canonical comparison

```text
RIB_B(t)
   ↓ frozen M_B(t)
F = interp(M_B(t), RIB_B(t))

RIB_B(t+Δ)
   ↓ replay through the same frozen M_B(t)
F' = interp(M_B(t), RIB_B(t+Δ))
   ↓
E = Δ(F, F')
```

`runtime_v23.FrozenGraphEvaluator` がt時点の有限graph-side evaluatorをdeep copyし、later sectionを同じ凍結評価器へreplayする。

したがって:

```text
live M_B change != automatic comparison failure
B change -> canonical E NOT FORMED
```

B比較には `boundary_id / purpose / question / conditions` を使い、observation timeの前進は許容する。

### Bot-local F coordinates

`exact / partial / miss / candidate_confidence` だけでは、同じconfidenceの別nodeへrouteした変化を落とすため、有限な実装座標を追加している。

```text
route:<selected-node-id> = 1.0
```

これはCore primitiveではない。有限routing stateのidentity差を保持するbot-local coordinateである。

## 2. Resolution policy

`assessment_policy_v23.py` は非対称な保守規則を固定する。

```text
E == 0
  -> resolved automatically

E != 0
  -> pending-review
  -> canonical Hには入れない

pending-review
  -> explicit reason + assessor + evidence
  -> resolved または unresolved
```

非ゼロEの大きさだけでunresolvedにはしない。`deny / miss / silence` をunresolvedへ直接変換するshortcutも持たない。

pending candidateは元の `turn-N` evidenceを保持し、review evidenceと結合する。

## 3. Canonical H / reconstruction eligibility

```text
explicit unresolved E only
        ↓
UnresolvedMismatchState
        ↓ fixed θ
should_reconstruct
```

`CanonicalLeapAuthority` は次を入力に取らない。

```text
legacy miss / deny / silence
unresolved queue length
local pressure / uncertainty
Core ξ scalar
```

旧 `xi_pool -> theta` live結線は既に切断済み。`unresolved_input_pressure()` は診断量、legacy名 `xi_pressure()` はlive compatibility hookとして0を返す。

## 4. Reconstruction path

canonical再編資格とtarget選択を分離する。

```text
canonical H >= fixed θ
      ↓
ReconstructionRequest
  target_ref = None
      ↓
CanonicalTargetPlanner
      ↓
canonical turn evidenceをearlier frozen evaluatorで再評価
      ├─ unique node -> target-proposed
      ├─ multiple    -> target-review-required
      └─ none        -> target-evidence-unavailable
      ↓ unique only
CanonicalReconstructionExecutor
      ↓
injected mutation callback
```

plannerはlegacy Hのhot-nodeを参照しない。executorはtarget選択を行わず、ambiguous / missing / invalid planではmutation callbackを呼ばない。

`pipeline_v23.py` には explicit review後のend-to-end candidate pathがあるが、default CLIのgraph mutation authorityにはまだ接続していない。

## 5. Opt-in reviewed durable shadow CLI

default CLI:

```bash
py main.py
```

これは現在もlegacy graph-mutation authorityを使う。

Core v2.3 shadow CLI:

```bash
py cli_v23.py
py cli_v23.py --seed
```

`cli_v23.py` は既存 `main.main()` をそのまま利用し、`respond` と `/v23` 系commandだけをwrapする。user-visible response、legacy feedback、LLM trust、legacy mutation authorityは維持される。

canonical shadow stateは `data/v23_shadow_state.json` へJSON保存する。

保存対象:

```text
fixed θ / decay
canonical H snapshot
assessment / pending records
explicit review audit
last assigned turn id
```

保存しないもの:

```text
frozen graph evaluator
old process-local graph snapshot
legacy graph-mutation authority
```

再起動後は `last_turn_id + 1` から新しいprocess-local comparison windowを開始する。旧凍結M_Bを再生成してrestart跨ぎのEを作ることはしない。

```text
turn N (old process)
   ↓ restart
turn N+1 (new process)
   -> no cross-restart E
turn N+2
   -> compare N+1 vs N+2 under frozen M_B(N+1)
```

旧pending/reviewはaudit・review用途として保持するが、そのtarget planningに必要な旧frozen evaluatorが無ければ `target-evidence-unavailable` で止まる。

### `/v23`

read-only status。

```text
turns in current window
last turn id
assessment count
pending count
review count
canonical H
fixed θ
reconstruction eligibility
latest pending / review
```

状態を変更しない。

### `/v23 resolve <reason>`

最新pendingを明示的にresolvedとして閉じる。

```text
pending -> resolved review
canonical H increment = 0
node graph mutation = 0
```

### `/v23 unresolved <reason>`

最新pendingを明示的にunresolvedとしてcanonical Hへ入れる。

```text
pending -> unresolved review
canonical H may increase
fixed θ eligibility may change
node graph mutation = 0
```

assessorは `cli-user`、evidenceには元turn refsと `cli-review:<pair>` を保持する。

### `/v23 plan`

最新のunresolved reviewをgate + target plannerへ通すdry-run。

```text
no unresolved review
  -> no-unresolved-review

H < θ
  -> below-reconstruction-threshold

H >= θ
  -> target-proposed / target-review-required / target-evidence-unavailable
```

**dry-run only**。executorもmutation callbackも呼ばない。

## 6. Current fixed boundaries

```text
raw input != RIB_B
RIB_B != F
F(t) / F'(t+Δ) use same frozen pre-update evaluator
live M_B change != B change
B change -> no canonical E
same match class/confidence but different route -> E can be nonzero
all E != H
nonzero E != unresolved by magnitude alone
legacy feedback != canonical H
unresolved input queue != Core ξ
queue length != canonical θ input
bare bool != sufficient unresolved classification
reconstruction eligibility != target selection
target selection != legacy hot-node selection
shadow review/plan != graph mutation
restart != permission to recreate old frozen evaluator
cross-restart E is not formed
```

## 7. Migration order

1. **DONE** — canonical `InteractionSection / F / F' / E / unresolved H / CoverageState`
2. **DONE** — pre-update evaluator凍結、later section replay、route identityを含む有限F
3. **PARTIAL** — `xi_pool` 実役割を `UnresolvedInputQueue` として分離。`main.py`内部名とCLI表示はcompatibilityとして残存
4. **DONE** — unresolved-input queue length -> theta のlive結線を切断
5. **DONE** — legacy feedback stateとcanonical Hを型・更新経路で分離
6. **PARTIAL / DURABLE SHADOW-CUTOVER READY** — canonical authority、resolution policy、controller、gate、target planner、executor、pipeline、migration session、opt-in `cli_v23.py`、explicit resolved/unresolved review、dry-run target plan、restart-safe JSON persistenceまで実装。**graph mutation authority cutoverのみ未実施**
7. **AFTER CUTOVER** — 旧 `EFP / xi / H_pre/H_post` APIをcompatibility層へ閉じ込める

## 8. Test boundary

```bash
PYTHONPATH=rdl_bot:. python -m unittest discover -s rdl_bot/tests -p "test_*.py" -v
```

固定している主な契約:

- legacy responseをshadow wrapperが変更しない
- frozen evaluatorはlive mutationを追わない
- later `RIB_B` をearlier frozen evaluatorで解釈する
- B変更時はEを作らない
- route identity差をFに保持する
- zero Eのみ自動resolved
- nonzero Eはpending
- explicit reviewなしではHへ入らない
- resolved reviewはHを増やさない
- unresolved reviewだけがHを増やせる
- reviewは元turn provenanceを保持する
- same pendingを二重reviewできない
- legacy feedback / queue diagnosticはcanonical authorityを変えない
- target plannerはlegacy hot-nodeを参照しない
- ambiguous / missing targetはexecutorへ進まない
- shadow CLI `/v23` はread-only
- shadow CLI reviewはgraphを変更しない
- `/v23 plan` はdry-runのみ
- canonical H / pending / review auditはrestart後も同値復元される
- turn idはrestart後も単調増加する
- restart直後はcross-restart Eを作らない
- 旧turn evidenceのfrozen evaluatorが無ければtargetを捏造しない

## Formation history

`RDL_個人MB外部化AI_中間設計図_v0.3.md` はpre-v2.3形成史として保持する。旧 `EFP / ξ / H_pre/H_post / θ_eff` 結線は現行Coreの定義根拠として直接使用しない。