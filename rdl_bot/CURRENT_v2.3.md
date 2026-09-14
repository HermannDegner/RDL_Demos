# rdl_bot — Core v2.3 migration boundary

Status: **migration in progress / opt-in canonical action authority operational**  
Normative semantic reference: `Aporapeiron/RDL_Core` T0 BASE / SPEC v2.3.

中断後の検証結果、Core / Functionsとの対応、残作業は
[`MIGRATION_CHECKPOINT_v23.md`](./MIGRATION_CHECKPOINT_v23.md) を参照。

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

canonical再編資格、target選択、実mutationを分離する。

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
canonical mutation adapter
      ↓
LLM revision generation
      ├─ unavailable / failed -> no mutation
      └─ success
           old node -> deprecated
           new node -> add + relation
```

plannerはlegacy Hのhot-nodeを参照しない。executorはtarget選択を行わず、ambiguous / missing / invalid planではmutation callbackを呼ばない。

`mutation_v23.py` はcanonical targetだけを受けるLLM revision adapterを持つ。legacy H、hot-node、queue pressureは入力に取らない。

## 5. Runtime entrypoints

### Default legacy authority

```bash
py main.py
```

従来互換入口。legacy graph-mutation authorityが残る。

### Reviewed canonical CLI

```bash
py cli_v23.py
py cli_v23.py --seed
```

canonical観測・review・plan・explicit `/v23 execute` を追加するが、通常turn中のlegacy leap/correction authorityは維持する。

### Opt-in canonical action-authority CLI

```bash
py cli_v23_authority.py
py cli_v23_authority.py --seed
```

`cli_v23_authority.py` はprocess-localにlegacy `_decide_leap` を無効化する。legacy feedback/load状態は観測・互換のため残るが、**graph reconstructionを認可しない**。

このモードでは:

```text
ordinary response routing
legacy feedback recording
LLM trust / maintenance
        ↓ 維持

legacy H-based leap/correction
        ↓ DISABLED

canonical explicit review
        ↓
canonical H + fixed θ
        ↓
unique canonical target
        ↓
/v23 execute
        ↓
唯一の再編mutation入口
```

したがってopt-in authority modeでは、legacy H/hot-nodeからnode revision・quarantineへ入る経路を切り、canonical reviewed targetだけをmutation authorityにできる。

**default `main.py` は変更していない。** これは段階cutoverの実証入口であり、default authorityを無条件に切り替えたものではない。

## 6. Durable canonical state

canonical stateは `data/v23_shadow_state.json` へJSON保存する。

保存対象:

```text
fixed θ / decay
canonical H snapshot
assessment / pending records
explicit review audit
explicit execution audit
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

旧pending/reviewはaudit用途として保持する。target planningに必要な旧frozen evaluatorが無ければ `target-evidence-unavailable` で止まる。

## 7. `/v23` commands

### `/v23`

read-only status。

```text
turns in current window
last turn id
assessment count
pending count
review count
execution count
canonical H
fixed θ
reconstruction eligibility
latest pending / review / execution
```

### `/v23 resolve <reason>`

最新pendingを明示的にresolvedとして閉じる。canonical H increment = 0、node mutation = 0。

### `/v23 unresolved <reason>`

最新pendingを明示的にunresolvedとしてcanonical Hへ入れる。assessorは `cli-user`、元turn refsと `cli-review:<pair>` をevidenceとして保持する。

### `/v23 plan`

最新unresolved reviewをgate + target plannerへ通すdry-run。mutationはしない。

### `/v23 execute`

最新の**既にexplicit review済み** unresolved caseに対してのみ実行可能。

```text
review済み canonical H >= θ
        ↓
unique canonical target
        ↓
/v23 execute
        ↓
CanonicalReconstructionExecutor
        ↓
mutation_v23 adapter
```

安全境界:

```text
target missing           -> no mutation
LLM off / unavailable    -> no mutation
revision API unavailable -> no mutation
revision generation fail -> no mutation
success                  -> old deprecated / new added
```

成功mutationは同じreviewについてone-shotで、execution auditを永続化するため再起動後も二重実行しない。無変更試行は後で明示的に再試行できる。

## 8. Current fixed boundaries

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
review / plan != graph mutation
execute requires explicit reviewed canonical target
restart != permission to recreate old frozen evaluator
cross-restart E is not formed
successful execution is one-shot per reviewed pair
opt-in canonical authority mode disables legacy mutation authority
```

## 9. Migration order

1. **DONE** — canonical `InteractionSection / F / F' / E / unresolved H / CoverageState`
2. **DONE** — pre-update evaluator凍結、later section replay、route identityを含む有限F
3. **PARTIAL** — `xi_pool` 実役割を `UnresolvedInputQueue` として分離。`main.py`内部名とCLI表示はcompatibilityとして残存
4. **DONE** — unresolved-input queue length -> theta のlive結線を切断
5. **DONE** — legacy feedback stateとcanonical Hを型・更新経路で分離
6. **PARTIAL / OPT-IN AUTHORITY CUTOVER OPERATIONAL** — canonical authority、resolution policy、controller、gate、target planner、executor、mutation adapter、pipeline、durable session、review/plan/execute、`cli_v23_authority.py` によるlegacy leap authority無効化まで実装。**default `main.py` のauthority cutoverのみ未実施**
7. **AFTER DEFAULT CUTOVER** — 旧 `EFP / xi / H_pre/H_post` APIをcompatibility層へ閉じ込める

## 10. Test boundary

```bash
PYTHONPATH=rdl_bot:. python -m unittest discover -s rdl_bot/tests -p "test_*.py" -v
```

固定している主な契約:

- legacy responseをv2.3 wrapperが変更しない
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
- `/v23` はread-only
- `/v23 plan` はdry-runのみ
- `/v23 execute` はreview済みunique canonical targetだけをmutationへ渡す
- LLM unavailable / revision失敗ではgraphを変更しない
- successful executionは同reviewでone-shot
- execution auditはrestart後も二重実行を防ぐ
- canonical H / pending / review auditはrestart後も同値復元される
- turn idはrestart後も単調増加する
- restart直後はcross-restart Eを作らない
- 旧turn evidenceのfrozen evaluatorが無ければtargetを捏造しない
- opt-in authority modeはinstall前のdefault legacy objectを変更しない
- authority mode install後はlegacy `_decide_leap` がmutationを認可しない

## Formation history

`RDL_個人MB外部化AI_中間設計図_v0.3.md` はpre-v2.3形成史として保持する。旧 `EFP / ξ / H_pre/H_post / θ_eff` 結線は現行Coreの定義根拠として直接使用しない。
