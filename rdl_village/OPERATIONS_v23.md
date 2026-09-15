# Village v2.3 operational coverage

Village の canonical migration infrastructure は `main` で有限 context authority / explicit runtime / live re-entry まで到達している。本書はその後の運用支援を定義する。

## 原則

運用支援は review authority ではない。

```text
finite review candidate
  + bounded local absorption-attempt evidence
  + same finite B / Purpose / dimensions / conditions
  + same signed residual across distinct consecutive windows
        ↓
review recommendation only
        ↓
explicit reviewer still decides
ordinary-temporal / boundary-change / resolved / unresolved
```

したがって、recommendation 自体は `H` を増やさず、`M_Δ` を開始せず、`Probe / Selection / M_B'` を生成しない。

## `v23_review_assist.py`

`VillageReviewAdvisor` は既に形成された `VillageUnresolvedReviewCandidate` だけを読む。

既定では3個の異なる連続 candidate window を要求する。

持続runは次の場合に切れる。

- finite context が変わる
- 対象 dimension が candidate evidence から消える
- residual の符号が反転する
- `minimum_abs_residual` を使用している場合、その有限フィルタ以下へ落ちる

同じ candidate / later section を再読しても窓数には加算しない。

`minimum_abs_residual` は review queue を絞る demo-local operational filter であり、canonical `H` や `θ` ではない。

Recommendation は明示的に次を未確定のまま保持する。

- `classificationStatus = not-performed`
- `ordinaryTemporalChangeExcluded = false`
- `boundaryOrCoverageChangeExcluded = false`
- `authority = advisory-only`
- `xiStatus = unrecovered-relations-remain`

## `v23_operational.py`

`install_village_operational_coverage()` は既存の explicit canonical runtime を利用し、次だけを追加する。

- agentごとの review recommendation
- reviewer向け work queue
- install済み finite context の一覧
- active canonical runtime session の一覧

Work queue は candidate ID / dimension / evidence refs を示すが、review status や除外判定を事前入力しない。

```python
from rdl_village import VillageSimulation, install_village_operational_coverage

simulation = VillageSimulation(seed=7)
coverage = install_village_operational_coverage(
    simulation,
    theta=1.0,
    required_review_windows=3,
)

simulation.run(480)
print(coverage.snapshot())
```

## `v23_report.py`

read-only baseline を標準JSONとして取得する入口。

```bash
python -m rdl_village.v23_report --ticks 640 --seed 7 --theta 1.0 --review-windows 3
```

出力は agent ごとに次を含む。

- review candidate 数
- explicit review 数
- candidate が形成された finite place / band context
- dimension別 candidate 数
- advisory review recommendation
- explicit reviewだけから形成された canonical H の現状
- install済み finite context 数
- active canonical runtime session 数

このコマンド自身は explicit review を一件も実行しない。そのため baseline 実行だけで `unresolved-mismatch`、canonical H、`M_Δ`、`M_B'` が作られることはない。

同じ seed / tick / operational options は同じ baseline report を返すことをCIで確認する。

## 有限境界

一つの recommendation や install済み `M_B'` を別 place / band へ一般化しない。

```text
well / morning != well / evening
well / morning != garden / morning
```

観測されていない context は未移行のまま残る。これは欠落ではなく有限 `B` を維持するための仕様である。

## 変更していないもの

- `LocalLoadVector` は canonical H ではない
- `ExplorationState` は Core ξ ではない
- historical `LeapEngine` は未移行 context では compatibility/local authority として残る
- recommendation は unresolved の代理判定をしない
- finite reconstruction は terminal truth を主張しない
