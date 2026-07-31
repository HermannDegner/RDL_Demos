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
  /xipool                     ξプールを表示
  /graph                      グラフ統計を表示
  /hot                        H高いノードを表示
  /quit                       終了
  y / n / ?                   直前の応答へのフィードバック（y=同意 n=否定 ?=言い換え）
"""

import sys
import os
import random

# Windows での文字化け防止
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdin.reconfigure(encoding="utf-8")

# カレントディレクトリを data/ の親に合わせる
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import json
from typing import Optional

from node_graph import NodeGraph, Node
from h_state import HState
from llm_bridge import LLMBridge
from sfo_profile import AI_SFO, create_sfo_profile_from_mbti
from llm_trust import LLMTrust, LLMTrustConfig


BANNER = """
========================================
  sumitsuku-AI  /  RDL Bot  v0.1
  Phase 0->A/B  CLI prototype
========================================
  /llm on|off|once  /h  /sfo  /mbti  /trust  /xipool  /graph  /hot  /quit
  feedback: y(agree) n(deny) ?(rephrase)
"""

SESSION_STATE_PATH = "data/session_state.json"
LLM_TRUST_CONFIG_PATH = "data/llm_trust_config.json"
DOMAIN_TAGS = ["人", "概念", "物語", "制度", "身体"]


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

    if fb == "n":
        h.on_deny(last_node_id)
        if node:
            node.confidence = max(0.05, node.confidence * 0.85)
            node.record_counterexample(last_input, "deny")
            graph.save()
        print("  → 否定を記録しました (H_post +1.0, confidence減衰)")
    elif fb == "?":
        h.on_rephrase(last_node_id)
        if node:
            node.confidence = max(0.05, node.confidence * 0.95)
            node.record_counterexample(last_input, "rephrase")
            graph.save()
        print("  → 言い換えを記録しました (H_post +0.3, confidence減衰)")
    elif fb == "y":
        h.on_agree(last_node_id)
        if node:
            node.confidence = min(1.0, node.confidence * 1.05)
            node.approval_count += 1
            node.touch()
            graph.save()
        print("  → 同意を記録しました (H_post x0.7, confidence微増, approval_count+1)")
    # 空Enterは H を上げない


def feedback_prompt(last_node_id: str, last_input: str, graph: NodeGraph, h: HState) -> None:
    """応答後のフィードバックを求める。"""
    fb = input("  [fb] > ")
    apply_feedback(fb, last_node_id, last_input, graph, h)


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
        print(f"  {h.summary()}")

    elif name == "/sfo":
        print(f"  AI_SFOプロファイル: {sfo_profile.to_dict()}")

    elif name == "/mbti":
        if len(parts) < 2:
            print("  MBTIタイプを指定してください (例: /mbti INTP)")
        else:
            mbti_type = parts[1].upper()
            new_sfo = create_sfo_profile_from_mbti(mbti_type)
            sfo_profile.main_foreground_space = new_sfo.main_foreground_space
            sfo_profile.hierarchy_bias = new_sfo.hierarchy_bias
            sfo_profile.得意操作 = new_sfo.得意操作
            sfo_profile.苦手操作 = new_sfo.苦手操作
            sfo_profile.attention_mode = new_sfo.attention_mode
            sfo_profile.initial_fingerprint = new_sfo.initial_fingerprint
            sfo_profile.drift_factor = 0.0 # MBTI変更でドリフトをリセット
            print(f"  SFOプロファイルを {mbti_type} に基づいて初期化しました。")

    elif name == "/trust":
        print(f"  LLM信用度設定: {llm_trust.config.to_dict()}")
        for tag, trust in llm_trust.trust_by_domain(graph, DOMAIN_TAGS).items():
            exp = llm_trust.internal_experience(graph, tag)
            print(f"    {tag}: trust={trust:.2f}  internal_experience={exp:.2f}")

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

    # 1. 低confidence・低使用頻度ノードのTTL減算と削除
    for n in list(graph.nodes.values()):
        n.decay_confidence()
        # llm_seed ノードの retirement 判定 (設計書 v0.3 §3.7 Seedの取り扱い原則)
        # ユーザー由来ノードに置換されきった llm_seed は削除候補
        if n.source == "llm_seed" and n.confidence < 0.3 and n.usage_count == 0:
            n.ttl = 0 # 即時削除対象とする

    if retire:
        graph.retire_dead_nodes()

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


def _correct_node(hot_node: Node, user_input: str, graph: NodeGraph, h: HState, llm: LLMBridge) -> tuple[Optional[str], Optional[str]]:
    """
    否定・言い換えのHが閾値を超えて蓄積した既存ノード(hot_node)を修正する。
    LLM on: LLMに既存の誤答・否定履歴を渡して代替ノードを生成し、
            hot_nodeはdeprecated化してrelationsで新ノードにつなぐ。
    LLM off: 代替を生成できないので、hot_nodeをquarantine化するだけに留める
             （このノードはsearch()/compose_from_graph()の対象から外れる）。
    """
    print(f"  [H閾値超過 → 既存ノードを再評価: {hot_node.rdl_type}]")

    if llm.mode in ("on", "on-once") and llm.available():
        h.on_llm_call()
        revised = llm.ask_for_node_revision(hot_node, user_input)
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
    node, match_type, nearest = graph.search(user_input)

    if match_type == "exact":
        h.on_exact(node.id)
        node.touch()
        node.increment_usage() # M_lat -> M_act 昇格判定
    elif match_type == "partial":
        h.on_partial(node.id)
        node.touch()
        node.increment_usage() # M_lat -> M_act 昇格判定

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
        # ミス：最近傍ノードIDをコンテキストとして渡す
        context_nid = nearest.id if nearest else "__none__"
        h.on_miss(context_nid)

    leap_needed, hot_nid = h.should_leap()

    if leap_needed:
        hot_node = graph.get_by_id(hot_nid)

        if hot_node is not None:
            # H閾値を超えたノードが実在する → 学習対象と修正対象を一致させる
            correction_resp, correction_id = _correct_node(hot_node, user_input, graph, h, llm)
            graph.save()

            if match_type in ("exact", "partial") and node.id == hot_node.id and correction_resp is not None:
                return correction_resp, correction_id
            if match_type == "miss" and correction_resp is not None:
                return correction_resp, correction_id
            # ここに来るのは、
            #  (a) hot_nodeが今回の一致ノードと同じだが修正に失敗し隔離のみだった場合
            #  (b) hot_nodeが今回の入力とは別ノードで、背景で修正だけ適用した場合
            # (a)は下のexact/partial応答チェックでstatus判定により弾かれ、
            #     結局フォールバックへ進む。(b)は今回の入力に通常通り応答する。

        elif match_type == "miss" and llm.mode in ("on", "on-once"):
            print("  [H閾値超過 → LLMに問い合わせ中...]")
            h.on_llm_call() # LLM呼び出しを記録
            new_node = llm.ask_for_node(user_input)
            if new_node:
                graph.add(new_node)
                graph.save()
                h.leap_done(hot_nid)
                h.resolve_miss(context_nid)
                resp = new_node.response or f"[新規学習: {new_node.rdl_type}]"
                return resp, new_node.id
            else:
                # LLM失敗 → ξプールに格納し、テキスト応答にフォールバック
                xi_pool.append(user_input) # LLMがノード化できなかった入力をξプールへ
                print("  [LLMノード化失敗 → ξプールに格納しました]")
                h.on_llm_call() # LLM呼び出しを記録
                raw = llm.ask(user_input)
                if raw:
                    return raw, "__llm__"
                else:
                    return "[LLM応答も失敗しました。ξプールに格納済み]", "__none__"

        elif match_type == "miss":
            print(f"  [H閾値超過 (θ={h.theta:.2f}) — グラフ内合成を試みます]")

    elif match_type == "miss" and llm.mode in ("on", "on-once") and llm.available():
        # H閾値には未達だが、このドメインはまだ内部経験が薄いかもしれない。
        # 信用度が高いほど、閾値を待たずに確率的にLLMへ相談する
        # （＝幼少期は外部LLMを養育者・外部足場として使う）。
        # ドメインは単一の最近傍ではなく上位k件の投票で推定する。
        domain = _infer_domain(graph, user_input, nearest)
        trust = llm_trust.trust_for(graph, domain)
        if random.random() < trust:
            print(f"  [ドメイン『{domain}』は内部経験が薄い (信用度={trust:.2f}) → H閾値を待たずLLMへ相談]")
            h.on_llm_call()
            new_node = llm.ask_for_node(user_input)
            if new_node:
                graph.add(new_node)
                graph.save()
                # このmissは解決されたので、たまたま近くにいた既存ノードに
                # 積み上がったH_preを軽減する（無関係なノードが後で誤って
                # 修正対象に選ばれるのを防ぐ）。
                h.resolve_miss(context_nid)
                resp = new_node.response or f"[新規学習(早期相談): {new_node.rdl_type}]"
                return resp, new_node.id
            else:
                xi_pool.append(user_input)
                print("  [LLMノード化失敗 → ξプールに格納しました]")
                h.on_llm_call()
                raw = llm.ask(user_input)
                if raw:
                    return raw, "__llm__"

    if match_type == "exact" and node.status not in ("quarantined", "deprecated"):
        graph.save()
        resp = node.response or f"[{node.rdl_type}] {user_input}"
        return resp, node.id

    if match_type == "partial" and node.status not in ("quarantined", "deprecated"):
        graph.save()
        resp = node.response or f"[{node.rdl_type}（部分一致）] {user_input}"
        return resp, node.id

    # miss、または自ノードが隔離されて代替が出せなかった場合のフォールバック
    # 危機モード判定 (設計書 v0.3 §3.4)
    if sfo_profile.check_crisis_mode(h.hot_nodes(top=1)[0][1] if h.hot_nodes() else 0, h.theta):
        print("  [危機モード発動] SFOプロファイルに基づき応答傾向を調整します。")
        # 危機モードでの応答ロジックをここに実装
        # 例: より安全な、ユーザーの言葉をなぞる応答に切り替えるなど
        return f"[危機モード] {sfo_profile.crisis_mode_ops['応答傾向']}ます。", "__crisis__"

    return compose_from_graph(user_input, graph)


def load_seed_json(graph: NodeGraph, path: str = "data/seed_v0.1.json") -> int:
    """グラフが空のとき手動 seed JSON を読み込む。追加数を返す。"""
    try:
        with open(path, encoding="utf-8") as f:
            items = json.load(f)
        for d in items:
            graph.add(Node(
                inputs=d.get("inputs", []),
                rdl_type=d.get("rdl_type", "未分類"),
                spatial_tag=d.get("spatial_tag", "概念"),
                response=d.get("response"),
                source="manual",
                confidence=0.9,
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
        sfo_profile = AI_SFO.from_dict(sfo_data) if sfo_data else AI_SFO(initial_fingerprint="RDL_native_observer")
        xi_pool: list[str] = state.get("xi_pool", [])
        saved_llm_mode = state.get("llm_mode")
        _turn_count = state.get("turn_count", 0)
        print(f"  セッション状態を復元しました（turn={_turn_count}, drift={sfo_profile.drift_factor:.2f}）")
    else:
        h = HState(theta=2.0)
        # SFOプロファイルの初期化 (設計書 v0.3 §3.4 MBTI入口プリセット)
        # 現時点ではRDL_native_observerをデフォルトとする。ユーザー入力で変更可能にする予定。
        sfo_profile = AI_SFO(initial_fingerprint="RDL_native_observer")
        xi_pool = [] # ξプール (設計書 v0.3 §3.5)
        saved_llm_mode = None
        _turn_count = 0

    llm = LLMBridge(sfo_profile) # SFOプロファイルをLLMBridgeに渡す

    # LLM利用可能なら初期モードを復元（未保存ならon）
    if llm.available():
        llm.set_mode(saved_llm_mode if saved_llm_mode in ("on", "off", "on-once") else "on")

    llm_trust = LLMTrust(load_llm_trust_config(LLM_TRUST_CONFIG_PATH))

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
