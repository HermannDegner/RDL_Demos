# RDL Demos

RDL（関係力学言語 / Relational Dynamics Language）をベースにした実験デモ集。
ブラウザ上のビジュアルシミュレーションと、CLIチャットボットで構成される。

**GitHub Pages:** https://hermanndegner.github.io/RDL_Demos/

理論ベース: [Limit-Space_Relational-Dynamics-Language](https://github.com/HermannDegner/Limit-Space_Relational-Dynamics-Language)

---

## ブラウザデモ

番号は作成順や発展順と一致しなくなっていたため、内容を表すURLへ移した。
旧 demo0〜demo6 は互換用の転送入口として残している。

### 統合発展型

[RDL Living Field](demos/relational-ecology-lab/) は、既存デモで分かれていた要素を
一つの因果ループへ統合した発展実験。

- 共通`RelationalAgent`型で動く5体のRabbitと1体のPredator
- 草・水・遮蔽と、摂取 → 枯渇 → 休眠 → 別地点再生の資源循環
- 制限された視覚と、方向が曖昧な音
- Rabbitの食・水・危険記憶と、Predatorの獲物・捕食結果記憶
- 予測差 `E` の `H_vec` への蓄積と、実効閾値を越えたときの `Leap`
- fixed tick と seeded RNG による再現可能な実行

物理環境、個体の内部予測、観測者専用メトリクスは更新経路を分離している。
繁殖は、まずこの最小因果ループを説明可能に保つため意図的に含めていない。

### 生態系・行動の発展系列

同じ対象へ条件を加え、意味と行動がどう変わるかを見る系列。

> 勾配世界 → 感覚制約 → 複合資源 → 能動的脅威 → 資源転移 → 統合場

| 段階 | デモ | 焦点 | 旧URL |
|---|---|---|---|
| 1 | [勾配で動く最小生態系](demos/ecology-gradient-world/) | 草が食料と隠れ場を兼ね、覚醒状態によって意味が変わる | demo3 |
| 2 | [感覚が制約された少数戦術](demos/ecology-limited-senses/) | 視覚・音・遮蔽を分離し、情報制約を加える | demo4 |
| 3 | [複合資源による生存選択](demos/ecology-multi-resource/) | 水場を加え、空腹・渇き・危険を競合させる | demo5 |
| 4 | [能動的脅威とアンカー行動](demos/rabbit-active-threat/) | 追跡する脅威に対する退避と資源確保 | demo6 |
| 5 | [資源枯渇と即時転移](demos/rabbit-resource-relocation/) | 資源の転移により永続的な安全地帯を崩す | demo0 |
| 6 | [RDL Living Field](demos/relational-ecology-lab/) | 系列全体を個体別予測・H_vec・因果ログとともに統合する | 新規 |

### 探索・評価の再実装

| デモ | 焦点 | 旧URL |
|---|---|---|
| [近傍セル評価とパラメータ探索](demos/ecology-parameter-search/) | 81条件を比較し、生存・介入・脱出から実行パラメータを選ぶ | demo1 |

生態系系列と主題はつながっているが、コード上は格子モデルとして組み直した別実装。

### 場と経路の学習

| デモ | 焦点 | 旧URL |
|---|---|---|
| [Non-Euclidean Warp Navigation](demos/warp-navigation/) | 失敗を H_vec として場へ残し、フローから迷路内の経路を学ぶ | demo2 |

これは生態系系列から独立した、場の学習と経路形成の実験。

---

## URL移行

| 旧URL | 新URL |
|---|---|
| demo0/ | demos/rabbit-resource-relocation/ |
| demo1/ | demos/ecology-parameter-search/ |
| demo2/ | demos/warp-navigation/ |
| demo3/ | demos/ecology-gradient-world/ |
| demo4/ | demos/ecology-limited-senses/ |
| demo5/ | demos/ecology-multi-resource/ |
| demo6/ | demos/rabbit-active-threat/ |

旧URLへアクセスすると、クエリ文字列とハッシュを保ったまま新URLへ転送される。

## ディレクトリ構成

~~~text
RDL_Demos/
├── index.html
├── rdl_core/               RDL中核概念の汎用参照実装
├── rdl_profiles/           Bごとの仮設係数プロファイル
├── rdl_experiment/         係数探索・耐久指標
├── demos/
│   ├── ecology-gradient-world/
│   ├── ecology-limited-senses/
│   ├── ecology-multi-resource/
│   ├── rabbit-active-threat/
│   ├── rabbit-resource-relocation/
│   ├── relational-ecology-lab/
│   ├── ecology-parameter-search/
│   └── warp-navigation/
├── demo0/ ... demo6/       旧URLからの転送
└── rdl_bot/                CLIチャットボット
~~~

## rdl_core（参照実装）

`rdl_core/` は、RDL文書側の中核概念を特定デモに依存しない形で読むための
最小参照コードである。

- `Boundary`：境界 `B`
- `MBNode`：整合慣性 `M_B`
- `HVector`：予測誤差の蓄積 `H_vec`
- `LeapEngine`：`M_Δ -> M_B'` の再編
- `MBGraph`：`W_ij` / 入れ子状 `M_B` ネットワーク

現時点では既存デモから独立した土台として置き、安定した部分から徐々に
`RDL Living Field` などへ接続する。

係数は `rdl_core/` に閉じ込めず、Bごとの仮設として `rdl_profiles/` に置く。
係数探索と耐久検査は `rdl_experiment/` が担当する。

---

## rdl_bot（CLIチャットボット）

RDL語彙でユーザーの入出力を構造化し、H蓄積 → leap → LLM問い合わせ → ノード学習の
サイクルで自律拡張するボット。

~~~bash
cd rdl_bot
pip install -r requirements.txt
py main.py
~~~

APIキーなしでも動作する（手動 seed 20ノード付き）。
詳細は [rdl_bot/README.md](rdl_bot/README.md) を参照。
