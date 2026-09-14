# Core v2.3同期作業の再開地点

更新日: 2026-09-14。対象は `rdl_bot`。Demos全体の同期完了宣言ではない。

## 目的と参照版

更新されたCoreへ既存実装を同期する。新しいランタイムの作成や、グラフ変更権限の拡大は今回の差分に含めない。

| 参照 | 固定版 | 役割 |
|---|---|---|
| [RDL_Core](https://github.com/Aporapeiron/RDL_Core/tree/9272be829c2f80b211b2601a2c10a50ad1f2ad2c) | `9272be8` / BASE・SPEC v2.3 | 定義と最低動作の基準 |
| [RDL_Functions](https://github.com/Aporapeiron/RDL_Functions/tree/89cb5115158fd99293b0a920b7ed6b2fb5910daf) | `89cb511` | 有効範囲を持つ実装候補・入出力契約 |
| [RDL_Demos](https://github.com/HermannDegner/RDL_Demos/tree/b7757fb1c7ba581a882c0e97bcb1483d526fc459) | `b7757fb` | 中断時の調査・テスト再現対象 |

Coreの要件、Functionsの任意実装候補、Botの移行方策を区別する。固定θ、人間の明示レビュー、専用CLIはBotの選択であり、Coreが全実装へ要求する方式ではない。

## 中断時の4件の失敗と今回の修正

中断版のBotテスト341件をローカルで実行し、CIと同じ4件の失敗を再現した。

`llm_revision_v23.generate_canonical_revision()` は新しい `ask_for_canonical_node_revision(target, request)` を優先する。しかし `test_cli_v23._LLM` は旧 `ask_for_node_revision` しか提供せず、実クライアントも持たなかった。このため生成器が `None` を返し、成功を前提とするノード追加・一回限りの実行・再試行・永続化の検証が失敗していた。

今回の変更:

- CLIテストの模擬LLMをcanonical APIへ同期。
- 旧APIを呼んだ場合はテストを失敗させる。
- 実行時に対象ID、レビュー理由・判定者、元turnとreviewの証拠参照が渡ることを検証。
- 修正後、Botテスト **341件すべて成功**（Python 3.12、外部LLM呼出しなし）。

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=rdl_bot:. python -m unittest discover -s rdl_bot/tests -p 'test_*.py'
```

本体コード、起動入口、閾値、mutation権限は変更していない。実LLMの品質、クラッシュ耐久性、他デモの同期完了をこの結果から主張しない。

## Core・Functionsとの対応

| 要件・契約 | Botの対応 | 判定・限界 |
|---|---|---|
| Bと有限作用断面RIB_Bを明示 | `BoundaryContext`、`InteractionSection`、`acquire_text_section` | 実装済み。対話テキストの有限断面 |
| 更新前の同一M_BでF/F′を比較 | `FrozenGraphEvaluator`、later section replay | 実装済み。凍結対象はgraph側の検索評価器でありBot全体ではない |
| Eと未解消Hを分離 | policy/controller/authority | 実装済み。非ゼロEはpending、明示unresolvedのみ加算 |
| H/θによる再編判定 | `CanonicalLeapAuthority`、action gate | 専用入口で旧leap判断を無効化。通常入口は旧判断が残る |
| T1の検査・選別・再構成 | planner/executor/mutation adapter | 限定的実装。単一対象の提案・置換があることは、T1全体の実装完了を意味しない |
| ξとノイズ・未知入力件数を分離 | `CoverageState`、`UnresolvedInputQueue`、pressure hook=0 | 分離済み。旧CLI表示・コメントは残る |
| Functionの入力・出力・証拠を区別 | section→interpretation→mismatch→assessment→request→plan | 型・証拠を分離。全モジュールの最小適合条件を網羅的に検証したわけではない |
| 通常更新のκ・散逸等 | node/dynamics/authority入口の局所適応 | Functions由来の局所候補として検査。古いコードにあるという理由だけで削除しない |
| 相互作用への応答の戻り、SILNの対象化（C1/C11） | 会話と後続入力、有限評価器 | Core要件全体への対応説明と検証は残作業 |

FunctionsのNN借用文書はHを未解消不整合と定義する一方、まとめに `σ_vec = E` を置いている。未解消分の射影をどこで行うか、適用条件を確認する必要がある。Demosを全Eの自動加算へ戻す根拠にはしない。

## 起動入口ごとの実際の権限

| 入口 | 旧Hによるleap/correction | canonical review/plan | canonical execute |
|---|---|---|---|
| `main.py` | 有効 | なし | なし |
| `cli_v23.py` | 有効 | 有効 | 明示コマンドで可能 |
| `cli_v23_authority.py` | 無効 | 有効 | 明示コマンドで可能 |

`shadow` という内部名はread-onlyの保証ではない。`/v23 plan` 自体はグラフを変更しないが、どの対話入口もグラフ全体の凍結モードではない。

専用authority入口でも、通常のLLM相談からのノード追加、feedbackのconfidence更新、maintenanceの退場・キュー再評価からの追加、seed投入は残る。旧leapの禁止と、全構造変更の禁止は別の契約である。

## 旧実装の扱い

- `H_pre/H_post`、hot-node、旧leap/correctionは通常入口では稼働中。資料だけのlegacyではない。
- authority入口では旧feedback記録を維持するが、旧leap認可とH/θ依存のreinforcement量調整を切っている。
- `xi_pool` 名・`/xipool` 表示は互換名。件数をCore ξと解釈しない。
- 旧中間設計図は形成史。現行Coreの定義根拠にはしない。
- κや散逸などの局所モデルは採用条件を調べる。Core必須でも、一律廃止対象でもない。

## 再開後の順序

1. **今回完了**: 中断版の失敗再現、テストAPI同期、Bot全テスト成功。
2. **次の最小段階**: 通常入口切替の前に、上の各変更経路を「通常の局所適応」「再編」「移行中の互換処理」へ対応づける。必要な動作を残す判断と、誤って新たなmutation経路を有効化しない判断を分ける。
3. canonical実行を運用上の完成扱いにする前に、外部API例外、部分的な証拠欠落、graph保存とexecution audit保存の間のクラッシュを確認する。現行テストの正常再起動時のone-shot保証を、二ファイルの原子的コミット保証と混同しない。
4. 通常入口のauthority切替は未実施。互換APIの隔離と他デモのCore同期は別途追跡する。

再起動時はreview/Hを復元するが凍結評価器は復元しない。旧証拠で対象を計画できない状態を未実装の自動再実行で補わない。


## 続行分: 旧処理の責務と診断表示の同期

前段コミット `ba640ad` のPR / push CIはともに成功した。以下を追加で確認・修正した。

| 処理 | 現在の責務 | 今回の扱い |
|---|---|---|
| `Node.inertia/kappa/reinforce` | confidence・使用・承認に基づく局所適応 | 数式を維持。Core必須則・ノード=M_Bという説明を訂正 |
| `dissipation_rates` → `LegacyFeedbackLoadState.dissipate` | 旧feedback/loadの減衰 | Functionsの散逸候補との関係を明示。canonical Hの減衰とは別 |
| `_reinforce_along_v_b` | 通常入口の旧H/θ依存slack | 互換処理として維持。authority入口のthreshold-neutral helperとは区別 |
| `_decide_leap` → `_correct_node` | 旧負荷による置換・隔離 | 通常入口では残存、authority入口では遮断。今回変更なし |
| `_learn_new_node`・partial裁定 | LLM相談による新規ノード取得 | 構造を変更する通常学習。Coreの再編と同一視しない。今回変更なし |
| `metabolize` | タイマーによる減衰・退場・キュー再評価・drift | H/θ判定を経ないため表示をmaintenanceに訂正。追加・削除は従来どおり残る |
| `phase0_seed` / bootstrap | 初期データの投入 | 再編認可とは別。今回変更なし |
| canonical review/plan/execute | 未解消Eの審査・対象計画・明示実行 | 前段で検証済みの経路を維持 |

`/h`は、常に0の互換pressureをCore ξと見なして𝒦を逆算する表示を廃止した。代わりにローカル慣性、キュー件数、正規化されたqueue診断を表示する。診断量を閾値へ接続してはいない。

`/dyn`は、旧pressureモデルの仮定計算とlive CLIでの切断を区別する。`/xipool`というコマンド名・保存キーは維持し、内容は未処理入力キューと表示する。

旧テストの「キューが閾値へ結線されている」という名前も訂正した。実際にはキューを渡さずpressureを直接注入する互換実験であり、その既存アサーションは変更していない。

続行分の検証: Bot全341テスト成功。診断コマンドを実行してグラフ・旧負荷・キューが変わらないことを確認。次の未完了事項は通常入口のauthority切替と、canonical実行の例外・保存境界の確認である。今回、変更権限の追加や入口切替は行っていない。
