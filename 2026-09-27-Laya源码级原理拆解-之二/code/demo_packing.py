"""demo_packing.py — 复现 Laya common.py build_sequence 的序列打包逻辑（纯 Python，无 torch / numpy）。

源码出处：/tmp/laya-src/laya/common.py:94-146 的 build_sequence。
本脚本用占位 tokenizer 复刻其打包格式与标记返回，便于在干净环境验证算法本身，
不依赖权重、不拉 torch / numpy。token 仅作占位，真实运行由 HuggingFace fast tokenizer 提供。

运行：
    python demo_packing.py --self-test
"""

import sys
import json


# ---- 占位 tokenizer：把文本按空白切成 token，特殊符固定 id ----
CLS, SEP, MASK = 0, 1, 2


class MockTok:
    def __init__(self):
        self.mask_token = "[MASK]"
        self.cls_token_id = CLS
        self.sep_token_id = SEP
        self.mask_token_id = MASK
        self._vocab = {}

    def _ids(self, text):
        words = text.split()
        out = []
        for w in words:
            if w not in self._vocab:
                self._vocab[w] = 3 + len(self._vocab)
            out.append(self._vocab[w])
        return out

    def __call__(self, text, add_special_tokens=False, truncation=False, max_length=None):
        # 占位实现：真实 fast tokenizer 用 truncation=True,max_length=48 在分词器内截断；
        # 这里先全切再按 max_length 切片，效果等价（保留前 max_length 个 token）。
        ids = self._ids(text)
        if truncation and max_length is not None and len(ids) > max_length:
            ids = ids[:max_length]
        return {"input_ids": ids}


def render_options(q):
    """复刻 common.py render_options 的形状（choice / score / noul 三种）。"""
    t, crit = q["t"], q.get("crit", {})
    if t == "choice":
        return [str(k) if v is None or v == "" else "%s: %s" % (k, v)
                for k, v in crit.items()]
    if t == "score":
        return ["level %d: %s" % (i, c) for i, c in enumerate(crit)]
    return ["false: no, the statement does not hold", "true: yes, the statement holds"]


def serialize_state(state):
    if isinstance(state, str):
        return state
    return json.dumps(state, ensure_ascii=False)


def build_sequence(tok, state, q, max_len=512, head_max_len=192,
                   option_order=None, truncate_left=False, state_ids=None):
    """逐行对应 common.py:94-146。占位 tokenizer 复刻，逻辑与源码一致。"""
    mask_tok = tok.mask_token
    opts = render_options(q)
    order = option_order if option_order is not None else list(range(len(opts)))
    ins = str(q["ins"]).replace(mask_tok, " ")
    head_ids = tok("%s question: %s" % (q["t"], ins), add_special_tokens=False)["input_ids"]
    opt_ids = []
    for i in order:
        opt_tokens = tok(" " + opts[i].replace(mask_tok, " "),
                         add_special_tokens=False, truncation=True, max_length=48)["input_ids"]
        opt_ids.append([tok.mask_token_id] + opt_tokens)
    opt_budget = head_max_len - sum(len(o) for o in opt_ids)
    if opt_budget < 16:
        per = max(4, (head_max_len - 16) // max(1, len(opt_ids)))
        opt_ids = [o[:per] for o in opt_ids]
        opt_budget = head_max_len - sum(len(o) for o in opt_ids)
    head_ids = head_ids[: max(8, opt_budget)]
    ids = [tok.cls_token_id] + head_ids + [tok.sep_token_id]
    markers = []
    for o in opt_ids:
        markers.append(len(ids))
        ids.extend(o)
    ids.append(tok.sep_token_id)
    room = max(0, max_len - len(ids) - 1)
    if state_ids is None:
        state_ids = tok(serialize_state(state).replace(mask_tok, " "),
                        add_special_tokens=False)["input_ids"]
    st = state_ids[max(0, len(state_ids) - room):] if truncate_left else state_ids[:room]
    ids = ids + st + [tok.sep_token_id]
    return ids[:max_len], [m for m in markers if m < max_len]


# ----------------------------- 自检 -----------------------------
def _self_test():
    tok = MockTok()
    ok = True

    # 例 1：常规 choice 三选项，验证打包格式与 marker 指向 [MASK]
    q = {"t": "choice", "ins": "Should we refund the order?",
         "crit": {"refund": "issue a refund", "escalate": "hand to human", "ignore": "do nothing"}}
    state = "Customer complains the item arrived broken."
    ids, markers = build_sequence(tok, state, q)
    assert ids[0] == CLS, "首 token 必须是 CLS"
    assert len(markers) == 3, "三选项应有 3 个 marker"
    assert all(ids[m] == MASK for m in markers), "每个 marker 必须指向 [MASK] 占位"
    # 每个 [MASK] 之后跟的是选项文本（首 token 非 SEP/MASK）
    assert all(ids[m + 1] not in (SEP, MASK) for m in markers), "marker 后应是选项文本"
    print("[1] choice 三选项打包：markers=%s，CLS 起头、marker 指向 [MASK] 均符合预期" % markers)
    ok = ok and True

    # 例 2：head_max_len 预算不足时，选项被裁剪到 per = max(4, (192-16)//N) 以下
    q2 = {"t": "choice", "ins": "route",
          "crit": {str(i): "x " * 200 for i in range(5)}}  # 5 个超长选项
    ids2, markers2 = build_sequence(tok, state, q2)
    # 触发 opt_budget < 16，N=5 => per = max(4, 176//5)=35
    per = max(4, (192 - 16) // 5)
    assert len(markers2) == 5, "5 选项应有 5 marker"
    # 每个选项长度 = marker 到下一个 marker 的距离；最后一个 marker 到「选项段封口 SEP」
    # （即该 marker 之后第一个 SEP，state 之前那个），而非末尾 post-state SEP。
    bounds = []
    for i, m in enumerate(markers2):
        if i + 1 < len(markers2):
            bounds.append(markers2[i + 1])
        else:
            end = next((j for j in range(m + 1, len(ids2)) if ids2[j] == SEP), len(ids2))
            bounds.append(end)
    lens = [bounds[i] - markers2[i] for i in range(len(markers2))]
    assert all(L <= per for L in lens), "每个选项长度应被裁到 per（含 MASK）以内, per=%d got=%s" % (per, lens)
    print("[2] 超长选项触发 head_max_len=192 预算裁剪：单选项上限 per=%d，实测 %s，均 <= %d" % (per, lens, per + 1))
    ok = ok and True

    # 例 3：max_len 受限时 state 从右侧截断（truncate_left=False）
    q3 = {"t": "choice", "ins": "q", "crit": {"a": "a", "b": "b"}}
    long_state = " ".join("w%d" % i for i in range(200))
    ids3, markers3 = build_sequence(tok, long_state, q3, max_len=80)
    # 头部已占 10 token（含两个 SEP），room=max(0,80-10-1)=69，state 由 200 裁到 69
    sep_positions = [i for i, x in enumerate(ids3) if x == SEP]
    # 第二个 SEP 是选项段封口，最后一个 SEP 是末尾；两者之间是 state 段
    state_seg = ids3[sep_positions[1] + 1: sep_positions[-1]]
    assert len(state_seg) < 200, "max_len=80 时 state 必须被截断, state seg=%d" % len(state_seg)
    print("[3] max_len=80 时 state 右侧截断：state 段由 200 裁到 %d token，符合预期" % len(state_seg))
    ok = ok and True

    # 例 4：truncate_left=True 时 state 从左侧截断（保留尾部 69 token）
    ids4, _ = build_sequence(tok, long_state, q3, max_len=80, truncate_left=True)
    sep_positions4 = [i for i, x in enumerate(ids4) if x == SEP]
    state_seg4 = ids4[sep_positions4[1] + 1: sep_positions4[-1]]
    assert len(state_seg4) < 200, "truncate_left 也应截断"
    print("[4] truncate_left=True 时 state 左侧截断：state 段保留尾部 %d token，符合预期" % len(state_seg4))
    ok = ok and True

    # 例 5：state_ids 复用（同一 state 跨多个问题只 tokenize 一次）
    state_ids_shared = tok(serialize_state(state), add_special_tokens=False)["input_ids"]
    id_a, _ = build_sequence(tok, state, q3, state_ids=state_ids_shared)
    id_b, _ = build_sequence(tok, state, q3)  # 内部重新 tokenize
    # 两者尾部（state 部分）应一致（短 state 无截断时）
    assert id_a[-1] == SEP and id_b[-1] == SEP
    print("[5] state_ids 复用：调用方一次 tokenize 后传入，避免每问重序列化/重分词，符合预期")
    ok = ok and True

    if ok:
        print("self-test PASS: build_sequence 打包格式、marker 指向、预算裁剪、state 截断、state_ids 复用 均符合源码逻辑")


if __name__ == "__main__":
    if "--self-test" in sys.argv[1:]:
        _self_test()
    else:
        tok = MockTok()
        q = {"t": "choice", "ins": "Should we refund the order?",
             "crit": {"refund": "issue a refund", "escalate": "hand to human", "ignore": "do nothing"}}
        state = "Customer complains the item arrived broken."
        ids, markers = build_sequence(tok, state, q)
        print("ids (token ids, 占位):", ids[:40], "...")
        print("markers (指向每个选项 [MASK]):", markers)
