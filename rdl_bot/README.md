# rdl_bot — 会話実験 / Core v2.3 migration

RDL（関係力学言語）の語彙を使ったCLI会話実験。

現在は **Core v2.3のcanonical意味境界** と、旧v0.1由来の **legacy-local runtime** を分離している。現行Coreの定義根拠は `Aporapeiron/RDL_Core` T0 BASE / SPEC v2.3 であり、このディレクトリに残る `EFP`、`xi_pool`、`H_pre/H_post` 等の歴史的名称をそのままCore記号として読まない。

移行の詳細と正規の現在地は [`CURRENT_v2.3.md`](./CURRENT_v2.3.md) を参照。

## 現在のcanonical経路

```text
RIB_B(t)
   ↓ frozen M_B(t)
F = interp(M_B(t), RIB_B(t))

RIB_B(t+Δ)
   ↓ replay through the same frozen M_B(t)
F' = interp(M_B(t), RIB_B(t+Δ))
   ↓
E = Δ(F, F')
   ↓ conservative resolution policy
zero E    -> resolved
nonzero E -> pending-review
   ↓ explicit review only
unresolved E
   ↓
canonical H
   ↓ fixed θ
reconstruction eligibility
   ↓
targetless request
   ↓ canonical evidence target planning
unique target only
   ↓
explicit canonical execute
   ↓
LLM revision mutation adapter
```

守る境界:

```text
raw input != RIB_B
RIB_B != F
F and F' use the same frozen pre-update evaluator
live M_B change != automatic comparison failure
B change -> canonical E is not formed
legacy miss / deny / silence != canonical H
unresolved input queue != Core ξ
queue length does not change canonical θ
nonzero E != unresolved by magnitude alone
canonical reconstruction eligibility != target selection
canonical target selection != legacy hot-node selection
restart != permission to recreate old frozen evaluator
```

routing Fには `exact / partial / miss / candidate_confidence` に加え、有限なbot-local座標 `route:<node-id>` を保持する。同じconfidence・同じmatch classでも別nodeへrouteした場合に、誤って `E=0` としないためである。これはCore primitiveではない。

## Runtimeの二経路

### default legacy CLI

```bash
cd rdl_bot
pip install -r requirements.txt
py main.py
```

`main.py` の実際の修正・隔離・学習は、まだ `LegacyFeedbackLoadState` の旧経路がauthoritativeである。

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

### opt-in Core v2.3 reviewed CLI

```bash
py cli_v23.py
py cli_v23.py --seed
```

`cli_v23.py` は既存 `main.main()` をそのまま使い、canonical観測・review・plan・explicit executeだけを追加する。user-visible response、legacy feedback、LLM trust、default legacy action authorityは維持される。

canonical stateは `data/v23_shadow_state.json` へJSON保存する。

保存対象:

```text
canonical H snapshot
pending / assessment
review audit
execution audit
last turn id
```

frozen graph evaluator自体は保存しない。再起動後は新しい比較窓を開始し、restartを跨ぐEは形成しない。

### `/v23`

read-only診断。

表示内容:

- current process windowのturn数
- last turn id
- assessment / pending / review / execution件数
- canonical H magnitude
- fixed θ
- reconstruction eligibility
- 最新pending / review / execution

### `/v23 resolve <reason>`

最新pendingをresolvedとして閉じる。canonical Hは増えず、node graphも変更しない。

### `/v23 unresolved <reason>`

最新pendingをunresolvedとしてcanonical Hへ入れる。これはexplicit reviewであり、legacy `deny / miss / silence` から自動生成しない。

### `/v23 plan`

最新unresolved reviewのgate + target planningをdry-runする。node graphは変更しない。

### `/v23 execute`

最新unresolved reviewがfixed θ以上で、canonical evidenceからunique targetが得られた場合に限り、explicitにmutation adapterを呼ぶ。

```text
reviewed canonical H >= θ
        ↓
canonical target plan = unique
        ↓
/v23 execute
        ↓
LLM revision generation
        ├─ unavailable / failed -> no mutation
        └─ success
             old node -> deprecated
             new node -> added + relation
```

この経路はlegacy H / hot-nodeを参照しない。同じreviewでmutation成功後はone-shotとなり、再起動後もexecution auditにより二重実行しない。LLM off等で無変更だった試行は、後で明示的に再試行できる。

## canonical modules

- `v23_state.py` — `InteractionSection / F / F' / E / UnresolvedMismatchState / CoverageState`
- `runtime_v23.py` — finite section取得、pre-update evaluator凍結、later section replay、restart-safe turn id
- `resolution_v23.py` — provenance付き `ResolutionAssessment`
- `assessment_policy_v23.py` — zero→resolved / nonzero→pending の保守的形成規則
- `authority_v23.py` — canonical H + fixed θだけを見る `CanonicalLeapAuthority`
- `canonical_runtime_v23.py` — real turn pairからresolved/pendingへ接続するcontroller
- `action_gate_v23.py` — targetless `ReconstructionRequest`
- `target_planner_v23.py` — canonical turn evidenceだけからtarget候補を計画
- `executor_v23.py` — unique targetだけをinjected mutation callbackへ渡す境界
- `mutation_v23.py` — canonical targetに対するLLM revision mutation adapter
- `pipeline_v23.py` — explicit review後のend-to-end candidate pipeline
- `migration_session_v23.py` — pending/review/one-shot execution auditを持つsession
- `persistence_v23.py` — canonical H / review / executionのrestart durability
- `cli_v23.py` — opt-in reviewed CLI入口
- `parallel_v23.py` — legacy/canonical判定をaction非介入で比較
- `local_state.py` — `UnresolvedInputQueue` 等bot-local状態の現行名
- `candidate_v23.py` — Step 4時点のthreshold-neutral compatibility adapter

canonical explicit execution pathは実装済みだが、**default `main.py` のmutation authorityにはまだ切り替えていない**。

## CLIコマンド

既存CLI互換のため、default表示名にはpre-v2.3語彙がまだ残る。

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
| `/v23` | **cli_v23のみ**。canonical read-only診断 |
| `/v23 resolve <reason>` | explicit resolved review |
| `/v23 unresolved <reason>` | explicit unresolved review → canonical H |
| `/v23 plan` | canonical target planning dry-run |
| `/v23 execute` | explicit canonical one-shot mutation試行 |
| `/quit` | 保存して終了 |
| `y / n / ?` | 直前応答へのlegacy feedback入力 |

`y / n / ?` や miss/silence はlegacy feedback stateを更新するが、canonical Hへ直接加算されない。

## テスト

リポジトリルートから:

```bash
PYTHONPATH=rdl_bot:. python -m unittest discover -s rdl_bot/tests -p "test_*.py" -v
```

GitHub Actionsではbotテストに加えてVillage回帰とNode側公開デモ回帰も実行する。

v2.3側では少なくとも次を固定している。

- raw text と finite `InteractionSection` を分離
- later `RIB_B` をearlier frozen evaluatorへreplayしてF'を形成
- B変更時はEを形成しない
- same match class / same confidenceでもroute変更をF差分として保持
- `E = Δ(F,F')` を直接Hと同一視しない
- zero Eだけを自動resolvedにできる
- nonzero Eはpendingに留める
- pendingは元turn evidenceを保持し、explicit review provenanceと結合する
- legacy feedback eventはcanonical Hを変更しない
- unresolved queue件数はfixed θを変更しない
- unresolved判定には `ResolutionAssessment` を要求し、裸boolや `deny -> unresolved` shortcutを作らない
- reconstruction eligibilityとtarget selectionを分離
- target plannerはlegacy hot-nodeを参照しない
- ambiguous/missing targetはexecutorへ進まない
- `/v23 execute` はexplicit review済みunique target以外を変更しない
- LLM unavailable / revision失敗ではnode graphを変更しない
- successful executionは同reviewでone-shot
- execution auditはrestart後も保持される
- frozen evaluatorを再起動後に捏造せず、cross-restart Eを作らない

## 形成史

旧v0.1系の数式、`EFP / ξ / H_pre/H_post / θ_eff` 結線、SFO仮説、NN/LangGraph借用の説明は形成史としてGit履歴および [`RDL_個人MB外部化AI_中間設計図_v0.3.md`](./RDL_個人MB外部化AI_中間設計図_v0.3.md) に保持する。

それらはCore v2.3の規範定義ではない。現行の移行判断では、まず `CURRENT_v2.3.md` とcanonical v2.3 module群の契約を優先する。