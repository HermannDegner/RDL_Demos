# RDL Living Field

既存の生態系デモで段階的に導入した知覚制約、複合資源、固定地形、
資源転移、局所的な予測負荷を、RabbitとPredatorが互いを環境として学ぶ更新系へ統合した
ブラウザ実験。

[デモを開く](./index.html)

> **Core v2.3 migration status**
>
> このデモの生態系挙動は継続利用するが、既存runtimeの `H` / `H_vec` / `xi` /
> `thetaEffective` は **Core v2.3 の H / ξ / θ と同一ではない**。それらは
> pre-v2.3由来のデモ固有状態・ローカル制御則として段階的に改名・分離する。
> 現行Coreの正規比較境界は [`v23_state.mjs`](./v23_state.mjs) にあり、
> `RIB_B → F/F' → E = Δ(F,F') → unresolved H` を別経路で保持する。
> Core ξはruntime scalarとして実装しない。

## 設計原則

### 1. 三つの場を分離する

| 場 | 保持する状態 | 個体の意思決定へ入る条件 |
|---|---|---|
| 物理環境 | 連続位置、境界、資源量、草の遮蔽、岩の地形、Rabbit、Predator | 接触、視覚、音として知覚された場合だけ |
| 個体の予測場 | Rabbitの資源・危険記憶、Predatorの獲物記憶、移動誤差、訪問履歴 | 所有する個体だけが参照する |
| 観測者の記録 | 生存数、休眠、転移、Leap、イベント | 入らない。表示と外部評価専用 |

Rabbit間だけでなく、RabbitとPredatorの間でも記憶配列は共有しない。共有情報を
導入する場合は、匂いや痕跡など物理環境に残る媒体を先に実装する。

### 2. 世界は連続、記憶は離散

- Rabbit、Predator、資源は `960 × 640` の連続座標を持つ。
- 個体の予測場だけを `24 × 16` セルで保持する。
- 境界は閉じており、反対側へ `wrap` しない。
- シミュレーションは60 Hz相当のfixed tickで更新する。

これにより、格子が身体運動を決めるのではなく、粗い記憶が連続運動の候補を
評価する関係になる。

### 3. 地形を、共有知識ではなく物理関係にする

seedごとに7個の岩を固定配置する。岩はRabbitとPredatorの両方に対して通過不可で、
岩を横切る視線も遮る。衝突時は岩へ向かう速度成分だけを除き、接線方向の速度を
残すため、斜めに接触した個体は壁沿いに滑る。

捕食行動中の脅威が岩へ衝突した場合は、そのtickで攻撃不成立となり低速回復へ
移る。資源の初期生成と再生地点は岩の内部および周辺から除外する。

岩の座標は物理環境に存在するが、どの個体の内部場にも最初から配らない。視界へ
入った岩だけを各個体の`motion`場へ記録し、未発見の岩へ衝突した場合も移動誤差
として記録する。同じ地形でも、種と探索履歴によって意味が異なる。

### 4. 資源転移を出来事の連鎖にする

~~~text
摂取 → 残量低下 → 生態的枯渇 → 休眠時間 → 別地点で再生
~~~

旧デモのように枯渇フレームで即時転送せず、休眠期間を置く。
そのため、個体の古い資源記憶と現在の視界が食い違う時間が生まれる。
この不一致は現在のruntimeでは資源予測差とデモ固有の適応圧へ接続されるが、
その適応圧をCore ξとはみなさない。

### 5. 捕食を一回の行動にする

Predatorとの接触を常時の即死判定にはしない。Predatorは追跡で接近した後、開始時に
狙った方向へ12 tickだけ加速する。捕食行動が成功しても外れても、その後は
速度が下がるため、攻撃のたびに離脱可能な時間が生まれる。

~~~text
追跡 → 捕食行動（加速） → 捕食／離脱 → 休息／回復（低速）
~~~

接触時の捕食成功率は、Rabbitが`escape`を選び、かつ捕食者から離れる方向へ
0.8以上の速度が出ていれば28%、逃走がまだ成立していなければ78%とする。
離脱したRabbitは危険地点を個体記憶へ刻み、直ちに行動を再計画する。Predator側も
捕食成立、接触後の離脱、空振り、地形衝突を`attack`の実測結果として保持する。
死亡と生還の間に、両者へ学習可能な出来事を残すための最小モデルである。

## 共通エージェント文法

~~~text
RelationalAgent
├─ Rabbit + RabbitProfile
└─ Predator + PredatorProfile
~~~

`RelationalAgent`は連続位置、個体記憶、予測、信頼度、ローカル予測負荷、
デモ固有の適応圧、Leap、因果ログを共通に持つ。現在コード上には歴史的な
`H` / `xi` フィールド名が残るが、Core v2.3のH / ξとは同一視しない。
Profileは身体半径、視界、計画間隔、誤差次元、表示する内部状態を定める。
共通なのは更新文法であり、種ごとの価値勾配まで同一にはしない。

| 種 | 予測誤差の次元 | 主な価値勾配 |
|---|---|---|
| Rabbit | `resource / danger / motion` | 食、水、遮蔽、安全、探索、移動費 |
| Predator | `prey / attack / motion` | 獲物記憶、捕食機会、探索、追跡費 |

## Rabbitの意思決定

各Rabbitは、停止を含む13方向の候補を比較する。概念上の価値は次の構成。

~~~text
V(a) = resourceReliability × memoryWeight × (w_food F_food + w_water F_water)
     + w_cover F_cover
     + restValue + explorationValue
     - dangerReliability × w_danger F_danger
     - motionReliability × w_cost F_cost
     + seededNoise
~~~

`F_food` などは全知の物理場ではなく、その個体の記憶セルと現在の知覚から作る。
脅威が見えないとき、音は距離ではなく誤差を含む方向だけを与える。

## Predatorの意思決定

Predatorも停止を含む13方向を比較する。視界内のRabbitは短い先読み位置として、
見失ったRabbitは`prey`場に残った粗い位置仮説として評価する。標準の最短経路や
Rabbitの実座標を直接参照しないため、岩陰で見失えば読み違え、古い場所を探索する。

~~~text
V_pred(a) = preyReliability × memoryWeight × w_prey F_prey
          + attackReliability × w_attack F_attack
          + explorationValue + restValue
          - motionReliability × w_cost F_cost
          + seededNoise
~~~

## 予測差とローカルLeap（pre-v2.3互換経路）

意思決定ごとに三つの値を予測し、次の計画時に実測との差を取る。

| 成分 | 予測と実測 |
|---|---|
| `resource` | 食・水との接触による実際の流入 |
| `danger` | 視覚・音から受けた危険曝露 |
| `motion` | 期待移動量に対する実移動量。境界や未予測の岩との衝突を含む |

Predatorは別の三次元を使う。

| 成分 | 予測と実測 |
|---|---|
| `prey` | 視認または獲物記憶から予測した遭遇強度と、実際の視認強度 |
| `attack` | 捕食行動を開始した場合の成立予測と、捕食／離脱／空振りの結果 |
| `motion` | 期待追跡量に対する実移動量。地形衝突と停滞を含む |

現在のシミュレーション挙動を保つローカル制御則は次である。
これは **Core v2.3のE/H/ξ/θの定義式ではない**。

~~~text
local_error_i(t) = abs(observed_i(t) - predicted_i(t))
local_load_i(t)  = decay_i × local_load_i(t-1) + gain_i × local_error_i(t)
local_leap_threshold = clamp(theta_base - 0.26 × adaptation_pressure)
~~~

`max(local_load) >= local_leap_threshold` になると、最大成分に応じてローカルLeapする。

- Rabbitの`resource`: 古い食・水記憶を弱め、未訪問方向の価値を上げる。
- Rabbitの`danger`: 音への慎重さと安全距離を増やす。
- Predatorの`prey`: 古い獲物位置を弱め、探索範囲を広げる。
- Predatorの`attack`: 突進開始距離と獲物の先読み時間を変える。
- 両者の`motion`: 停滞地点や地形のコストを上げ、進行角を組み替える。

Leap後はローカル負荷を完全消去せず28%残す。この28%はデモ固有の継続挙動であり、
Core Hの一般法則としては扱わない。

### Core v2.3 canonical sidecar

現行Coreとの接続は別に次の順序を固定している。

~~~text
raw interaction(s)
  ↓ Purpose / B
RIB_B(t)
  ↓ same pre-update M_B
F(t)

later interaction(s)
  ↓ same Purpose / B
RIB_B(t+Δ)
  ↓ same pre-update M_B
F'(t+Δ)
  ↓
E = Δ(F, F')
  ↓ unresolved component only
H
~~~

`coverage / unknown relation / exploration pressure` はHとは別状態であり、
それらをCore ξへ数値化しない。

## 1 tick の更新順

1. 休眠資源の時計を進め、必要なら別地点で再生する。
2. Predatorが前回予測を評価し、知覚、記憶統合、ローカルLeap、行動選択を行う。
3. 捕食行動の接触を一度だけ解決する。RabbitとPredatorの双方が結果を保持する。
4. 各Rabbitへ、地形を含む視覚と音の知覚結果を渡す。
5. 計画tickなら前回予測を評価し、記憶統合、ローカルLeap判定、次行動選択を行う。
6. Rabbitを連続空間で移動し、閉境界と岩の衝突を解決する。
7. 資源との接触、摂取、休息、地形抵抗を適用する。
8. 生存限界を判定する。
9. 観測者専用メトリクスを読み出せる状態にする。

観察対象はRabbitだけでなくPredatorも選択できる。Predatorを選ぶと、獲物記憶、
探索履歴、`prey / attack / motion`のローカル負荷、捕食者自身の因果ログを表示する。

## 再現

URLの `seed` クエリで初期乱数系列を固定できる。

~~~text
./index.html?seed=2401
~~~

同じコード、同じseed、同じtick数なら `Simulation.snapshot()` は同じ状態を返す。

## テスト

リポジトリルートで実行する。

~~~bash
node --test tests/relational-ecology-lab.test.mjs tests/relational-ecology-lab-v23.test.mjs
~~~

既存テストは決定論、非共有記憶、共通`RelationalAgent`型、Predatorの限定知覚と
獲物記憶、捕食失敗からのローカルLeap、休眠からの別地点再生、閉境界、地形遮蔽、
壁沿い移動、捕食と岩の衝突、資源配置除外、観測読み出しの非介入を検証する。

`relational-ecology-lab-v23.test.mjs` は、raw observationとRIB_Bの分離、同じ
pre-update `M_B` でのF/F'形成、`E = Δ(F,F')`、resolved mismatchのH非流入、
coverageとH/ξの分離を固定する。

## 意図的に次段階へ残したもの

- `core.mjs` / `app.mjs` 内の歴史的な `H` / `xi` / `thetaEffective` 名を、
  `localLoad` / `adaptationPressure` / `localLeapThreshold` へ挙動不変で移行すること
- 繁殖と遺伝
- 匂い・痕跡による個体間の間接情報共有
- エピソード外側でのパラメータ探索

繁殖を先に加えると、個体内の学習と世代間の選択を同じ結果から判別しにくい。
次段階では、まず物理的な痕跡場、その後に繁殖、最後に外側のメタ探索を加える。
