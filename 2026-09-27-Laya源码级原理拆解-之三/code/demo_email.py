#!/usr/bin/env python3
"""demo_email.py — 复刻 laya/email.py 的「邮件正文清洗」管线。

正则与函数逐行对齐源码（覆盖英/葡/西三语客户端）。纯标准库，无外部依赖。
运行 `python demo_email.py --self-test` 自检全绿，标准输出即正文引用的「预期输出」。

一手来源：/tmp/laya-src/laya/email.py（MIT，NandhaKishorM/laya）。
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

_QUOTE_HEADERS = [
    re.compile(r"^\s*On .{0,300}wrote:\s*$", re.I),
    re.compile(r"^\s*Em (?=.*\d).{0,300}escreveu:\s*$", re.I),
    re.compile(r"^\s*El (?=.*\d).{0,300}escribi[óo]:\s*$", re.I),
    re.compile(r"^\s*-{2,}\s*(Original|Forwarded) Message\s*-{2,}", re.I),
    re.compile(r"^\s*-{2,}\s*(Mensagem (original|encaminhada)|Mensaje (original|reenviado))\s*-{2,}", re.I),
    re.compile(r"^\s*_{8,}\s*$"),
    re.compile(r"^\s*From:\s.*[@<]", re.I),
    re.compile(r"^\s*De:\s.*[@<]", re.I),
]
_ATTRIBUTION_TAIL = re.compile(r"^.{0,120}\S@\S+\s+(wrote|escreveu|escribi[óo]):\s*$", re.I)
_ATTRIBUTION_HEAD = re.compile(r"^\s*(On|Em|El) (?=.*\d)", re.I)
_HEADER_FROM_NAME = re.compile(r"^\s*(De|From):\s+\S", re.I)
_HEADER_NEXT = re.compile(r"^\s*(Enviad[oa]( em| el)?:\s|Sent:\s|(Data|Fecha|Date):\s.*\d{4})", re.I)
_SIGNATURE_MARKERS = [
    re.compile(r"^\s*--\s*$"),
    re.compile(
        r"^\s*(?i:best|kind|warmest|warm|many thanks|thanks|thank you|regards|cheers|sincerely)"
        r"(?i:\s+(?:and|&)\s+regards|\s+(?:regards|wishes|again|in advance|a lot|so much|very much))?"
        r"[\s,;:!.]*(?:[^\W\d_a-zß-öø-ÿ][\w'-]*[\s,.]*){0,3}$"
    ),
    re.compile(r"^\s*sent from my (iphone|android|mobile|ipad)", re.I),
    re.compile(
        r"^\s*(atenciosamente|att|abraços?|abs|um abraço|cordialmente|grat[oa]|(muito )?obrigad[oa]s?"
        r"( desde já| pela atenção)?|(com os melhores )?cumprimentos|saudações|"
        r"(un )?saludos?( cordiales)?|atentamente|(muchas )?gracias( de antemano)?)[\s,!.]*$",
        re.I,
    ),
]
_DEVICE = (r"iphone|ipad|android|ios|celular|telemóvel|móvil|galaxy|smartphone|samsung|tablet|"
           r"outlook|yahoo|mail|e-?mail|gmail|windows")
_DEVICE_FOOTER = re.compile(
    r"^\s*((enviad[oa] (do|pelo|pela|via|desde|a partir do)( meu| minha| mi)?|sent from( my)?)"
    r" (%s)( (%s|para|for|no|na|\d+))*|(obter o|get) outlook (para|for) (ios|android))[\s.!]*$"
    % (_DEVICE, _DEVICE),
    re.I,
)
_DISCLAIMER = re.compile(
    r"(\b(e-?mail|message|information|communication|transmission|contents?)\b[^.]{0,60}"
    r"\bconfidential\b[^.]{0,60}\b(intended|solely|addressee|recipient|privileged|"
    r"disclos|unauthori[sz]ed)|"
    r"\bconfidential\b[^.]{0,60}\b(and (may|is) (also )?privileged)|"
    r"if you (have )?received this (e-?mail|message) in error|"
    r"\b(esta|este) (mensagem|e-?mail|mensaje|correo)\b[^.]{0,80}(confidencia|sigilos|privilegiad)|"
    r"\b(uso exclusivo|exclusivamente|únicamente|unicamente)\b[^.]{0,30}"
    r"(destinatári|destinatari|pessoa|persona|entidade|entidad)|"
    r"\b(recebeu|recebido|receber) (esta|este) (mensagem|e-?mail)\b[^.]{0,20} por (engano|erro)|"
    r"\b(ha recibido|recibió|recibe) (este|esta) (mensaje|correo)\b[^.]{0,20} por error|"
    r"\bantes de imprimir\b[^.]{0,100}(meio ambiente|medio ambiente|natureza|planeta|realmente necess)|"
    r"\b(meio|medio) ambiente\b[^.]{0,30}antes de imprimir)",
    re.I,
)
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def _starts_new_sentence(line: str) -> bool:
    for ch in line:
        if ch.isalpha():
            return ch.isupper()
    return False


def _split_fused_lines(sentence: str) -> List[str]:
    if "\n" not in sentence:
        return [sentence]
    pieces, buf = [], ""
    for line in (ln.strip() for ln in sentence.split("\n")):
        if not line:
            continue
        if buf and _starts_new_sentence(line):
            pieces.append(buf)
            buf = line
        else:
            buf = (buf + " " + line) if buf else line
    if buf:
        pieces.append(buf)
    return pieces


def _strip_disclaimer(paragraph: str) -> str:
    if not _DISCLAIMER.search(paragraph):
        return paragraph
    parts = [p.strip() for p in _SENTENCE.split(paragraph) if p.strip()]
    pieces = []
    for p in parts:
        pieces.extend(_split_fused_lines(p) if _DISCLAIMER.search(p) else [p])
    return " ".join(p for p in pieces if not _DISCLAIMER.search(p))


def clean_email_body(body: str, max_chars: int = 3000) -> str:
    text = (body or "").replace("\r\n", "\n").replace("\r", "\n").replace("\\n", "\n")
    if len(text) > max_chars * 4:
        text = text[:max_chars * 4]
    lines = []
    src = text.split("\n")
    for i, line in enumerate(src):
        if any(p.match(line) for p in _QUOTE_HEADERS) and lines:
            break
        if (lines and _HEADER_FROM_NAME.match(line) and i + 1 < len(src)
                and _HEADER_NEXT.match(src[i + 1])):
            break
        if _ATTRIBUTION_TAIL.match(line) and lines:
            if _ATTRIBUTION_HEAD.match(lines[-1]):
                lines.pop()
            break
        if line.lstrip().startswith(">"):
            continue
        lines.append(line.rstrip())
    cut = len(lines)
    for i in range(max(1, min(int(len(lines) * 0.6), len(lines) - 8)), len(lines)):
        n = len(lines[i].strip())
        if (n <= 40 and any(p.match(lines[i]) for p in _SIGNATURE_MARKERS)) or (
                n <= 60 and _DEVICE_FOOTER.match(lines[i])):
            cut = i
            break
    lines = lines[:cut]
    paragraphs = [_strip_disclaimer(p) for p in re.split(r"\n\s*\n", "\n".join(lines))]
    text = re.sub(r"[ \t]+", " ", "\n\n".join(p.strip() for p in paragraphs if p.strip()))
    return text[:max_chars]


def email_state(subject: str, body: str, sender: Optional[str] = None, clean: bool = True, **extra) -> Dict:
    state = {
        "subject": (subject or "").strip(),
        "body": clean_email_body(body) if clean else (body or ""),
    }
    if sender:
        state["from"] = sender
    state.update({k: v for k, v in extra.items() if v is not None})
    return state


# ----------------------------------------------------------------------------
# 一封带引文历史 + 签名 + 免责声明的邮件（英文 + 葡/西客户端规则同源）
# ----------------------------------------------------------------------------
SAMPLE_EMAIL = """Hi team,

I paid for my subscription last week but the refund never arrived on my card.
Please process it, this is blocking my renewal.

The information in this email is confidential and intended solely for the addressee.
If you have received this email in error please notify us immediately.

Thanks,
Alice
alice@acme.com

On Mon, Sep 22, 2025 at 10:00 AM, Bob <bob@acme.com> wrote:
> any update on billing?
"""


def _demo():
    print("=== 原始邮件（节选，含引文/签名/免责声明）===")
    print(SAMPLE_EMAIL)
    print("=== email_state（清洗后）===")
    state = email_state("Refund not received", SAMPLE_EMAIL, sender="alice@acme.com")
    print(repr(state["body"]))
    print()
    print("--- 清洗后正文（可读）---")
    print(state["body"])


def _self_test():
    state = email_state("Refund not received", SAMPLE_EMAIL)
    body = state["body"]
    # 1) 三类噪声都应被剔除
    assert "On Mon" not in body, "引文历史未剔除"
    assert "Thanks," not in body, "签名未剔除"
    assert "confidential" not in body, "免责声明未剔除"
    # 2) 真正的请求必须保留
    assert "paid for my subscription" in body, "请求正文被误删"
    assert "blocking my renewal" in body, "请求正文被误删"
    # 3) 多行请求在清洗后仍连成一段
    assert "Hi team," in body and "Please process it" in body
    print("self-test PASS: 引文/签名/免责声明剔除，真实请求保留")


if __name__ == "__main__":
    import sys
    if "--self-test" in sys.argv:
        _self_test()
    else:
        _demo()
