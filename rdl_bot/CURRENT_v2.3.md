# rdl_bot — Core v2.3 migration boundary

Status: **migration in progress**  
Normative semantic reference: `Aporapeiron/RDL_Core` T0 BASE / SPEC v2.3.

`rdl_bot` は旧RDL世代から継続している会話実験であり、既存コードには `EFP`、`xi_pool`、`H_pre/H_post` などの pre-v2.3 設計名が残っている。

それらは現行Coreの規範実装として読まない。

## Current canonical sidecar

`v23_state.py` にcanonical意味境界を置き、`runtime_v23.py` で実conversation turnを旧Runtimeの判断を変えずshadow取得する。

```text
raw conversation event
        ↓ Purpose / B / acquisition
InteractionSection   ≈ bot implementation of RIB_B
        ↓ frozen pre-response graph-side evaluator
        F

later event
        ↓ acquisition
InteractionSection'
        ↓ same model_ref の場合のみ比較
        F'
        ↓
E = Δ(F, F')
        ↓ unresolved only
        H
```

`runtime_v23.V23ConversationShadow` は応答生成前の有限graph状態をfingerprintし、入力sectionとFを記録する。旧 `main.respond()` はそのまま呼ばれるため、shadow観測はlegacy応答・学習・保存判断を変更しない。

応答後にgraph状態が変わり、次の入力時の `model_ref` が異なる場合は、same pre-update `M_B` だったことにせず `E` を形成しない。

現在の固定点:

```text
raw input != RIB_B
RIB_B     != F
coverage / missing / unknown / rejection != H
coverage / missing / unknown / rejection != ξ
noise / random jitter != ξ
all E != H
runtime unresolved-input queue length does not change theta
legacy miss / deny / silence do not mutate canonical H
model_ref changed -> canonical E NOT FORMED
```

`CoverageState` はbot-localな観測不足の記録であり、Core `ξ` ではない。

`UnresolvedMismatchState` はcanonical `E = Δ(F,F')` の未解決成分だけを保持する。ユーザーの否定、沈黙、未知入力、LLM呼出回数などを、それ自体としてCore Hへ加算しない。

## Runtime migration state

現行CLIのauthoritative action pathは、まだ `LegacyFeedbackLoadState` を再編判断に使っている。

```text
miss / partial / exact / deny / rephrase / agree / silence
                    ↓
          LegacyFeedbackLoadState
             H_pre / H_post
                    ↓
          legacy leap / correction
```

このlegacy feedback/load状態とcanonical Hは**別の状態型**として固定済み。`miss / deny / silence` を発生させても `UnresolvedMismatchState` は変化しない。canonical Hを増やせるのは、same pre-update modelで形成した `F / F'` のcanonical mismatchを明示的に `unresolved=True` として観測した場合だけである。

旧 `xi_pool -> theta` 結線はlive runtimeから切断済み。

```text
unresolved input queue
      ├─ 保存 / 後続再評価 / ノード化      → 維持
      └─ queue length -> leap threshold    → CUT
```

`h_state.unresolved_input_pressure()` はキュー長の**診断量**として残るが、`h_state.xi_pressure()` はlive CLI compatibility hookとして0を返す。したがって未解決入力の件数は、現行CLIのleap閾値を上下させない。

`LegacyFeedbackLoadState.theta_eff(explicit_pressure)` などのpressure-sensitive実験APIは形成史・回帰用に残るが、live CLIは未解決キューからそのpressureを供給しない。

実役割名として `local_state.UnresolvedInputQueue` を追加済みで、v2.3 adapter側APIは `unresolved_queue` を使う。`main.py` 内部の `xi_pool` 変数名・`/xipool` 表示などはcompatibility表面としてまだ残る。

## Canonical reconstruction authority candidate

`authority_v23.py` に `CanonicalLeapAuthority` を追加した。これはまだlive CLIのaction authorityではなく、Step 6の**非権威的な並走候補**である。

```text
same-model canonical E
        ↓ explicit unresolved classification
UnresolvedMismatchState
        ↓ fixed theta
should_reconstruct
```

このauthorityはAPI構造上、次を受け取らない。

```text
legacy miss / deny / silence
unresolved queue length
local pressure / uncertainty
Core ξ scalar
```

そのため、それらからcanonical θを動かす経路は存在しない。`model_ref` が変わったturn pairは `model-changed-no-E` として扱い、Eの代替値を作らずHも更新しない。

現段階では `CanonicalLeapAuthority.should_reconstruct` は**候補判定の観測値**であり、`main.py` の修正・隔離・新規学習を発火させない。live cutover前に、unresolved分類契約とlegacy actionとの差分観測を追加で固定する。

旧設計書:

- `RDL_個人MB外部化AI_中間設計図_v0.3.md`

は形成史として保持するが、Core v2.3の定義根拠として直接使用しない。

## Migration order

1. **DONE** — canonical `InteractionSection / F / F' / E / unresolved H / CoverageState` を追加
2. **DONE** — conversation eventからcanonical sectionをshadow取得し、same model_refの場合だけ入力F同士を比較可能にする
3. **PARTIAL** — `xi_pool` の実役割を `UnresolvedInputQueue` として分離し、新APIでは `unresolved_queue` を使用。`main.py` 内部名とCLI表示はcompatibilityとして残存
4. **DONE** — unresolved-input queue length -> theta のlive runtime結線を切断。キュー診断量は保持
5. **DONE** — `miss / deny / silence` 等のlegacy feedback eventとcanonical Hを型・更新経路の両方で分離。canonical mismatchを明示的にunresolvedと判定した場合だけcanonical Hへ接続可能
6. **PARTIAL** — `CanonicalLeapAuthority` をcanonical H + fixed θで実装し、legacy feedback/queue/pressureが侵入できない契約を固定。live action pathへの切替は未実施
7. **NEXT AFTER CUTOVER** — 旧 `EFP / xi / H_pre/H_post` APIをcompatibility層へ閉じ込める

各段階で既存CLIのsession保存、LLM trust、node graph、SFO profileの回帰を維持する。ただしStep 4以降、pre-v2.3のqueue-driven threshold挙動は意図的に互換対象から外れる。

## Test boundary

```bash
PYTHONPATH=rdl_bot:. python -m unittest discover -s rdl_bot/tests -p "test_*.py" -v
```

`test_v23_state.py` はcanonical意味境界を固定する。

`test_runtime_v23.py` は少なくとも次を固定する。

- shadow wrapperがlegacy応答結果を変更しない
- 実conversation inputがraw textとは別のfinite `InteractionSection` として取得される
- input sectionとFを同一視しない
- same frozen graph/model_refでは入力F比較ができる
- graph snapshotが変わればfalse same-model Eを作らない
- graph fingerprintは同じ有限状態に対して決定的

`test_h_state.py` / `test_dynamics.py` はStep 4以降、次を分離して固定する。

- `unresolved_input_pressure()` はキュー長のdiagnosticとして動く
- live `xi_pressure()` は常に0で、queue lengthをthetaへ結線しない
- explicit pressureを与えたlegacy threshold実験APIはhistorical regressionとしてのみ残る

`test_feedback_boundary_v23.py` はStep 5として次を固定する。

- `LegacyFeedbackLoadState` と `UnresolvedMismatchState` は別型
- legacy `miss / deny / silence` はcanonical Hを変更しない
- resolved canonical mismatchはHへ入らない
- unresolved canonical mismatchだけがcanonical Hを増やせる

`test_authority_v23.py` はStep 6候補として次を固定する。

- resolved mismatchはcandidate reconstructionを発火しない
- unresolved canonical mismatchはfixed θに対する候補再編を発火できる
- model_ref変更はE/Hへ変換しない
- legacy feedback loadはcandidate authorityを変更しない
- queue-size diagnosticはcandidate θを変更しない
- authority APIにpressure/feedback入力口を作らない
