# RDL_village

RDL的NPCによる簡易村シミュレーター。Python実装、外部依存なし。

> **Migration status:** 既存simulation本体は pre-v2.3 の歴史的実装を含む。現行Coreの意味基準は `Aporapeiron/RDL_Core` T0 BASE / SPEC v2.3。`v23_boundary.py` にcanonicalな `RIB_B / F / F' / E / unresolved H` の並走境界を追加している。

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
        ↓ Purpose / B / acquisition
VillageRIBSection(t)
        ↓ same pre-update model_ref
        F

later selected observations
        ↓
VillageRIBSection(t+Δ)
        ↓ same model_ref
        F'
        ↓
E = Δ(F, F')
        ↓ unresolved only
        H
        ↓ H >= θ
reconstruction candidate
```

また、既存 `XiPool` が担ってきた「探索しやすさ」「未確定結果の保持」は有用なsimulation stateだが、現行Core `ξ` と同一ではない。

`v23_boundary.py` ではこの役割を `ExplorationState` として分離する。

```text
ExplorationState != Core ξ
ExplorationState != Core H
boredom / fear / dialogue load != Core H by identity
all prediction error != H
```

既存 `core.py / npc.py / simulation.py` の `XiPool` 名と旧H結線は、挙動を壊さない段階移行の対象として残っている。

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
| `v23_boundary.py` | **CURRENT migration boundary** — RIBSection / F / F' / E / unresolved H / ExplorationState |
| `core.py` | pre-v2.3動態を含む既存simulation core。段階移行対象 |
| `profiles.py` | 係数プロファイルと NeuroProfile |
| `world.py` | 時計・場所・資源循環・物理環境 |
| `perception.py` | 個体知覚と個体予測場 |
| `relations.py` | 方向つき多軸関係 |
| `dialogue.py` | 語彙ノードと構造化 DialogueEvent |
| `action.py` | 関係作用・移動計画・物理ゲート |
| `npc.py` | VillageNPC と意思決定サイクル |
| `simulation.py` | tick進行・イベント配布・結果評価・非介入観測 |
| `richness.py` | 生命らしさの測定 |
| `test_v23_boundary.py` | 現行Core意味境界のmigration test |
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

1. **DONE** — `v23_boundary.py` と意味境界テストを追加
2. `XiPool` の実役割を exploration pressure / unresolved outcome queue に分解
3. simulation / plannerの `xi.exploration_pressure()` をdemo-local `ExplorationState.pressure` へ移す
4. `HVec` の各チャネルを Core H / demo-local load / direct motivation に分類
5. canonical `RIB_B(t) / RIB_B(t+Δ) → F/F' → E` をshadow観測
6. reconstruction判定を、必要な範囲でcanonical unresolved Hへ接続
7. 旧Core記号名をcompatibility層へ閉じ込める

段階ごとに固定seed回帰を維持し、挙動変更と意味名称変更を同時に行わない。

---

## 現状と限界

この村には環境過酷性が薄く、捕食者・致死的天候・季節・病気などの外圧が限定的。そのため生存率だけではモデル評価にならない。

また短期simulationに対して、個体側にはより長い時間スケールの仮説が含まれる。世界側に対応する変化が無い場合、その層の形成を実証したことにはならない。

既存の未解決事項:

- 破断・負荷が特定チャネルへ偏る可能性
- `gather` がほとんど駆動しない条件
- 夜に留まるコストが弱く、生活相として立ちにくい
- demo-local探索圧とCore ξの旧同一化を完全に解消する必要
