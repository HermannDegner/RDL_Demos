# rdl_bot — Core v2.3 migration boundary

Status: **migration in progress**  
Normative semantic reference: `Aporapeiron/RDL_Core` T0 BASE / SPEC v2.3.

`rdl_bot` は旧RDL世代から継続している会話実験であり、既存コードには `EFP`、`xi_pool`、`H_pre/H_post`、`theta_eff = theta + g(xi)` などの pre-v2.3 設計が残っている。

それらは現行Coreの規範実装として読まない。

## Current canonical sidecar

`v23_state.py` に、旧Runtimeから独立したcanonical意味境界を置いた。

```text
raw conversation event
        ↓ Purpose / B / acquisition
InteractionSection   ≈ bot implementation of RIB_B
        ↓ same pre-update model_ref / M_B-side evaluator
        F

later event
        ↓ acquisition
InteractionSection'
        ↓ same model_ref
        F'
        ↓
E = Δ(F, F')
        ↓ unresolved only
        H
```

現在の固定点:

```text
raw input != RIB_B
RIB_B     != F
coverage / missing / unknown / rejection != H
coverage / missing / unknown / rejection != ξ
noise / random jitter != ξ
all E != H
θ is not lowered by a measurable "ξ pressure"
```

`CoverageState` はbot-localな観測不足の記録であり、Core `ξ` ではない。

`UnresolvedMismatchState` はcanonical `E = Δ(F,F')` の未解決成分だけを保持する。ユーザーの否定、沈黙、未知入力、LLM呼出回数などを、それ自体としてCore Hへ加算しない。

## Legacy runtime

現行CLIはまだ旧経路を利用している。

```text
xi_pool
H_pre / H_post
theta_eff = theta + g(xi)
miss / deny / silence -> H
```

この経路は **compatibility / historical implementation** であり、段階移行対象。

旧設計書:

- `RDL_個人MB外部化AI_中間設計図_v0.3.md`

は形成史として保持するが、Core v2.3の定義根拠として直接使用しない。

## Migration order

1. **DONE** — canonical `InteractionSection / F / F' / E / unresolved H / CoverageState` を追加
2. **NEXT** — conversation eventからcanonical sectionをshadow取得し、旧Runtimeの判断を変えず観測比較する
3. `xi_pool` を coverage / unresolved-input queue 等の実役割へ再分類
4. `xi_pool -> theta` の結線を切る
5. `miss / deny / silence -> Core H` の直結を切り、canonical mismatchとの対応が成立する場合だけHへ接続
6. leap / reconstruction判定をcanonical Hと固定θの経路へ切替
7. 旧 `EFP / xi / H_pre/H_post` APIをcompatibility層へ閉じ込める

各段階で既存CLIの挙動、session保存、LLM trust、node graph、SFO profileの回帰を維持する。

## Test boundary

```bash
PYTHONPATH=rdl_bot:. python -m unittest discover -s rdl_bot/tests -p "test_*.py" -v
```

`test_v23_state.py` は少なくとも以下を固定する。

- raw text と `RIB_B` section の分離
- same pre-update modelによる `F / F'`
- `E = Δ(F,F')`
- resolved E はHへ保持しない
- unresolved Eだけが固定θに対する再編候補になる
- coverageはHにもξにも昇格しない
