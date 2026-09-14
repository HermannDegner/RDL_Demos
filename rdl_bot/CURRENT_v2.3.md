# rdl_bot — Core v2.3 migration boundary

Status: **migration in progress**  
Normative semantic reference: `Aporapeiron/RDL_Core` T0 BASE / SPEC v2.3.

`rdl_bot` は旧RDL世代から継続している会話実験であり、既存コードには `EFP`、`xi_pool`、`H_pre/H_post` などの pre-v2.3 設計名が残っている。これらは現行Coreの規範実装として読まない。

## Canonical comparison path

`v23_state.py` が意味境界を、`runtime_v23.py` が実conversation sectionとpre-update evaluatorの凍結を担当する。

```text
RIB_B(t)
   ↓ frozen M_B(t)
F = interp(M_B(t), RIB_B(t))

RIB_B(t+Δ)
   ↓ replay through the same frozen M_B(t)
F' = interp(M_B(t), RIB_B(t+Δ))
   ↓
E = Δ(F, F')
   ↓ conservative resolution policy / explicit review
resolved / pending / unresolved
   ↓ unresolved only
H
   ↓ fixed θ
reconstruction eligibility
```

live graphがtからt+Δの間に強化・学習・修正されても、それ自体はcanonical Eを妨げない。`runtime_v23.FrozenGraphEvaluator` がt時点の有限graph-side evaluatorをdeep copyし、後時点のsectionをそこへreplayする。

比較を止めるのは、同じ問いとして扱えない **B変更** である。`boundary_id / purpose / question / conditions` が変わればcanonical Eを形成しない。observation timeの前進は許容する。

`compare_inputs()` は同じmodel_ref同士だけを見るstrict diagnosticとして残すが、canonical temporal comparisonは `replay_later_under_earlier_model()` を使う。

### Bot-local F coordinates

routing Fは `exact / partial / miss / candidate_confidence` だけでは不十分である。同じconfidenceの異なるnodeへrouteしても全数値が一致し、誤って `E=0` になり得るため、有限なbot-local座標として `route:<node-id> = 1.0` を保持する。

```text
F = {
  exact,
  partial,
  miss,
  candidate_confidence,
  route:<selected-node-id>
}
```

`route:<node-id>` はCore primitiveではない。凍結された有限routing evaluatorが「どのrouteを選んだか」を落とさないための実装座標である。

現在の固定点:

```text
raw input != RIB_B
RIB_B != F
F(t) and F'(t+Δ) use the same frozen pre-update evaluator
live M_B change != automatic comparison failure
B change -> canonical E NOT FORMED
same match class/confidence but different route -> E can be nonzero
coverage / missing / unknown / rejection != H
coverage / missing / unknown / rejection != ξ
noise / random jitter != ξ
all E != H
nonzero E != unresolved by magnitude alone
runtime unresolved-input queue length does not change theta
legacy miss / deny / silence do not mutate canonical H
bare bool is not a sufficient unresolved classification
canonical reconstruction eligibility != node target selection
canonical target selection != legacy hot-node selection
```

## Runtime migration state

現行default CLIのauthoritative action pathは、まだ `LegacyFeedbackLoadState` を使う。

```text
miss / partial / exact / deny / rephrase / agree / silence
                    ↓
          LegacyFeedbackLoadState
             H_pre / H_post
                    ↓
          legacy leap / correction
```

このlegacy feedback/load状態とcanonical Hは別型・別更新経路として固定済み。

旧 `xi_pool -> theta` 結線はlive runtimeから切断済み。

```text
unresolved input queue
      ├─ 保存 / 後続再評価 / ノード化      → 維持
      └─ queue length -> leap threshold    → CUT
```

`h_state.unresolved_input_pressure()` はキュー長の診断量として残るが、live compatibility hook `xi_pressure()` は0を返す。実役割名は `local_state.UnresolvedInputQueue`。`main.py` 内部の `xi_pool` 変数名と `/xipool` 表示はcompatibility表面としてまだ残る。

## Canonical resolution policy

`resolution_v23.py` の `ResolutionAssessment` が、canonical mismatchをresolved / unresolvedのどちらとして扱うかを記録するprovenance-bearing boundaryである。

```text
ResolutionAssessment(
    unresolved,
    reason,
    assessor,
    evidence_refs
)
```

`reason` と `assessor` は必須。`CanonicalLeapAuthority` は裸のboolを受け取らない。また `from_deny / from_miss / from_silence` のようなshortcut constructorは意図的に持たない。

`assessment_policy_v23.py` は実conversation向けの保守的な形成規則を固定する。

```text
canonical E magnitude == 0
    -> resolved automatically

canonical E magnitude > 0
    -> pending
    -> Hには入れない

pending
    -> explicit reason + assessor + evidence
    -> unresolvedへ昇格可能
```

したがって、非ゼロEの大きさだけでunresolvedにはしない。legacy feedback eventは上位評価のevidenceになり得るが、それ自体をcanonical unresolved判定へ変換しない。

pending candidateは元のturn evidenceを保持し、review昇格時には新しいreview evidenceと結合する。元の比較provenanceを捨てない。

`canonical_runtime_v23.py` の `CanonicalRuntimeController` はこの形成規則を実turn pairへ接続する。

```text
shadow turn pair
  ↓ earlier frozen-model replay
canonical E
  ↓ conservative classify
zero      -> resolved-observed -> authority（H増分なし）
non-zero  -> pending-review    -> authorityへ入れない
  ↓ explicit review only
unresolved assessment
  ↓
canonical H
```

## Canonical reconstruction path

`authority_v23.py` の `CanonicalLeapAuthority` はcanonical H + fixed θで再編資格を判定する。default CLIのaction authorityにはまだ切り替えていない。

```text
unresolved canonical E only
        ↓
UnresolvedMismatchState
        ↓ fixed θ
should_reconstruct
```

このauthorityはAPI構造上、legacy miss/deny/silence、unresolved queue length、local pressure/uncertainty、Core ξ scalarを受け取らない。

`action_gate_v23.py` の `CanonicalActionGate` は、`should_reconstruct` が成立したauthority observationだけをtargetless `ReconstructionRequest` へ変換する。

```text
canonical H >= fixed θ
      ↓
ReconstructionRequest
  target_ref = None
```

再編資格とtarget選択は別問題である。mismatchにexplicit reasonsが無い場合でも、非ゼロdimension名からrequest理由を保守的に補完する。

`target_planner_v23.py` の `CanonicalTargetPlanner` はcanonical evidenceに含まれる `turn-N` だけを使い、earlier frozen evaluator上でtarget候補を再評価する。

```text
canonical turn evidence
  ↓ earlier frozen evaluator
candidate node refs
  ├─ unique 1 node -> target-proposed
  ├─ multiple      -> target-review-required
  └─ none          -> target-evidence-unavailable
```

legacy Hのhot-nodeは参照しない。review evidenceのような非turn参照からtargetを捏造しない。

`executor_v23.py` の `CanonicalReconstructionExecutor` は `target-proposed` のみを、注入されたmutation callbackへ渡す。ambiguous / missing / invalid target planはmutationを呼ばない。

`pipeline_v23.py` の `CanonicalReconstructionPipeline` はここまでを一つに結ぶ。

```text
pending-review
  ↓ explicit review
unresolved ResolutionAssessment
  ↓
canonical H + fixed θ
  ↓
targetless ReconstructionRequest
  ↓
canonical evidence target plan
  ↓ unique target only
injected mutation callback
```

raw deny/miss/silenceからpipeline executionへ入る自動経路は無い。

## Opt-in migration session

`migration_session_v23.py` の `CanonicalMigrationSession` は実conversationをlegacy応答のまま観測するopt-in統合層である。

```text
legacy respond result ───────────────→ user-visible result unchanged
        │
        └→ shadow capture
             ↓ adjacent turn replay
          resolved / pending-review
             ↓
          stored assessments
```

nonzero canonical Eはpendingとして蓄積されるだけで、自動H更新・自動mutationは起こらない。`review_and_execute(...)` を明示的に呼び、reason / assessor / evidenceを与えた場合だけcanonical pipelineへ進める。

このsession自体は実装済みだが、**default `main.py` CLIにはまだ配線していない**。したがって現時点でユーザーが通常起動した場合のauthoritative mutation pathはlegacyのままである。

`parallel_v23.py` の `CanonicalParallelObserver` は、legacy `should_leap(0.0)` とcandidate `should_reconstruct` を同じturn pairについてaction非介入で記録する。legacy loadを消費せず、candidate判定も修正・隔離・学習を発火させない。

## Migration order

1. **DONE** — canonical `InteractionSection / F / F' / E / unresolved H / CoverageState`
2. **DONE** — conversation sectionのshadow取得、pre-update evaluator凍結、later sectionのearlier-model replay、route identityを含む有限F座標
3. **PARTIAL** — `xi_pool` の実役割を `UnresolvedInputQueue` として分離。`main.py`内部名とCLI表示はcompatibilityとして残存
4. **DONE** — unresolved-input queue length -> theta のlive結線を切断
5. **DONE** — legacy feedback eventとcanonical Hを型・更新経路の両方で分離
6. **PARTIAL / CUTOVER-READY CANDIDATE PATH** — canonical H + fixed θ authority、保守的resolution policy、runtime controller、targetless gate、canonical target planner、executor、end-to-end pipeline、opt-in migration session、legacy/canonical並走observerまで実装。default CLI配線とauthoritative cutoverは未実施
7. **NEXT AFTER CUTOVER** — 旧 `EFP / xi / H_pre/H_post` APIをcompatibility層へ閉じ込める

## Tests

```bash
PYTHONPATH=rdl_bot:. python -m unittest discover -s rdl_bot/tests -p "test_*.py" -v
```

v2.3テストは少なくとも次を固定する。

- raw textとfinite `InteractionSection`を分離
- pre-update graph evaluatorがlive mutationを追わず凍結される
- later RIB_Bをearlier frozen evaluatorへreplayしてF'を形成
- B変更時はEを作らない
- model fingerprintはrouting-relevant state変更を検出する
- same match class / same confidenceでもrouteが変わればF差分を保持する
- zero Eは自動resolvedにできる
- nonzero Eは大きさだけではunresolvedにせずpendingに留める
- pendingは元turn provenanceを保持し、explicit review evidenceと結合する
- pendingはexplicit provenanceなしではcanonical Hへ入らない
- resolved mismatchはHへ入らない
- legacy feedback eventはcanonical Hを変更しない
- queue diagnosticはfixed θを変更しない
- unresolved分類はprovenance付き `ResolutionAssessment` を要求
- bare boolや `deny -> unresolved` shortcutを拒否
- reconstruction request生成時にlegacy hot-nodeを要求しない
- canonical requestはtargetlessで始まり、再編資格とtarget選択を分離する
- canonical target plannerはturn evidenceだけからunique targetを提案する
- ambiguous / missing targetはexecutorへ進まない
- executorはinjected mutation callback以外のmutation知識を持たない
- end-to-end pipelineはexplicit reviewなしではmutationへ到達しない
- migration sessionはlegacy応答を変えず、pendingを自動実行しない
- foreign session recordはreviewできない
- legacy/canonicalの判定差をaction非介入で記録できる

## Formation history

`RDL_個人MB外部化AI_中間設計図_v0.3.md` はpre-v2.3形成史として保持する。旧 `EFP / ξ / H_pre/H_post / θ_eff` 結線は現行Coreの定義根拠として直接使用しない。
