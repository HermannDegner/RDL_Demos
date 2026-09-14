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
   ↓ resolution policy / explicit review
resolved / pending / unresolved
   ↓ unresolved only
H
   ↓ fixed θ
reconstruction eligibility
```

live graphがtからt+Δの間に強化・学習・修正されても、それ自体はcanonical Eを妨げない。`runtime_v23.FrozenGraphEvaluator` がt時点の有限graph-side evaluatorをdeep copyし、後時点のsectionをそこへreplayする。

比較を止めるのは、同じ問いとして扱えない **B変更** である。`boundary_id / purpose / question / conditions` が変わればcanonical Eを形成しない。observation timeの前進は許容する。

`compare_inputs()` は同じmodel_ref同士だけを見るstrict diagnosticとして残すが、canonical temporal comparisonは `replay_later_under_earlier_model()` を使う。

現在の固定点:

```text
raw input != RIB_B
RIB_B != F
F(t) and F'(t+Δ) use the same frozen pre-update evaluator
live M_B change != automatic comparison failure
B change -> canonical E NOT FORMED
coverage / missing / unknown / rejection != H
coverage / missing / unknown / rejection != ξ
noise / random jitter != ξ
all E != H
nonzero E != unresolved by magnitude alone
runtime unresolved-input queue length does not change theta
legacy miss / deny / silence do not mutate canonical H
bare bool is not a sufficient unresolved classification
canonical reconstruction eligibility != node target selection
```

## Runtime migration state

現行CLIのauthoritative action pathは、まだ `LegacyFeedbackLoadState` を使う。

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

## Canonical reconstruction authority and action gate

`authority_v23.py` の `CanonicalLeapAuthority` はcanonical H + fixed θで再編資格を判定する。まだlive CLIのaction authorityではない。

```text
unresolved canonical E only
        ↓
UnresolvedMismatchState
        ↓ fixed theta
should_reconstruct
```

このauthorityはAPI構造上、legacy miss/deny/silence、unresolved queue length、local pressure/uncertainty、Core ξ scalarを受け取らない。

`action_gate_v23.py` の `CanonicalActionGate` は、`should_reconstruct` が成立したauthority observationだけを `ReconstructionRequest` へ変換する。

重要なのは、request生成時点で**target nodeを決めない**ことである。

```text
canonical H >= fixed θ
      ↓
ReconstructionRequest
  target_ref = None
      ↓
separate canonical target planner / executor（未実装）
```

canonical再編資格と「どのnodeを修正するか」は別問題であり、後者をlegacy hot-nodeから流用しない。`CanonicalActionGate` はlegacy state / hot-nodeを入力に取らない。

`parallel_v23.py` の `CanonicalParallelObserver` は、legacy `should_leap(0.0)` とcandidate `should_reconstruct` を同じturn pairについてaction非介入で記録する。legacy loadを消費せず、candidate判定も修正・隔離・学習を発火させない。

観測可能な差:

```text
legacy = leap, canonical = no reconstruction
legacy = no leap, canonical = reconstruction candidate
live model changed, same B -> frozen earlier modelでcanonical比較継続
B changed -> canonical comparison unavailable
```

Step 6の残件は、pending reviewを扱うcanonical target planner / executorと、それを経たlive action cutoverである。

## Migration order

1. **DONE** — canonical `InteractionSection / F / F' / E / unresolved H / CoverageState`
2. **DONE** — conversation sectionのshadow取得とpre-update evaluator凍結、later sectionのearlier-model replay
3. **PARTIAL** — `xi_pool` の実役割を `UnresolvedInputQueue` として分離。`main.py`内部名とCLI表示はcompatibilityとして残存
4. **DONE** — unresolved-input queue length -> theta のlive結線を切断
5. **DONE** — legacy feedback eventとcanonical Hを型・更新経路の両方で分離
6. **PARTIAL** — canonical H + fixed θ authority、保守的resolution policy、live controller、targetless action gate、legacy/canonical並走observerまで実装。canonical target planner / executorとlive cutoverは未実施
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
- zero Eは自動resolvedにできる
- nonzero Eは大きさだけではunresolvedにせずpendingに留める
- pendingはexplicit provenanceなしではcanonical Hへ入らない
- resolved mismatchはHへ入らない
- legacy feedback eventはcanonical Hを変更しない
- queue diagnosticはfixed θを変更しない
- unresolved分類はprovenance付き `ResolutionAssessment` を要求
- bare boolや `deny -> unresolved` shortcutを拒否
- reconstruction request生成時にlegacy hot-nodeを要求しない
- canonical requestはtargetlessで始まり、再編資格とtarget選択を分離する
- legacy/canonicalの判定差をaction非介入で記録できる

## Formation history

`RDL_個人MB外部化AI_中間設計図_v0.3.md` はpre-v2.3形成史として保持する。旧 `EFP / ξ / H_pre/H_post / θ_eff` 結線は現行Coreの定義根拠として直接使用しない。
