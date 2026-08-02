"""
main.py
RDL個人M_B外部化AI - CLI ループ (Phase 0 + Phase A/B)

使い方:
  python main.py              通常起動
  python main.py --seed       Phase 0: LLMで初期ノードを種まきしてから起動

コマンド（会話中）:
  /llm on|off|once            LLMモード切替
  /h                          H状態を表示
  /sfo                        AI_SFOプロファイルを表示
  /mbti <TYPE>                MBTIタイプでSFOプロファイルを再初期化
  /trust                      ドメイン別LLM信用度を表示
  /dyn                        動態係数とその帰結を表示
  /xipool                     ξプールを表示
  /graph                      グラフ統計を表示
  /hot                        H高いノードを表示
  /quit                       終了
  y / n / ?                   直前の応答へのフィードバック（y=同意 n=否定 ?=言い換え）
"""

import sys
import os
import math
import random

# Windows での文字化け防止
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdin.reconfigure(encoding="utf-8")

# カレントディレクトリを data/ の親に合わせる
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import json
from dataclasses import dataclass
from typing import Optional

import dynamics
from dynamics import load_dynamics_config
from node_graph import NodeGraph, Node, SEED_SOURCES
from h_state import HState, xi_pressure
from llm_bridge import LLMBridge
from sfo_profile import AI_SFO, DEFAULT_SFO_PRESET, create_sfo_profile_from_mbti
from llm_trust import LLMTrust, LLMTrustConfig


BANNER = """
========================================
  sumitsuku-AI  /  RDL Bot  v0.1
  Phase 0->A/B  CLI prototype
========================================
  /llm on|off|once  /h  /sfo  /mbti  /trust  /dyn  /xipool  /graph  /hot  /quit
  feedback: y(agree) n(deny) ?(rephrase)
"""

SESSION_STATE_PATH = "data/session_state.json"
LLM_TRUST_CONFIG_PATH = "data/llm_trust_config.json"
DYNAMICS_CONFIG_PATH = "data/dynamics_config.json"
DOMAIN_TAGS = ["人", "概念", "物語", "制度", "身体"]

# 「入力を捉えられたか」の実測値。E_match = |observed − predicted| の observed 側。
MATCH_OBSERVATION = {"exact": 1.0, "partial": 0.6, "miss": 0.0}


def _observed_acceptance() -> dict:
    cfg = dynamics.CONFIG
    return {
        "y": cfg.observed_agree,
        "?": cfg.observed_rephrase,
        "n": cfg.observed_deny,
        "": cfg.observed_silence,
    }


def _predicted_acceptance(graph: NodeGraph, node_id: str) -> float:
    """
    「この応答は受け入れられる」という M_B 自身の予測。

    応答を担ったノードの confidence が、そのままその方向の慣性の強さ
    （＝どれだけ自信を持って出したか）なので予測値に使う。
    ノードが無い応答（グラフ内合成・LLM生応答・危機モード）は
    内部に根拠が無いので設定値の低い予測を使う。
    """
    node = graph.get_by_id(node_id)
    if node is None:
        return dynamics.CONFIG.fallback_predicted_acceptance
    return node.confidence


def _error_note(error: Optional[float], fallback: float) -> str:
    """フィードバック表示用。E駆動なら実際の増分を、そうでなければ従来値を示す。"""
    if error is None:
        return f"H_post +{fallback:.1f}"
    return f"E={error:.2f} → H_post +{dynamics.CONFIG.e_gain_acceptance * error:.2f}"


def load_llm_trust_config(path: str) -> LLMTrustConfig:
    """
    LLM信用度の初期変数を読み込む。ファイルが無い/壊れていればデフォルト値。
    コードを触らずに data/llm_trust_config.json を置くだけで調整できる。
    """
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return LLMTrustConfig.from_dict(data)
    except FileNotFoundError:
        return LLMTrustConfig()
    except json.JSONDecodeError:
        print(f"  [ERROR] LLM信用度設定のJSONが壊れています ({path})。デフォルト値を使います。")
        return LLMTrustConfig()


def apply_feedback(fb: str, last_node_id: str, last_input: str, graph: NodeGraph, h: HState) -> None:
    """
    フィードバックはHだけでなく、ノード自体（confidenceと反例）にも反映する。
    実際の応答内容の修正（response書き換え）はH閾値超過によるleap
    （_correct_node）側で行う。単発のy/n/?で毎回応答内容自体を
    書き換えると単一の雑音入力で乱高下するため、ここではノードの
    信頼度調整と証跡の記録に留める。
    """
    fb = fb.strip().lower()
    node = graph.get_by_id(last_node_id)

    # 実測（Δの終点）: 応答時に書き留めた受容予測と突き合わせて E を出す。
    observed = _observed_acceptance().get(fb)
    error = h.close_decision(observed) if observed is not None else None

    if fb == "n":
        h.on_deny(last_node_id, error)
        if node:
            node.confidence = max(0.05, node.confidence * 0.85)
            node.record_counterexample(last_input, "deny")
            graph.save()
        print(f"  → 否定を記録しました ({_error_note(error, 1.0)}, confidence減衰)")
    elif fb == "?":
        h.on_rephrase(last_node_id, error)
        if node:
            node.confidence = max(0.05, node.confidence * 0.95)
            node.record_counterexample(last_input, "rephrase")
            graph.save()
        print(f"  → 言い換えを記録しました ({_error_note(error, 0.3)}, confidence減衰)")
    elif fb == "y":
        h.on_agree(last_node_id, error)
        if node:
            node.confidence = min(1.0, node.confidence * 1.05)
            node.approval_count += 1
            node.touch()
            graph.save()
        print(f"  → 同意を記録しました (H_post x0.7, {_error_note(error, 0.0)}, "
              f"confidence微増, approval_count+1)")
    # 空Enterは H を上げない


def feedback_prompt(last_node_id: str, last_input: str, graph: NodeGraph, h: HState) -> None:
    """応答後のフィードバックを求める。"""
    fb = input("  [fb] > ")
    if fb.strip() == "":
        fb = ""  # 空Enterは沈黙として観測する
    apply_feedback(fb, last_node_id, last_input, graph, h)


def print_dynamics(graph: NodeGraph) -> None:
    """
    動態係数と、その帰結を表示する。

    これらの係数は Core にも借用実装層にも決定則が無く、実際に動かした
    感触でしか決まらない（NN借用 v0.1 の残課題そのもの）。
    「γ=0.01」だけ見ても調整できないので、半減期のような
    解釈できる形に直して並べる。
    """
    cfg = dynamics.CONFIG
    print(f"  動態係数（{DYNAMICS_CONFIG_PATH} で上書き可）:")
    print(f"    {cfg.to_dict()}")

    print("  帰結:")
    # θ が上限に張り付くまでの leap 回数
    if cfg.theta_raise_on_leap > 1.0 and cfg.theta_max > cfg.theta_initial:
        n = math.ceil(math.log(cfg.theta_max / cfg.theta_initial)
                      / math.log(cfg.theta_raise_on_leap))
        print(f"    θ: leap {n} 回で上限 {cfg.theta_max} に到達"
              f"（M_Δ相ごとに ×{cfg.theta_relax} で初期値へ戻る）")

    # ξ圧が最大のときの θ_eff の範囲
    lo = 1 - cfg.xi_drop_ratio - cfg.xi_jitter_ratio
    hi = 1 - cfg.xi_drop_ratio + cfg.xi_jitter_ratio
    print(f"    ξ: プール {cfg.xi_saturation:.0f} 件でξ圧1.0 → "
          f"θ_eff は θ×[{lo:.2f}, {hi:.2f}] に揺れる")

    # κゲートが発動する慣性
    if 0 < cfg.kappa_hitl_threshold < 1:
        m_b = -cfg.kappa_m0 * math.log(cfg.kappa_hitl_threshold)
        print(f"    κ: ‖M_B‖>{m_b:.1f} で自力修正不能とみなす"
              f"（例: confidence 1.0 なら使用 {m_b / max(cfg.inertia_usage_weight, 1e-9):.0f} 回相当）")

    # 散逸の半減期
    print("    散逸（H が半減するまでのターン数）:")
    for label, conf, usage, appr in (
        ("同梱seed  ", 0.5, 0, 0),
        ("定着中    ", 0.9, 10, 0),
        ("絶対化    ", 1.0, 30, 10),
    ):
        n = Node(inputs=["_"], confidence=conf)
        n.usage_count, n.approval_count = usage, appr
        rate = min(cfg.dissipation_cap, cfg.dissipation_gamma * n.inertia())
        half = math.log(2) / rate if rate > 0 else float("inf")
        print(f"      {label} ‖M_B‖={n.inertia():5.2f}  a_k={rate:.3f}  半減期={half:.0f}ターン")

    # 実グラフの現状
    if graph.nodes:
        kappas = [n.kappa() for n in graph.nodes.values() if n.status == "active"]
        if kappas:
            frozen = sum(1 for k in kappas if k < cfg.kappa_hitl_threshold)
            print(f"    現状: activeノード{len(kappas)}件  κ中央値="
                  f"{sorted(kappas)[len(kappas) // 2]:.3f}  自力修正不能={frozen}件")


def handle_command(cmd: str, llm: LLMBridge, graph: NodeGraph, h: HState, sfo_profile: AI_SFO, xi_pool: list[str], llm_trust: LLMTrust) -> bool:
    """コマンド処理。Trueなら次のループへ。"""
    parts = cmd.strip().split()
    name = parts[0]

    if name == "/quit":
        graph.save()
        save_session_state(SESSION_STATE_PATH, h, sfo_profile, xi_pool, llm.mode, _turn_count)
        print("グラフとセッション状態を保存して終了します。")
        sys.exit(0)

    elif name == "/llm":
        if len(parts) < 2:
            print(f"  LLMモード: {llm.mode}  (利用可能: {llm.available()})")
        else:
            mode_map = {"on": "on", "off": "off", "once": "on-once"}
            m = mode_map.get(parts[1])
            if m:
                llm.set_mode(m)
                print(f"  LLMモード → {llm.mode}")
            else:
                print("  on / off / once を指定してください")

    elif name == "/h":
        pressure = xi_pressure(xi_pool)
        print(f"  {h.summary(pressure)}")
        # 関係保存則 ‖M_B‖·D[ξ] = 𝒦 の逆算（Core §4.2）。
        # 𝒦 は直接観測できないので積として逆算するだけで、制御には使わない。
        m_b = graph.m_b_norm()
        print(f"  ‖M_B‖={m_b:.2f}  D[ξ]≈{pressure:.2f}  𝒦≈{m_b * pressure:.2f}"
              f"   （𝒦は逆算値。制御には使わない）")

    elif name == "/sfo":
        print(f"  AI_SFOプロファイル: {sfo_profile.to_dict()}")

    elif name == "/mbti":
        if len(parts) < 2:
            print("  MBTIタイプを指定してください (例: /mbti INTP)")
        else:
            # 大文字化はしない。プリセット名には RDL_native_* のように
            # 混在ケースのキーがあり、検索側で正規化される。
            new_sfo = create_sfo_profile_from_mbti(parts[1])
            sfo_profile.main_foreground_space = new_sfo.main_foreground_space
            sfo_profile.hierarchy_bias = new_sfo.hierarchy_bias
            sfo_profile.得意操作 = new_sfo.得意操作
            sfo_profile.苦手操作 = new_sfo.苦手操作
            sfo_profile.attention_mode = new_sfo.attention_mode
            sfo_profile.initial_fingerprint = new_sfo.initial_fingerprint
            sfo_profile.drift_factor = 0.0 # MBTI変更でドリフトをリセット
            print(f"  SFOプロファイルを {new_sfo.initial_fingerprint} に基づいて初期化しました。")

    elif name == "/trust":
        print(f"  LLM信用度設定: {llm_trust.config.to_dict()}")
        for tag, trust in llm_trust.trust_by_domain(graph, DOMAIN_TAGS).items():
            exp = llm_trust.internal_experience(graph, tag)
            print(f"    {tag}: trust={trust:.2f}  internal_experience={exp:.2f}")

    elif name == "/dyn":
        print_dynamics(graph)

    elif name == "/xipool":
        if not xi_pool:
            print("  ξプールは空です。")
        else:
            print("  ξプール内容:")
            for i, item in enumerate(xi_pool):
                print(f"    {i+1}. {item}")

    elif name == "/graph":
        s = graph.stats()
        print(f"  ノード総数: {s['total']}")
        print(f"  ソース別: {s['by_source']}")
        print(f"  フェーズ別: {s['by_phase']}")

    elif name == "/hot":
        hot = h.hot_nodes()
        if not hot:
            print("  H蓄積なし")
        for nid, v in hot:
            n = graph.get_by_id(nid)
            label = n.rdl_type if n else nid
            print(f"  {label} ({nid}): {v:.2f}")

    else:
        print(f"  不明なコマンド: {name}")

    return True


_turn_count = 0


def metabolize(graph: NodeGraph, sfo_profile: AI_SFO, xi_pool: list[str], h_state: HState, retire: bool = False):
    """M_Δ相: 定期再編フェーズ (設計書 v0.3 §3.6)"""
    print("  [M_Δ相] 代謝フェーズ開始...")

    # 0. 熱の散逸 dH_vec/dt の -A·H_vec 項（NN借用 v0.1 §4）。
    # 慣性の強い（M_Bの得意な）方向ほど速く冷め、弱い方向に熱が残る。
    h_state.dissipate(graph.dissipation_rates())

    # 1. 低confidence・低使用頻度ノードのTTL減算と削除
    for n in list(graph.nodes.values()):
        n.decay_confidence()
        # seed ノードの retirement 判定 (設計書 v0.3 §3.7 Seedの取り扱い原則)
        # ユーザー由来ノードに置換されきった seed は削除候補。
        # 同梱の bootstrap_seed も llm_seed と同じく仮置きの足場なので対象。
        if n.source in SEED_SOURCES and n.confidence < 0.3 and n.usage_count == 0:
            n.ttl = 0 # 即時削除対象とする

    if retire:
        graph.retire_dead_nodes()

        # 1b. 退場したノードのH蓄積を破棄する。
        # グラフから消えたノードIDのHが残ると、修正対象が存在しないまま
        # should_leap() の最大値を占め続け、実在ノードのleapを妨げる。
        stale = h_state.prune(graph.nodes.keys())
        if stale:
            print(f"  [M_Δ相] 実体を失った {stale} 件のH蓄積を破棄しました。")

        # 1c. leapのたびに上がったθを初期値へ向けて緩める（設計書 §2 動的調整）
        h_state.relax_theta()

        # 2. 類似ノード群のマージまたは分割 (プレースホルダー)
        graph.merge_or_split_nodes()

        # 3. W_ijエッジの張り直し（実使用パターンに基づく） (プレースホルダー)
        # 現状では node.relations を直接更新するロジックがないため、ここではスキップ
        # graph.update_relations(active_node_id, related_node_ids) # 呼び出し例

        # 4. ξプールの再評価 (設計書 v0.3 §3.5)
        if xi_pool:
            print(f"  [M_Δ相] ξプール ({len(xi_pool)}件) を再評価中...")
            re_evaluated_xi = []
            for item in xi_pool:
                # ここで再度LLMに問い合わせるか、グラフ内検索を試みる
                # 今回は簡易的に、グラフ内検索を試みる
                node, match_type, _ = graph.search(item)
                if node and match_type != "miss":
                    print(f"    → ξプールからノード化成功: {item}")
                    # 新規ノードとして追加（source: graph_composedとして扱う）
                    new_node = Node(inputs=[item], rdl_type=node.rdl_type, spatial_tag=node.spatial_tag, response=node.response, source="graph_composed", confidence=0.7)
                    graph.add(new_node)
                else:
                    re_evaluated_xi.append(item) # まだノード化できないものはプールに残す
            xi_pool[:] = re_evaluated_xi # ξプールを更新
            if not xi_pool: print("  [M_Δ相] ξプールが空になりました。")

        # 5. SFOプロファイルの微調整・drift_factor 更新 (設計書 v0.3 §3.4 ドリフト機構)
        # 以前はhistory全体を毎回数え直しており、同じイベントが何度も
        # drift_factorに加算されていた。前回チェックポイント以降の
        # 差分だけを集計するdrift_deltas()に置き換える。
        deltas = h_state.drift_deltas()
        sfo_profile.update_drift(deltas)
        print(f"  [M_Δ相] SFOプロファイル drift_factor: {sfo_profile.drift_factor:.2f}")

    print("  [M_Δ相] 代謝フェーズ完了。")


def compose_from_graph(user_input: str, graph: NodeGraph) -> tuple[str, str]:
    """
    LLM:off 時の暫定グラフ内合成。
    最も入力とパターン長が近い部分一致ノードの response を借りる。
    """
    text_lower = user_input.lower()
    best_node = None
    best_score = 0.0

    for node in graph.nodes.values():
        if node.status in ("quarantined", "deprecated"):
            # 隔離・非推奨ノードの内容をここで借用すると、
            # せっかく否定を受けて隔離した回答をまた出してしまう。
            continue
        for pattern in node.inputs:
            pattern_lower = pattern.lower()
            if pattern_lower in text_lower or text_lower in pattern_lower:
                # 以前は len(pattern)/len(text) で、長い登録パターンほど
                # 過剰に高得点になっていた。短い方/長い方の比率に修正。
                shorter = min(len(pattern_lower), len(text_lower))
                longer = max(len(pattern_lower), len(text_lower), 1)
                score = (shorter / longer) * node.confidence
                if score > best_score:
                    best_score = score
                    best_node = node

    if best_node and best_score > 0.1:
        resp = best_node.response or f"[{best_node.rdl_type}（近傍合成）]"
        return f"{resp}（※近傍合成）", best_node.id

    return "[未知の入力です。/llm on で外部参照できます]", "__none__"


@dataclass
class LeapDecision:
    """
    このターンに発火したleapの内容。
    Hがどこに溜まったか（target）と、それが今回の入力に由来するか
    （scope）を明示的に分けて持つ。以前はこの区別が無く、今回の入力とは
    無関係なノードの修正版がそのまま今回の応答として返っていた。
    """
    target_node_id: str
    scope: str          # "current" | "background" | "unresolved" | "phantom"
    cause: str          # deny / rephrase / miss / silence / unknown
    trigger_event_seq: int
    # 修正プロンプトに渡してよい現在入力。scope="current" のときだけ入る。
    trigger_input: Optional[str] = None



def _reinforce_along_v_b(node: Node, h: HState, pressure: float, base_rate: float) -> None:
    """
    整合領域（H < θ_eff）における dM_B/dt を適用する（Core §6.1）。

    更新量は二つの係数で絞る：
      slack : θ_eff への近さ。H が 0 なら満額、θ_eff に近づくほど 0 に漸近し、
              超えれば跳躍側（_correct_node）へ移る。これにより整合と跳躍が
              「同じ量 H に対する連続な応答」になる（Core §6.3）
      κ     : 自己修正可能性（NN借用 v0.1 §1 の dM_B/dt = κ·η·E·F^T ...）。
              慣性が強くなるほど更新率が下がる＝過学習防止であり、
              同時に「固まった構造は自分では動かない」という M_B 絶対性の表現

    以前は整合側の dM_B/dt がそもそも存在せず（touch と usage_count だけ）、
    H閾値を境に「何も起きない」から「全面再編」へ不連続に飛んでいた。
    """
    theta_eff = h.theta_eff(pressure)
    if theta_eff <= 0:
        return
    slack = max(0.0, 1.0 - h.merged_h(node.id) / theta_eff)
    node.reinforce(base_rate * slack * node.kappa())


def _warn_if_self_correction_is_lost(node: Node) -> None:
    """
    κ→0 の領域（LangGraph借用 v0.1 §6 の κ ゲート）。

    慣性が固まりすぎて自力では修正できないノードで応答している場合、
    自動更新に任せず、ユーザーの判断を仰ぐべき箇所であることを示す。
    「確信が固まっている時こそレビューが要る」を構造から出す。
    """
    kappa = node.kappa()
    if kappa < dynamics.CONFIG.kappa_hitl_threshold:
        print(f"  [κ={kappa:.3f} — この応答は慣性が固まっており自力で修正できません。"
              f"誤っていれば n で否定してください]")


def _decide_leap(h: HState, graph: NodeGraph, match_type: str, node: Optional[Node],
                 user_input: str, pressure: float = 0.0) -> Optional[LeapDecision]:
    """
    H閾値を超えたノードを特定し、それが今回の入力とどう関係するかを判定する。

    scope:
      current    今回一致したノード自身が熱い → 修正して今回の応答に使う
      background 今回とは無関係なノードが熱い → 裏で修正するが応答には使わない
      unresolved 未解決入力の蓄積が閾値超過 → 今回がmissなら新規学習で消化
      phantom    実体の無いID（__llm__ など、退場済みノード）→ 破棄
    """
    leap_needed, hot_nid = h.should_leap(pressure)
    if not leap_needed:
        return None

    common = {
        "target_node_id": hot_nid,
        "cause": h.dominant_cause(hot_nid),
        "trigger_event_seq": h.last_event_seq(hot_nid),
    }

    if hot_nid == HState.PENDING_MISS_ID:
        return LeapDecision(scope="unresolved", **common)

    hot_node = graph.get_by_id(hot_nid)
    if hot_node is None:
        return LeapDecision(scope="phantom", **common)

    if match_type in ("exact", "partial") and node is not None and node.id == hot_node.id:
        return LeapDecision(scope="current", trigger_input=user_input, **common)

    return LeapDecision(scope="background", **common)


def _correct_node(hot_node: Node, decision: LeapDecision, graph: NodeGraph, h: HState, llm: LLMBridge) -> tuple[Optional[str], Optional[str]]:
    """
    否定・言い換えのHが閾値を超えて蓄積した既存ノード(hot_node)を修正する。
    LLM on: LLMに既存の誤答・否定履歴を渡して代替ノードを生成し、
            hot_nodeはdeprecated化してrelationsで新ノードにつなぐ。
    LLM off: 代替を生成できないので、hot_nodeをquarantine化するだけに留める
             （このノードはsearch()/compose_from_graph()の対象から外れる）。

    現在入力は decision.trigger_input 経由でのみ渡す。背景ノードの修正に
    今回の無関係な入力を混ぜると、修正内容そのものが汚染される。
    """
    label = "既存ノードを再評価" if decision.scope == "current" else "背景ノードを再評価"
    print(f"  [H閾値超過 → {label}: {hot_node.rdl_type} (cause={decision.cause})]")

    if llm.mode in ("on", "on-once") and llm.available():
        h.on_llm_call()
        revised = llm.ask_for_node_revision(hot_node, decision.trigger_input)
        h.leap_done(hot_node.id)
        if revised:
            revised.relations.append(hot_node.id)
            graph.add(revised)
            graph.update_relations(hot_node.id, [revised.id])
            hot_node.status = "deprecated"
            hot_node.confidence *= 0.3
            resp = revised.response or f"[修正: {revised.rdl_type}]"
            return resp, revised.id
        else:
            hot_node.status = "quarantined"
            hot_node.confidence *= 0.5
            print("  [ノード修正に失敗 → 隔離しました]")
            return None, None
    else:
        hot_node.status = "quarantined"
        hot_node.confidence *= 0.5
        h.leap_done(hot_node.id)
        print("  [LLM off — 修正できないためノードを隔離しました]")
        return None, None


def _learn_new_node(user_input: str, graph: NodeGraph, h: HState, llm: LLMBridge,
                    xi_pool: list[str], reason: str) -> Optional[tuple[str, str]]:
    """
    未知入力をLLMでノード化する。成功なら (応答, ノードID)、
    ノード化できなければξプールへ退避して生応答を返す。
    どちらも駄目なら None（呼び出し側でグラフ内合成へ）。
    """
    if not (llm.mode in ("on", "on-once") and llm.available()):
        return None

    h.on_llm_call()
    new_node = llm.ask_for_node(user_input)
    if new_node:
        graph.add(new_node)
        graph.save()
        return new_node.response or f"[新規学習({reason}): {new_node.rdl_type}]", new_node.id

    # ノード化できなかった入力はξプールへ（後のM_Δ相で再評価される）
    xi_pool.append(user_input)
    print("  [LLMノード化失敗 → ξプールに格納しました]")
    h.on_llm_call()
    raw = llm.ask(user_input)
    if raw:
        return raw, "__llm__"
    return None


def _infer_domain(graph: NodeGraph, user_input: str, nearest: Optional[Node]) -> str:
    """
    入力のドメイン(spatial_tag)を推定する。単一の最近傍ノードだけに
    頼ると、たまたま登録順が早い・たまたま類似度計算がぶれたノードに
    引っ張られやすいため、上位k件の類似度加重投票で決める。
    """
    top = graph.top_k_similar(user_input, k=3)
    if not top:
        return nearest.spatial_tag if nearest else "概念"
    votes: dict[str, float] = {}
    for node, sim in top:
        votes[node.spatial_tag] = votes.get(node.spatial_tag, 0.0) + sim
    return max(votes, key=lambda tag: votes[tag])


def respond(user_input: str, graph: NodeGraph, h: HState, llm: LLMBridge, sfo_profile: AI_SFO, xi_pool: list[str], llm_trust: LLMTrust) -> tuple[str, str]:
    """
    応答を生成して返す。
    返り値: (response_text, last_node_id)

    以前はexact/partial一致経路ではleap判定そのものが行われず、
    否定され続けているノードが永久に固定されていた。
    match_typeによらず毎回should_leap()を確認し、H閾値を超えた
    ノード（hot_nid）を実際に修正対象にする。

    また、H閾値超過を待つ一様なゲートは「幼少期にも自力解決を
    要求しすぎる」ため、ドメイン（spatial_tag）ごとのLLM信用度が
    高い（＝そのドメインの内部経験がまだ薄い）場合は、H閾値未達でも
    確率的にLLMへ相談する（下のllm_trustブロック）。経験が育った
    ドメインでは信用度が下がり、この早期相談は自然に起きなくなる。
    """
    # 検索する前に「この入力を捉えられる」という予測を確定させておく（Δの始点）。
    # 予測を先に固定しないと E = |observed − predicted| が計算できない。
    h.predict_match()
    node, match_type, nearest = graph.search(user_input)

    # ξ圧は跳躍境界を揺らし(θ_eff)、整合側の更新量にも効く。1ターン1回だけ評価する。
    pressure = xi_pressure(xi_pool)

    # 実測（Δの終点）: 捉えられたか。E_match が H_pre の増分になる。
    e_match = h.observe_match(MATCH_OBSERVATION[match_type])

    if match_type == "exact":
        h.on_exact(node.id, e_match)
        node.touch()
        node.increment_usage() # M_lat -> M_act 昇格判定
        _reinforce_along_v_b(node, h, pressure, dynamics.CONFIG.align_rate_exact)
    elif match_type == "partial":
        h.on_partial(node.id, e_match)
        node.touch()
        node.increment_usage() # M_lat -> M_act 昇格判定
        _reinforce_along_v_b(node, h, pressure, dynamics.CONFIG.align_rate_partial)

        # 内部応答とLLM信用度の裁定：低confidenceの部分一致は、
        # そのドメインの信用度が上回っているならLLMに譲ったほうがよい
        # （内部確信が薄いのに無理に内部応答へ寄せない）。
        # 差が大きいほど確率的に発火させ、単発の逆転で毎回ぶれないようにする。
        if llm.mode in ("on", "on-once") and llm.available():
            trust = llm_trust.trust_for(graph, node.spatial_tag)
            margin = trust - node.confidence
            if margin > 0 and random.random() < margin:
                print(f"  [部分一致confidence={node.confidence:.2f} < ドメイン『{node.spatial_tag}』信用度{trust:.2f} → LLMへ裁定]")
                h.on_llm_call()
                new_node = llm.ask_for_node(user_input)
                if new_node:
                    graph.add(new_node)
                    graph.save()
                    resp = new_node.response or f"[新規学習(裁定): {new_node.rdl_type}]"
                    return resp, new_node.id
                # LLM失敗時は通常の部分一致応答へフォールスルー
    else:
        # ミス：十分に似たノードが無ければ PENDING_MISS_ID 側へ積む。
        # 無関係なノードに積むと、そのノードが後で誤って修正・隔離される。
        context_nid = nearest.id if nearest else None
        h.on_miss(context_nid, e_match)

    # --- 構造の再編成(leap)は、今回の応答生成とは独立に処理する ---
    # Hが溜まっている場所（target）と、今回の入力（trigger）は別物なので、
    # 背景ノードの修正結果を今回の応答として返さない。
    decision = _decide_leap(h, graph, match_type, node, user_input, pressure)
    leap_response: Optional[tuple[str, str]] = None

    if decision is not None:
        if decision.scope == "phantom":
            # 実体の無いID（__llm__ / __crisis__、M_Δ相で退場したノード）に
            # Hが溜まった状態。修正対象が無いのでleapで消化できず、放置すると
            # 毎ターン should_leap() の最大値を占め続けて実ノードのleapを妨げる。
            h.forget(decision.target_node_id)

        elif decision.scope == "unresolved":
            # 未解決入力の蓄積が閾値超過。今回もmissなら新規学習で消化する。
            if match_type == "miss":
                print(f"  [未解決入力のH閾値超過 (θ={h.theta:.2f})]")
                learned = _learn_new_node(user_input, graph, h, llm, xi_pool, reason="未解決H")
                if learned is not None:
                    h.resolve_miss(context_nid)
                    leap_response = learned
            # LLMの成否や今回の一致有無によらず、必ず減衰させる。
            # ここで減衰させないと、この蓄積が毎ターン should_leap() の
            # 最大値を占め続け、実ノードのleapを永久に妨げてしまう
            # （疑似IDで起きていたのと同じ停止）。
            h.leap_done(decision.target_node_id)

        else:
            hot_node = graph.get_by_id(decision.target_node_id)
            correction_resp, correction_id = _correct_node(hot_node, decision, graph, h, llm)
            graph.save()
            # 応答として使えるのは、今回の入力自身が熱かった場合のみ。
            # background の修正版は今回の入力への答えではない。
            if decision.scope == "current" and correction_resp is not None:
                leap_response = (correction_resp, correction_id)

    if leap_response is not None:
        return leap_response

    # --- ここから先は「今回の入力への応答」 ---

    if match_type == "miss" and llm.mode in ("on", "on-once") and llm.available():
        # このドメインはまだ内部経験が薄いかもしれない。信用度が高いほど
        # 確率的にLLMへ相談する（＝幼少期は外部LLMを養育者・外部足場として使う）。
        # ドメインは単一の最近傍ではなく上位k件の投票で推定する。
        domain = _infer_domain(graph, user_input, nearest)
        trust = llm_trust.trust_for(graph, domain)
        if random.random() < trust:
            print(f"  [ドメイン『{domain}』は内部経験が薄い (信用度={trust:.2f}) → LLMへ相談]")
            learned = _learn_new_node(user_input, graph, h, llm, xi_pool, reason="早期相談")
            if learned is not None:
                # このmissは解決されたので、対応するH_preを軽減する。
                h.resolve_miss(context_nid)
                return learned

    if match_type == "exact" and node.status not in ("quarantined", "deprecated"):
        graph.save()
        _warn_if_self_correction_is_lost(node)
        resp = node.response or f"[{node.rdl_type}] {user_input}"
        return resp, node.id

    if match_type == "partial" and node.status not in ("quarantined", "deprecated"):
        graph.save()
        _warn_if_self_correction_is_lost(node)
        resp = node.response or f"[{node.rdl_type}（部分一致）] {user_input}"
        return resp, node.id

    # miss、または自ノードが隔離されて代替が出せなかった場合のフォールバック
    # 危機モード判定 (設計書 v0.3 §3.4)
    hot = h.hot_nodes(top=1)
    if sfo_profile.check_crisis_mode(hot[0][1] if hot else 0.0, h.theta):
        print("  [危機モード発動] SFOプロファイルに基づき応答傾向を調整します。")
        # 危機モードでの応答ロジックをここに実装
        # 例: より安全な、ユーザーの言葉をなぞる応答に切り替えるなど
        return f"[危機モード] {sfo_profile.crisis_mode_ops['応答傾向']}ます。", "__crisis__"

    return compose_from_graph(user_input, graph)


def load_seed_json(graph: NodeGraph, path: str = "data/seed_v0.1.json") -> int:
    """
    グラフが空のとき同梱の普遍 seed JSON を読み込む。追加数を返す。

    以前は source="manual" / confidence=0.9 で入れていた。設計書 §3.7 は
    seedを「仮置きの足場であり、ユーザー由来ノードに置換される」ものと
    定めているが、manual は内部経験の重みが最大(0.8)なので、seedを
    読み込んだだけで人=0.07 / 概念=0.08 / 身体=0.11 と、起動直後から
    外部LLMをほぼ信用しないAIになっていた（設計書 Phase A の
    「LLM 70% / グラフ30%」とは逆）。

    出自を bootstrap_seed に分け、内部経験の重みを llm_seed 並みに
    抑えることで、ユーザーとの相互作用（approval_count）で初めて
    内部経験へ変換されるようにする。
    """
    try:
        with open(path, encoding="utf-8") as f:
            items = json.load(f)
        for d in items:
            graph.add(Node(
                inputs=d.get("inputs", []),
                rdl_type=d.get("rdl_type", "未分類"),
                spatial_tag=d.get("spatial_tag", "概念"),
                response=d.get("response"),
                source="bootstrap_seed",
                confidence=0.5,
            ))
        graph.save()
        return len(items)
    except FileNotFoundError:
        return 0


def phase0_seed(graph: NodeGraph, llm: LLMBridge):
    """Phase 0: LLMで普遍ノードを種まきする。"""
    if not llm.available():
        print("  LLMが利用不可 (ANTHROPIC_API_KEY未設定) — seedをスキップします")
        return

    print("  Phase 0: LLMで初期ノードを生成中...")
    nodes = llm.seed_universal_nodes()
    for n in nodes:
        graph.add(n)
    graph.save()
    print(f"  {len(nodes)} 個の seed ノードを追加しました。")


def save_session_state(path: str, h: HState, sfo_profile: AI_SFO, xi_pool: list[str], llm_mode: str, turn_count: int):
    """
    H・SFO・ξプール・LLMモード・ターン数を永続化する。
    以前はgraph.jsonしか保存されず、再起動のたびにユーザーとの
    齟齬や適応過程（H, drift, ξプール）が初期化されていた。
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = {
        "h_state": h.to_dict(),
        "sfo_profile": sfo_profile.to_dict(),
        "xi_pool": xi_pool,
        "llm_mode": llm_mode,
        "turn_count": turn_count,
    }
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def load_session_state(path: str) -> Optional[dict]:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
        print(f"  [ERROR] セッション状態のJSONが壊れています ({path})。初期状態から始めます。")
        return None


def main():
    global _turn_count
    seed_mode = "--seed" in sys.argv

    graph = NodeGraph("data/graph.json")

    state = load_session_state(SESSION_STATE_PATH)
    if state:
        h = HState.from_dict(state.get("h_state", {}))
        sfo_data = state.get("sfo_profile")
        sfo_profile = AI_SFO.from_dict(sfo_data) if sfo_data else create_sfo_profile_from_mbti(DEFAULT_SFO_PRESET)
        xi_pool: list[str] = state.get("xi_pool", [])
        saved_llm_mode = state.get("llm_mode")
        _turn_count = state.get("turn_count", 0)
        print(f"  セッション状態を復元しました（turn={_turn_count}, drift={sfo_profile.drift_factor:.2f}）")
    else:
        h = HState(theta=2.0)
        # SFOプロファイルの初期化 (設計書 v0.3 §3.4 MBTI入口プリセット)
        # 以前は AI_SFO(initial_fingerprint="RDL_native_observer") と
        # 指紋の文字列だけを差し替えており、実際の得意操作・苦手操作は
        # dataclassの既定値のままでプリセットと食い違っていた。
        sfo_profile = create_sfo_profile_from_mbti(DEFAULT_SFO_PRESET)
        xi_pool = [] # ξプール (設計書 v0.3 §3.5)
        saved_llm_mode = None
        _turn_count = 0

    llm = LLMBridge(sfo_profile) # SFOプロファイルをLLMBridgeに渡す

    # LLM利用可能なら初期モードを復元（未保存ならon）
    if llm.available():
        llm.set_mode(saved_llm_mode if saved_llm_mode in ("on", "off", "on-once") else "on")

    llm_trust = LLMTrust(load_llm_trust_config(LLM_TRUST_CONFIG_PATH))
    dynamics.configure(load_dynamics_config(DYNAMICS_CONFIG_PATH))

    print(BANNER)

    if seed_mode:
        phase0_seed(graph, llm)

    # グラフが空なら手動 seed を自動ロード
    if graph.stats()["total"] == 0:
        n = load_seed_json(graph)
        if n:
            print(f"  seed_v0.1.json から {n} ノードをロードしました。")

    s = graph.stats()
    print(f"  グラフ読込: {s['total']} ノード  LLM: {llm.mode} ({llm.model})")
    print()

    last_node_id = "__none__"
    last_input = "__none__"

    while True:
        try:
            user_input = input("あなた > ").strip()
        except (EOFError, KeyboardInterrupt):
            graph.save()
            save_session_state(SESSION_STATE_PATH, h, sfo_profile, xi_pool, llm.mode, _turn_count)
            print("\n終了します。")
            break

        if not user_input:
            h.on_silence(last_node_id)
            continue

        if user_input.startswith("/"):
            handle_command(user_input, llm, graph, h, sfo_profile, xi_pool, llm_trust)
            continue

        # フィードバックショートカット（直前応答への反応）
        if user_input in ("y", "n", "?") and last_node_id != "__none__":
            apply_feedback(user_input, last_node_id, last_input, graph, h)
            continue

        try:
            response, last_node_id = respond(user_input, graph, h, llm, sfo_profile, xi_pool, llm_trust)
        except Exception as e:
            # LLM API呼び出しなど外部境界での失敗でループ全体を落とさない。
            print(f"  [ERROR] 応答生成に失敗しました: {e}")
            graph.save()
            continue
        # 応答した時点で「これは受け入れられる」という予測を書き留める（Δの始点）。
        # ユーザー反応が返った時に突き合わせて E_acceptance を出す。
        h.open_decision(last_node_id, _predicted_acceptance(graph, last_node_id))
        last_input = user_input
        print(f"Bot  > {response}")

        # 毎ターン簡易フィードバック
        feedback_prompt(last_node_id, last_input, graph, h)

        # M_Δ相: 代謝（毎ターン減衰、50ターンごとに死滅退場＋保存）
        _turn_count += 1
        retire = (_turn_count % 50 == 0)
        metabolize(graph, sfo_profile, xi_pool, h, retire=retire)
        if retire:
            graph.save()
            save_session_state(SESSION_STATE_PATH, h, sfo_profile, xi_pool, llm.mode, _turn_count)


if __name__ == "__main__":
    main()
