# Living Field / Villageの移行再開地点

2026-09-14。Core `9272be8`（BASE / SPEC v2.3）とFunctions `89cb511`を基準とする。
Demos調査基点は `b7757fb`。Bot修正PR #9の上に積む独立差分であり、Botの追加変更は含めない。

## 先にLiving Fieldを扱う理由

| 対象 | 実際の経路 | 次に必要なこと |
|---|---|---|
| Living Field | Rabbit/PredatorのevaluateDecision → recordPredictionErrors → ローカル負荷・reliability更新 → maybeLeap | 共通の観測箇所へ、行動非介入の比較を接続できる |
| Village | evaluate_prediction内で移動・資源・関係・目標の誤差、対人再活性化、対話圧・不快、退屈を統合 → h_vec / xi → LeapEngine | 異なる役割の量を取得・解釈・残差・直接動機へ先に分解する |

両者とも、既存のv2.3比較モジュールがあることと、シミュレーションの行動判断が
canonical経路へ移行済みであることは別。Villageの `ledger.errors` 全体を
そのままCore E/Hと呼び替えない。Functionsの局所モデルも、その適用境界を明示する。

## 今回の接続

```js
const simulation = new Simulation({ seed: 2401, observeV23: true });
simulation.step(720);
const diagnostics = simulation.v23Snapshot();
```

- `evaluateDecision` の正規化済みobservedを有限作用断面の実装近似として取得する。
  decision.predictionやlegacy Hを作用断面へ流用しない。
- 有限評価器は取得時のreliability係数をコピーした重み付き変換。
  個体の記憶・意思決定全体を表すM_Bではない。
- 同じ以前の係数で二つの観測断面を解釈し、F/F′とEを記録する。
- ここでのEは**隣接する観測窓の重み付き解釈差**。旧予測の正誤、損失、
  再編の必要性をそのまま意味しない。Functionsの目的付き局所写像として扱う。
- 非ゼロ差は `pending-assessment`、ゼロ差は `zero-difference`。
  Hへの加算、閾値判定、再編、レビュー機能は追加していない。
- Predatorのattackは対象外。攻撃未試行を失敗ゼロとして扱わないため、
  試行単位の別境界を設計するまでprey/motionだけを比較する。
- 選択次元の欠測・非有限値があれば比較窓を切る。欠測をゼロへ変換しない。
- 最新比較と件数だけを保持し、履歴は無制限に蓄積しない。
  個体間で共有せず、エピソード再生成時は新しい比較窓にする。
- 既定は無効。ブラウザUIや既存snapshotのschemaは変更しない。

## 検証

新テストは固定seed 41 / 2401について、観測あり・なしを90tickごとに720tickまで比較する。
snapshotだけでなく、個体記憶、reliability、ローカル負荷、意思決定、因果ログ、
乱数状態も一致することを要求する。Rabbit/Predator両方で実比較が発生することも確認する。

加えて、係数の凍結、欠測時の比較中断、snapshotの不変性、個体・エピソード間の分離を検証する。
ローカル環境が利用できないため実行検証はGitHub Actionsで行う。

## 残作業

1. Living Fieldで、この比較から何を予測不整合・未解消分と判定するかを定義する。
   時間変化を自動で失敗と分類しない。現在の観測器はその判断のための足場。
2. 攻撃試行の観測境界・未試行・成功/失敗を分離する。
3. VillageはErrorLedgerへ入る各量と、いつモデル更新が起きるかを分解する。
   とくにrelation評価と移動記憶更新の前後を分け、更新後モデルで以前のFを再生成しない。
4. 行動・再編authorityの切替は別段階。旧ローカルLeapを今回の比較で置き換えていない。
