# rdl_bot — RDL個人M_B外部化AI v0.1

RDL（関係力学言語）の語彙でユーザーの入出力を構造化し、  
H蓄積 → leap → LLM問い合わせ → ノード学習 というサイクルで自律拡張するCLIチャットボット。

---

## 起動

```bash
# 通常起動（graph.json が空なら seed_v0.1.json を自動ロード）
py main.py

# LLMで追加ノードを生成してから起動（ANTHROPIC_API_KEY 必要）
py main.py --seed
```

依存:
```bash
pip install -r requirements.txt   # anthropic>=0.40.0
```

APIキーなしでも seed_v0.1.json（手動20ノード）で最小動作する。

---

## コマンド

| コマンド | 説明 |
|---------|------|
| `/llm on\|off\|once` | LLMモード切替 |
| `/h` | H状態表示（H_pre / H_post / θ） |
| `/sfo` | 現在のAI_SFOプロファイルを表示 |
| `/mbti <TYPE>` | MBTIタイプに基づきSFOプロファイルを再初期化（例: `/mbti INTP`） |
| `/trust` | ドメイン（spatial_tag）別のLLM信用度と設定値を表示 |
| `/xipool` | ξプールの内容を表示 |
| `/graph` | グラフ統計（総ノード数・source別・phase別・status別） |
| `/hot` | H値が高いノードTOP3 |
| `/quit` | グラフ保存して終了 |
| `y / n / ?` | 直前応答へのフィードバック（同意 / 否定 / 言い換え要求） |

---

## ファイル構成

```
rdl_bot/
├── main.py          CLIループ + respond() + metabolize()
├── node_graph.py    Node / NodeGraph（検索・保存・読込）
├── h_state.py       HState（H_pre/H_post・leap判定）
├── llm_bridge.py    LLMBridge（Anthropic API・ξポンプ）
├── sfo_profile.py   AI_SFO（空間流向診断プロファイル・MBTI変換・drift機構）
├── llm_trust.py     LLMTrust（ドメイン別LLM信用度モデル）
├── requirements.txt
└── data/
    ├── seed_v0.1.json         手動 Phase 0 ノード（20件・APIキー不要）
    ├── graph.json             実行時に生成・更新される学習グラフ
    ├── session_state.json     H_pre/H_post・SFO drift・ξプール・LLMモードの永続化
    └── llm_trust_config.json  （任意）LLM信用度の初期変数を上書きする設定ファイル
```

---

## 設計メモ

### H（フラストレーション）

- `H_pre`：入力ミス時に蓄積（軽め、weight=0.4）
- `H_post`：ユーザー反応（deny/rephrase/silence）で蓄積（重め、weight=1.0）
- `should_leap()` は `H_pre×0.4 + H_post` の合成値で、全ノード中もっとも高いもの（`hot_nid`）について判定
- 閾値 θ=2.0 を超えると leap。`leap_done()` は対象ノードの `H_pre` / `H_post` を両方とも減衰させる
- `should_leap()` は **exact/partial一致時にも毎ターン確認する**（以前はmiss時にしか確認しておらず、否定され続けた既存ノードの応答が固定化する問題があった）

### ノードライフサイクル

```
source: manual / llm_seed / llm_learned / graph_composed
phase:  M_lat（候補）→ activation_count≥3 で M_act（安定）
status: active → quarantined（LLM off時に否定が閾値超過）
              → deprecated（LLM on時、修正ノードに置き換わった）
```

- `manual` ノードは実使用（`touch()`）のたびにTTLが回復し、使われ続ける限り経過ターン数だけでは死滅しない
- `llm_seed` ノードは TTL<=0 かつ低confidenceで `retire_dead_nodes()` により削除（50ターンごと）
- 毎ターン `decay_confidence()` が全ノードに走る（TTLが尽きた未使用ノードのみ実質的に減衰する）
- `quarantined` / `deprecated` ノードは `search()` / `compose_from_graph()` の応答候補から除外される。`deprecated` ノードは `relations` 経由で後継ノードへ透過的にリダイレクトされる

### leap フロー（既存ノードの修正 と 新規学習の両方をカバー）

```
should_leap() = True（hot_nid = 最もHが高いノード）
  ├── hot_nidが既存ノードに対応する
  │     ├── LLM:on  → ask_for_node_revision() → 修正版ノードを新規作成し
  │     │             旧ノードをdeprecated化、relationsで接続
  │     └── LLM:off → 旧ノードをquarantine化（応答には使わない）
  └── hot_nidが実ノードに対応しない（miss由来の新規パターン）
        ├── LLM:on  → ask_for_node() → Node(source=llm_learned, phase=M_lat)
        └── LLM:off → compose_from_graph()（近傍ノードのresponseを借用）
```

否定(`n`)・言い換え(`?`)の単発フィードバックは、応答内容そのものは書き換えず
`confidence` の減衰とノードへの反例記録（`counterexamples`）に留める。
応答内容の実際の修正は上記のleapフロー（H閾値超過）で行う設計。

### ドメイン別LLM信用度（幼少期の外部足場）

H閾値超過を待ってからLLMへ問い合わせる一様なゲートだけだと、内部グラフが
薄い起動直後でも「自力解決」を要求しすぎてしまう。そこで `spatial_tag`
（人/概念/物語/制度/身体）ごとに、内部経験がまだ薄いドメインでは
H閾値未達でも確率的にLLMへ早期相談できるようにしてある。

```
trust = trust_decay_scale / (trust_decay_scale + internal_experience)
internal_experience = Σ(そのドメインのactiveノードについて
                        experience_weight(node) × (node_weight
                        + usage_weight×usage_count + confidence_weight×confidence))
```

`experience_weight(node)` は、ノードの出自(`source`)に応じた基礎重み
（`llm_seed`=0.1 …「教わっただけ」/ `manual`=0.8 など）から始まり、
ユーザー承認（`approval_count`）が積み重なるほど1.0（自分で検証済み）に
近づく。これにより、LLMから教わっただけの知識を大量に持っていても
「経験豊富だからLLMを信用しなくなる」という誤判定を避けている。

quarantined/deprecatedノードは「否定され続けている経験」なので
internal_experienceには数えない。ドメインごとに独立して計算されるため、
概念空間は成熟していても身体空間はまだ幼い、といった非一様な成熟が起こる。

信用度は「miss時の早期相談」だけでなく、部分一致した内部応答の
confidenceがそのドメインの信用度を下回る場合にも、確率的にLLMへの
裁定（内部応答を使うかLLMに譲るか）に使われる。ドメイン推定は単一の
最近傍ノードではなく、文字N-gram類似度の上位k件による投票
（`NodeGraph.top_k_similar()` / `_infer_domain()`）で行う。

重み・上下限はすべて初期変数として `LLMTrustConfig`（`llm_trust.py`）に
まとまっており、`data/llm_trust_config.json` を置けばコードを触らずに
上書きできる（例: `{"trust_decay_scale": 0.7, "usage_weight": 0.5}`）。
`/trust` コマンドで現在の設定値とドメイン別信用度を確認できる。

### 永続化

- `graph.json`：ノードグラフ本体（原子的書き込み。書き込み中断時は `.corrupt` に退避して空グラフから再開）
- `session_state.json`：`H_pre`/`H_post`/history、SFOプロファイルとdrift_factor、ξプール、LLMモード、ターン数。
  50ターンごと・`/quit`終了時に保存し、起動時に自動復元する

### 既知の制限（Phase 1）

- exact/partial一致自体は依然として部分文字列マッチ（表記ゆれ・同義語には弱い）
- miss時の最近傍探索は文字N-gram（分かち書き不要）に変更済みだが、埋め込みベースの意味的類似度ではない
- グラフ内合成（LLM:off 時）は近傍借用のみ。W_ij による本格合成は Phase 4
- SFO・MBTI初期値・ξ pool・簡易M_Δ代謝は実装済み（`sfo_profile.py`）。SFOがノード選択自体に影響する仕組み、LLMへのノードグラフ文脈注入、W_ijの本格的な張り直しは未着手

---

## フェーズロードマップ（設計図より）

| Phase | 内容 | 状態 |
|-------|------|------|
| 0 | 普遍ノード種まき（手動 or LLM） | 完了 |
| A | CLIループ・H蓄積・leap・LLM学習 | 実装中 |
| B | SFO初期値（MBTI入力）・drift | 実装中 |
| C | ξ pool・M_Δ本格代謝 | 実装中 |
| D | W_ij・ノード間合成・限界の地図UI | 未着手 |
