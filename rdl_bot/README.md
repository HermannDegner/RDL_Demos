# rdl_bot — 会話実験 / Core v2.3 migration

RDL（関係力学言語）の語彙を使ったCLI会話実験。

現在は **Core v2.3のcanonical意味境界** と、旧v0.1由来の **legacy-local runtime** を分離して並走させている。
現行Coreの定義根拠は `Aporapeiron/RDL_Core` T0 BASE / SPEC v2.3 であり、このディレクトリに残る `EFP`、`xi_pool`、`H_pre/H_post` 等の歴史的名称をそのままCore記号として読まない。

移行の詳細と正規の現在地は [`CURRENT_v2.3.md`](./CURRENT_v2.3.md) を参照。

## 現在の意味境界

```text
raw conversation event
        ↓ Purpose / B / acquisition
InteractionSection        # RIB_B のbot実装断面
        ↓ frozen pre-response evaluator
        F

later event
        ↓ same model_ref の場合だけ比較
        F'
        ↓
E = Δ(F, F')
        ↓ ResolutionAssessment
unresolved component only
        ↓
canonical H candidate
        ↓ fixed θ
reconstruction eligibility
```

守る境界:

```text
raw input != RIB_B
RIB_B != F
legacy miss / deny / silence != canonical H
unresolved input queue != Core ξ
queue length does not change canonical θ
model_ref changed -> canonical E is not formed
resolved E -> canonical H does not increase
```

## Runtimeの二経路

### canonical sidecar / candidate

- `v23_state.py` — `InteractionSection / F / F' / E / UnresolvedMismatchState / CoverageState`
- `runtime_v23.py` — 実conversation turnを有限sectionとしてshadow取得するadapter
- `resolution_v23.py` — unresolved判定を理由・判定主体・evidence付きで保持する `ResolutionAssessment`
- `authority_v23.py` — canonical H + fixed θだけを見る非権威的な `CanonicalLeapAuthority`
- `parallel_v23.py` — legacy判定とcanonical候補判定をaction非介入で比較するobserver
- `local_state.py` — `UnresolvedInputQueue` などbot-local状態の現行名

`CanonicalLeapAuthority` はまだlive CLIのaction authorityではない。現在は差分観測用の候補であり、`main.py` のノード修正・隔離・新規学習を直接発火しない。

### legacy action path

現行CLIの実際の修正・隔離・学習は、まだ `main.py` と `LegacyFeedbackLoadState` の旧経路が担当する。

```text
miss / partial / exact / deny / rephrase / agree / silence
                    ↓
          LegacyFeedbackLoadState
             H_pre / H_post
                    ↓
          legacy leap / correction
```

これは **bot-local feedback/load state** であり、Core Hそのものではない。

旧 `xi_pool -> theta` 結線はlive runtimeから既に切断済み。未解決入力キューは保存・後続再評価には使うが、その件数はleap閾値を動かさない。

```text
unresolved input queue
      ├─ save / retry / materialize later  -> keep
      └─ queue length -> threshold         -> CUT
```

`h_state.unresolved_input_pressure()` は診断量として残る。歴史的API名 `xi_pressure()` はlive compatibility hookとして0を返す。

## 起動

```bash
cd rdl_bot
pip install -r requirements.txt
py main.py
```

LLMで追加seedを作って起動する場合:

```bash
py main.py --seed
```

LLM接続なしでも同梱seedで最小動作する。

## CLIコマンド

既存CLI互換のため、表示名にはpre-v2.3語彙がまだ残る。

| コマンド | 現在の扱い |
|---|---|
| `/llm on\|off\|once` | LLMモード切替 |
| `/h` | legacy feedback/load state の表示。Core H表示ではない |
| `/sfo` | AI_SFOプロファイル表示 |
| `/mbti <TYPE>` | SFOプリセット再初期化 |
| `/trust` | ドメイン別LLM信用度表示 |
| `/dyn` | legacy/demo-local動態係数表示 |
| `/xipool` | unresolved input queue のhistorical alias表示 |
| `/graph` | ノードグラフ統計 |
| `/hot` | legacy feedback/loadの高いノード表示 |
| `/quit` | 保存して終了 |
| `y / n / ?` | 直前応答へのlegacy feedback入力 |

`y / n / ?` や miss/silence はlegacy feedback stateを更新するが、canonical Hへ直接加算されない。

## ファイル構成

```text
rdl_bot/
├── main.py                 legacy CLI action path
├── node_graph.py           Node / NodeGraph
├── h_state.py              LegacyFeedbackLoadState + queue-threshold compatibility hook
├── local_state.py          UnresolvedInputQueue 等のbot-local名
├── v23_state.py            canonical v2.3意味境界
├── runtime_v23.py          conversation shadow acquisition
├── resolution_v23.py       ResolutionAssessment
├── authority_v23.py        canonical fixed-θ authority candidate
├── parallel_v23.py         legacy/canonical decision comparison
├── candidate_v23.py        migration candidate adapters
├── llm_bridge.py           LLM bridge
├── llm_trust.py            domain-local LLM trust model
├── sfo_profile.py          SFO operational profile
├── dynamics.py             legacy/demo-local係数設定
├── CURRENT_v2.3.md         migrationの正規現在地
├── RDL_個人MB外部化AI_中間設計図_v0.3.md   pre-v2.3形成史
└── tests/
```

## テスト

リポジトリルートから:

```bash
PYTHONPATH=rdl_bot:. python -m unittest discover -s rdl_bot/tests -p "test_*.py" -v
```

GitHub Actionsではbotテストに加えてVillage回帰とNode側公開デモ回帰も実行する。

v2.3側では少なくとも次を固定している。

- raw text と `InteractionSection` を分離する
- same pre-update model_ref のときだけ `F / F'` を比較する
- `E = Δ(F,F')` を直接Hと同一視しない
- resolved mismatchはcanonical Hへ入れない
- legacy feedback eventはcanonical Hを変更しない
- unresolved queueの件数はθを変更しない
- unresolved判定には `ResolutionAssessment` を要求し、裸のboolや `deny -> unresolved` shortcutを作らない
- candidate authorityはfixed θを使い、pressure/feedback入力口を持たない
- legacy/canonicalの判定差をaction非介入で記録できる

## 形成史

旧v0.1系の数式、`EFP / ξ / H_pre/H_post / θ_eff` 結線、SFO仮説、NN/LangGraph借用の説明は形成史としてGit履歴および
[`RDL_個人MB外部化AI_中間設計図_v0.3.md`](./RDL_個人MB外部化AI_中間設計図_v0.3.md)
に保持する。

それらはCore v2.3の規範定義ではない。現行の移行判断では、まず `CURRENT_v2.3.md` と `v23_state.py` / `authority_v23.py` の契約を優先する。
