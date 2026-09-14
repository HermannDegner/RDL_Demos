# rdl_bot — Core v2.3 migration boundary

Status: **migration in progress**  
Normative semantic reference: `Aporapeiron/RDL_Core` T0 BASE / SPEC v2.3.

`rdl_bot` は旧RDL世代から継続している会話実験であり、既存コードには `EFP`、`xi_pool`、`H_pre/H_post`、`theta_eff = theta + g(xi)` などの pre-v2.3 設計が残っている。

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
θ is not lowered by a measurable "ξ pressure"
model_ref changed -> canonical E NOT FORMED
```

`CoverageState` はbot-localな観測不足の記録であり、Core `ξ` ではない。

`UnresolvedMismatchState` はcanonical `E = Δ(F,F')` の未解決成分だけを保持する。ユーザーの否定、沈黙、未知入力、LLM呼出回数などを、それ自体としてCore Hへ加算しない。

## Legacy runtime

現行CLIのauthoritative action pathはまだ旧経路を利用している。

```text
xi_pool
H_pre / H_post
theta_eff = theta + g(xi)
miss / deny / silence -> legacy feedback load
```

この経路は **compatibility / historical implementation** であり、段階移行対象。

コード上では旧 `HState` は `LegacyFeedbackLoadState`、旧 `xi_pressure` は `unresolved_input_pressure` のcompatibility aliasへ降格済み。これらをCore H / ξそのものとして扱わない。

旧設計書:

- `RDL_個人MB外部化AI_中間設計図_v0.3.md`

は形成史として保持するが、Core v2.3の定義根拠として直接使用しない。

## Migration order

1. **DONE** — canonical `InteractionSection / F / F' / E / unresolved H / CoverageState` を追加
2. **DONE** — conversation eventからcanonical sectionをshadow取得し、旧Runtimeの判断を変えず観測する。same model_refの場合だけ入力F同士を比較可能
3. **NEXT** — `xi_pool` を coverage / unresolved-input queue 等の実役割へ再分類し、runtime/API名を段階的に切替
4. `xi_pool -> theta` の結線を切る
5. `miss / deny / silence -> Core H` の同一視を完全に外し、canonical mismatchとの対応が成立する場合だけHへ接続
6. leap / reconstruction判定をcanonical Hと固定θの経路へ切替
7. 旧 `EFP / xi / H_pre/H_post` APIをcompatibility層へ閉じ込める

各段階で既存CLIの挙動、session保存、LLM trust、node graph、SFO profileの回帰を維持する。

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
