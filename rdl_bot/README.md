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

## テスト

```bash
cd rdl_bot
python -m unittest discover        # 追加依存なし（stdlibのunittest）
```

APIキー不要。LLM呼び出しは行わず、検索・H蓄積・leap分岐・代謝・永続化を検証する。

---

## コマンド

| コマンド | 説明 |
|---------|------|
| `/llm on\|off\|once` | LLMモード切替 |
| `/h` | H状態表示（H_pre / H_post / θ） |
| `/sfo` | 現在のAI_SFOプロファイルを表示 |
| `/mbti <TYPE>` | MBTIタイプまたは `RDL_native_*` プリセットでSFOプロファイルを再初期化（例: `/mbti INTP`、`/mbti RDL_native_trickster`。大文字小文字は問わない） |
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
├── tests/           単体テスト（stdlibのunittestのみ・追加依存なし）
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
- θは leap のたびに ×1.05（上限5.0）で上がり、M_Δ相のたびに ×0.97 で初期値2.0へ向けて緩む。
  上げる経路しか無いと約30回のleapで上限に張り付き二度と反応しなくなるため、設計書 §2 の
  「動的調整」に合わせて両方向に動かしている（`relax_theta()`）
- **実ノードに対応しないIDのHは破棄する**（`forget()` / `prune()`）。`__llm__`・`__crisis__`・`__none__`
  といった疑似IDや、M_Δ相で退場済みのノードIDにHが溜まると、修正対象が存在せずleapで消化できない。
  放置するとそれが毎ターン `should_leap()` の最大値を占め続け、実在ノードのleapが永久に起きなくなる
  （例: LLM生応答を3回 `n` で否定すると `H_post["__llm__"]` が閾値を超え、以降の学習が止まる）

### κ（自己修正可能性）と散逸

借用実装層（`RDL_計算実装層_NN借用 v0.1` / `RDL_応用実装層_LangGraph_LangChain借用 v0.1`）から
Node 再設計なしに適用できる分を入れてある。

```
‖M_B‖(node) = confidence × (1 + 0.3×usage_count + 0.5×approval_count)
κ(node)     = exp(-‖M_B‖ / 5.0)
a_k         = min(cap, γ × ‖M_B‖)          散逸行列 A の対角成分
```

- **κ が整合側の更新率を絞る** — `dM_B/dt = κ·η·E·F^T − λ·M_B + ξ` の κ に相当。
  慣性が強くなるほど自分では動かなくなる（過学習防止であり、同時に M_B 絶対性の表現）
- **κ→0 のノードで応答するときは警告を出す** — 「確信が固まっている時こそレビューが要る」を
  構造から出す（LangGraph借用 §6 の κ ゲート。CLI では HITL の代わりにユーザーへ促す）
- **H が毎ターン受動的に散逸する** — `dH_vec/dt` の `−A·H_vec` 項。慣性の強い（M_B の得意な）
  方向ほど速く冷め、**弱い方向に熱が残る**。以前は完全ヒット・同意・leap という離散イベントで
  しか H が下がらず、この指向性が生まれなかった
- **関係保存則は逆算観測のみ** — `/h` が `‖M_B‖ · D[ξ] = 𝒦` を表示する。Core §4.2 のとおり
  𝒦 は直接観測できないので積として逆算するだけで、制御には使わない

### ノードライフサイクル

```
source: bootstrap_seed / llm_seed / llm_learned / graph_composed / manual
phase:  M_lat（候補）→ activation_count≥3 で M_act（安定）
status: active → quarantined（LLM off時に否定が閾値超過）
              → deprecated（LLM on時、修正ノードに置き換わった）
```

- 同梱の `seed_v0.1.json` は `bootstrap_seed` / confidence 0.5 で読み込まれる。設計書 §3.7 が定めるとおり
  「仮置きの足場」であり、内部経験の重みは `llm_seed` と同じ 0.1。ユーザー承認（`approval_count`）が
  積み重なって初めて内部経験へ変換される
- 実使用（`touch()`）のたびにTTLが回復し、使われ続ける限り経過ターン数だけでは死滅しない
- seed ノード（`bootstrap_seed` / `llm_seed`）は TTL<=0 かつ低confidenceで `retire_dead_nodes()` により削除（50ターンごと）
- 毎ターン `decay_confidence()` が全ノードに走る（TTLが尽きた未使用ノードのみ実質的に減衰する）
- `quarantined` / `deprecated` ノードは `search()` / `compose_from_graph()` の応答候補から除外される。`deprecated` ノードは `relations` 経由で後継ノードへ透過的にリダイレクトされる

### leap フロー — Hの発生位置と作用先を分離する

`should_leap()` が返すのは「グラフ全体で最もHが高いノード」であって、
「今回の入力に関係するノード」ではない。この2つを混同すると、今回とは
無関係な過去のノードの修正版が今回の返答になってしまう。そこで leap を
`LeapDecision`（target / **scope** / cause / trigger_event_seq / trigger_input）
として明示化し、scope で扱いを分けている。

```
should_leap() = True
  ├── current    今回一致したノード自身が熱い
  │                LLM:on  → ask_for_node_revision(hot_node, 現在入力)
  │                          → 修正版を作り旧ノードをdeprecated化、応答に使う
  │                LLM:off → 旧ノードをquarantine化（応答には使わない）
  ├── background 今回とは無関係なノードが熱い
  │                同上の修正を裏で行うが、**今回の応答としては返さない**。
  │                修正プロンプトにも現在入力を渡さない（内容が汚染されるため）
  ├── unresolved 未解決入力(PENDING_MISS_ID)の蓄積が閾値超過
  │                今回がmissなら ask_for_node() で新規学習して消化。
  │                LLMの成否や今回の一致有無によらず必ず減衰させる
  └── phantom    実体の無いID（__llm__ / __crisis__、退場済みノード）→ 破棄
```

`current` 以外では `trigger_input` が None になり、`ask_for_node_revision()`
はプロンプトから現在入力の行ごと落とす。

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
（`bootstrap_seed`/`llm_seed`=0.1 …「教わっただけ」/ `manual`=0.8 など）から始まり、
ユーザー承認（`approval_count`）が積み重なるほど1.0（自分で検証済み）に
近づく。これにより、LLMから教わっただけの知識を大量に持っていても
「経験豊富だからLLMを信用しなくなる」という誤判定を避けている。

quarantined/deprecatedノードは「否定され続けている経験」なので
internal_experienceには数えない。ドメインごとに独立して計算されるため、
概念空間は成熟していても身体空間はまだ幼い、といった非一様な成熟が起こる。

起動直後（seed 20件のみ）の信用度はおよそ 人0.43 / 概念0.46 / 身体0.55 /
物語0.95 / 制度0.95 で、外部LLMを足場として使える範囲にある。そのドメインの
ノードがユーザーに承認・使用されると 0.05 付近まで下がり、自力解決へ移る。

信用度は「miss時の早期相談」だけでなく、部分一致した内部応答の
confidenceがそのドメインの信用度を下回る場合にも、確率的にLLMへの
裁定（内部応答を使うかLLMに譲るか）に使われる。ドメイン推定は単一の
最近傍ノードではなく、文字N-gram類似度の上位k件による投票
（`NodeGraph.top_k_similar()` / `_infer_domain()`）で行う。

重み・上下限はすべて初期変数として `LLMTrustConfig`（`llm_trust.py`）に
まとまっており、`data/llm_trust_config.json` を置けばコードを触らずに
上書きできる（例: `{"trust_decay_scale": 0.7, "usage_weight": 0.5}`）。
`/trust` コマンドで現在の設定値とドメイン別信用度を確認できる。

### LLM応答のパース

`ask_for_node()` / `ask_for_node_revision()` / `seed_universal_nodes()` は JSON を要求するが、
LLMは素のJSON・コードフェンス付き・散文の前置き付きのいずれでも返しうる。`_extract_json()` は
①素のパース → ②コードフェンスの中身 → ③最初に現れる `{...}` / `[...]` の切り出し、の順で試す。
③では配列とオブジェクトのうちテキスト中で先に現れる方を優先し、配列内の最初の `{` を掴んで
一部だけ返すことを避けている。

### 永続化

- `graph.json`：ノードグラフ本体（原子的書き込み。書き込み中断時は `.corrupt` に退避して空グラフから再開）。
  学習したノードには生のユーザー入力が入りうる（`llm_learned` の inputs フォールバック、`counterexamples`）ため
  `.gitignore` 済み。無ければ起動時に `seed_v0.1.json` から作り直される
- `session_state.json`：`H_pre`/`H_post`/history、θとθ下限、SFOプロファイルとdrift_factor、ξプール、
  LLMモード、ターン数。50ターンごと・`/quit`終了時に保存し、起動時に自動復元する。
  会話由来の内容を含むため `.gitignore` 済み
- `AI_SFO.from_dict()` / `LLMTrustConfig.from_dict()` は未知のキーを無視する
  （バージョンをまたいで残る `session_state.json` で起動不能にしないため）

### 既知の制限（Phase 1）

- exact/partial一致自体は依然として部分文字列マッチ（表記ゆれ・同義語には弱い）
- miss時の最近傍探索は文字N-gram（分かち書き不要）に変更済みだが、埋め込みベースの意味的類似度ではない。
  類似度が `MIN_NEAREST_SIMILARITY`(0.05) 未満なら最近傍なしとし、そのmissのHは
  `HState.PENDING_MISS_ID` へ積む（無関係なノードにHを積むと、そのノードが誤って修正・隔離される）
- **Node が「観測・概念・関係・応答」を1つに混在させている。** `inputs`/`rdl_type`/`response` は
  発話に対する応答テンプレートであって、ユーザーのM_B構造そのものではない。時間変化・条件・
  内的葛藤・過去判断との反転関係などは保持できない
- **`relations` が型なしのID列で、2つの用途に多重化されている**（意味的なW_ij と
  deprecated→後継の履歴リンク）。`_resolve_active()` は `relations[-1]` を後継とみなすため、
  後から意味エッジを足すと後継解決が壊れる。型付きEdge（`successor_of` / `semantically_related_to` 等）
  への分離が必要
- グラフ内合成（LLM:off 時）は近傍借用のみ。W_ij による本格合成は Phase 4
- SFO・MBTI初期値・ξ pool・簡易M_Δ代謝は実装済み（`sfo_profile.py`）。SFOがノード選択自体に影響する仕組み、LLMへのノードグラフ文脈注入、W_ijの本格的な張り直しは未着手
- `NodeGraph.merge_or_split_nodes()` は空実装、`update_relations()` も片方向にIDを足すだけ（Phase D）
- 危機モードの発火条件は `H > θ×1.5` だが、θ超過の時点で先にleapが走るため実際にはほぼ到達しない。
  設計書 §3.4 の「H_post連続上昇」「齟齬の連鎖検出」に沿った判定への置き換えが必要
- `respond()` など主要関数が `(graph, h, llm, sfo_profile, xi_pool, llm_trust)` を引き回しており、
  状態が増えるほど引数が膨らむ。セッション状態を1つのオブジェクトにまとめる余地がある

---

## フェーズロードマップ（設計図より）

| Phase | 内容 | 状態 |
|-------|------|------|
| 0 | 普遍ノード種まき（手動 or LLM） | 完了 |
| A | CLIループ・H蓄積・leap・LLM学習 | 実装中 |
| B | SFO初期値（MBTI入力）・drift | 実装中 |
| C | ξ pool・M_Δ本格代謝 | 実装中 |
| D | W_ij・ノード間合成・限界の地図UI | 未着手 |
