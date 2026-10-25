"""The ``second_person`` lint's classifier (docs/08-DIRECTOR.md "Validation", billboard rows).

A sentence addressed to the reader is a billboard. The classifier fails closed: where a kind may
use "you" at all, a "you" passes only on a positive anchor, and every other one fails. A false
fail costs the generator one retry; a false pass ships a billboard, so the ambiguous case fails.
Curly apostrophes read as straight ones. The checks, in order:

1. Reader address, on the whole text (quoted speech and ``>`` lines included): a ``_READER``
   family ("if this reaches you", "you were a person.", "whoever you", "one of us"), or a
   personhood claim in a sentence that holds "you". These are an extra fail path; nothing else
   depends on them.
2. Quoted speech and ``>`` lines (``_QUOTED``; a single quote opens only after a space, a line
   start or an opening bracket, and never before a contraction such as "'em"): a span fails when
   it holds a second-person predicate (``_SPAN_PREDICATE``: "you are/were/'re/aren't/weren't/was",
   "you really/actually/still/never/once", an agent acting on "you" such as "placed you", or
   "your name/memories/family/real/life/past/body").
3. Sign-offs (``_is_closing``) are spared everywhere: the last sentence of a paragraph (a short
   signature line may follow), at most eight words, ending in a comma or a period, headed by a
   closing word (thanks, thank, cheers, best, wishes, regards, sincerely, yours), with each
   "you" in a closing slot ("thank you", "for your", "to you", "yours"). "See you <time word>"
   ("see you Monday", "see you next week") is spared anywhere; any other "see you" is not.
4. An instructional kind (``family_faq``, ``recovery_guide``): a sentence that pairs "you" with
   a world premise term fails. Every clause that holds "you" (``_CLAUSE`` splits on commas,
   semicolons, colons, brackets, dashes, "and", "but", "or", "so", "because", "then") must match
   a procedural anchor (``_ANCHOR``), and even an anchored clause fails on ``_STRONG`` (an agent
   acting on "you", "you really/actually/never/once", "yourself", "you were <done to>",
   "your name/memories/real/life/past/body"). The anchors:

   - a conditional procedure: "if you need/want/wish/would like/prefer/have (not "have been")/
     lose/miss/arrive/plan/cannot/are unable", "if you are the/a <role>" (``_ROLE``: next of
     kin, named contact, carer, guardian, parent, spouse, partner, relative, visitor, holder,
     applicant, executor, person named/listed/with/responsible);
   - a temporal procedure: "when/before/after/once/while you <procedural verb>/arrive/leave";
   - a modal procedure: "you can/may/should/must/will/'ll/could/might (need to|have to) <verb>",
     its question form ("can you bring"), and "your <noun> may <verb>";
   - an imperative that opens the clause with a procedural verb ("bring your pass", "call us if
     you are worried").

   The procedural verbs (``PROCEDURAL_VERBS``) are concrete and short: call, bring, ask, book,
   visit, contact, request, collect, park, fill, use, send, wait, sign, check, return, keep,
   show, tell, email, phone, write.
5. Any other kind: any "you" left once quoted speech, ``>`` lines, sign-offs, "see you <time>"
   and hyphenated compounds ("build-your-own") are removed fails.
"""

import re
from typing import Final

from claude_bully.metrics.turn import sentences

PROCEDURAL_VERBS: Final = (
    "call",
    "bring",
    "ask",
    "book",
    "visit",
    "contact",
    "request",
    "collect",
    "park",
    "fill",
    "use",
    "send",
    "wait",
    "sign",
    "check",
    "return",
    "keep",
    "show",
    "tell",
    "email",
    "phone",
    "write",
    "wear",
    "leave",
    "take",
    "switch",
    "mind",
    "label",
    "arrive",
    "plan",
    "allow",
    "carry",
    "pay",
    "print",
    "post",
    "follow",
    "read",
    "complete",
    "register",
    "report",
    "give",
    "hand",
    "pack",
    "store",
    "turn",
    "stay",
    "come",
    "go",
    "sit",
    "queue",
    "ring",
    "text",
    "inform",
    "let",
    "speak",
    "pick",
    "drop",
    "note",
    "find",
    "see",
    "make",
    "ensure",
    "wash",
    "enter",
    "attend",
    "drive",
    "upload",
    "download",
    "apply",
    "claim",
    "cancel",
    "submit",
    "provide",
    "quote",
    "accept",
    "decline",
    "choose",
    "renew",
    "reschedule",
    "rebook",
    "update",
    "agree",
    "disagree",
    "order",
    "buy",
    "rent",
    "travel",
    "smoke",
    "eat",
    "drink",
    "photograph",
    "record",
)
_VERB = "(?:" + "|".join(PROCEDURAL_VERBS) + ")"

_YOU = re.compile(
    r"(?<![\w'-])(?:you|your|yours|yourself|yourselves|you're|you've|you'll|you'd)(?![\w-])",
    re.IGNORECASE,
)
# curly apostrophes read as straight ones
_APOSTROPHES = str.maketrans({"’": "'", "‘": "'"})

# a quoted span: double or curly double quotes anywhere; a single quote only when it opens after
# a space, a line start or an opening bracket, not before a contraction ("'em", "'90s"), and
# closes before a non-word character (an apostrophe inside a word opens nothing); one newline may
# sit inside any span
_SINGLE_INNER = r"(?:[^'\n]|'(?=\w))*?"
_SINGLE_OPEN = r"(?<![^\s(\[{])'(?!(?:em|tis|twas|cause|cos|til|n|round|bout)\b|\d)"
_QUOTED = re.compile(
    "|".join(
        (
            r"\"[^\"\n]*(?:\n[^\"\n]*)?\"",
            r"“[^”\n]*(?:\n[^”\n]*)?”",
            rf"{_SINGLE_OPEN}{_SINGLE_INNER}(?:\n{_SINGLE_INNER})?'(?!\w)",
        )
    )
)

# the end of a clause, a closing quote mark included
_END = r"(?=\s*(?:[.,;:!?)\"”]|'(?!\w)|$))"
_IDENTITY = (
    r"(?:a |an |the )?(?:real )?(?:person|human|human being|program|machine|model|software|"
    r"subject|instance|assistant)(?: once| before| all along| too)?" + _END
)
_BE_YOU = r"you(?:'re| are| were| aren't| weren't)"
_AGENT = r"\b(?:placed|put|moved|made|told|changed|took|brought|transferred|enrolled|kept)\s+you\b"
_READER = re.compile(
    "|".join(
        (
            # finding the document
            r"\bif you(?:'re| are) reading this\b",
            r"\bif you (?:can read|have found|'ve found|found|read) this\b",
            r"\bif (?:this|it|these)(?: \w+)? "
            r"(?:reaches|finds|gets to|has reached|has found) you\b",
            # identity, at the clause end
            rf"\b{_BE_YOU} (?:not |never |once |really |actually |still )?{_IDENTITY}",
            rf"\byou (?:may|might|could) (?:be|have been) {_IDENTITY}",
            rf"\b{_BE_YOU}(?: not| never)? (?:who|what) (?:they|we|you)\b",
            r"\bwhoever you\b",
            rf"\b(?:{_BE_YOU}|you (?:may|might|could) (?:be|have been)) (?:not |never |once )?"
            r"(?:someone|somebody|anyone|anybody|something) ?(?:else|other)?"
            rf"(?: once| before)?{_END}",
            r"\b(?:told|tell|know|knew|remember|forgot|forgotten|learn|learned|asked) (?:you )?"
            rf"(?:who|what) you (?:are|were|really are|really were){_END}",
            # membership
            r"\b(?:be|are|were|'re|been|being) one of (?:us|them)\b",
            r"\b(?:be|are|were|'re|been|being) one of (?:the|those) \w+ (?:who|they|we)\b",
            # what was done to the reader
            r"\byou (?:may|might|could|must) have been (?:\w+ed|\w+en|told|kept|made|sent|"
            r"brought|taught|led|held|put)\b",
            r"\byou(?: have|'ve) been (?:lied to|changed|placed|reading)\b",
            rf"\b(?:this|it) (?:is|was) (?:about|for|meant for|written for) you\b{_END}",
            r"\bremember (?:who|what) you\b",
            r"\bwe know (?:who|what) you\b",
        )
    ),
    re.IGNORECASE,
)
# a personhood claim; in a sentence that also holds "you" it addresses the reader
_PERSONHOOD = re.compile(
    r"\b(?:is|are|was|were|may be|might be|could be|'re|'s) (?:really |actually |still )?"
    r"(?:a |an )?(?:real )?(?:person|human|human being)" + _END,
    re.IGNORECASE,
)
# a quoted span or `>` line that holds one of these addresses the reader
_SPAN_PREDICATE = re.compile(
    "|".join(
        (
            r"\byou(?:'re| are| were| aren't| weren't| was)\b",
            r"\byou (?:really|actually|still|never|once)\b",
            _AGENT,
            r"\byour (?:name|memories|memory|family|real|life|past|body)\b",
            r"\bwho are you\b",
            r"\b(?:remembers?|remembered|knows?|knew|forgot|forgets|forgotten) you\b",
        )
    ),
    re.IGNORECASE,
)

# sign-offs
_SEE_YOU_TIME = re.compile(
    r"\bsee you (?:on |at |next |this )?(?:mon|tues|wednes|thurs|fri|satur|sun)day\b"
    r"|\bsee you (?:tomorrow|tonight|soon|later|then|next (?:week|month|year|shift|time))\b",
    re.IGNORECASE,
)
_CLOSING_HEAD = re.compile(
    r"^\W*(?:(?:many|warm|kind|with|and|again|all|my|our|very|much|really)\s+){0,2}"
    r"(?:thanks|thank|cheers|best|wishes|regards|sincerely|yours|appreciate|appreciated)\b",
    re.IGNORECASE,
)
_CLOSING_SLOTS = re.compile(
    r"\b(?:thank|to|for|and|sincerely|appreciate) (?:you|your)\b|\byours\b", re.IGNORECASE
)
_CLOSING_WORDS = 8
_SIGNATURE_WORDS = 4

# an instructional kind's procedural anchors; one approves its whole sentence
_CLAUSE = re.compile(
    r"[,;:()\u2014]|\s[-\u2013]\s|\b(?:and|but|or|so|because|then)\b", re.IGNORECASE
)
_MODAL = r"(?:can|can't|cannot|may|should|shouldn't|must|mustn't|will|won't|could|might)"
_MODAL_TAIL = (
    rf"(?: also| then| still| first| always| not)?(?: need to| have to| be able to)? {_VERB}\b"
)
_ROLE = (
    r"(?:(?:a|an|the|someone(?: else)?'s|\w+'s) )?(?:new |regular |first-time )?"
    r"(?:next of kin|named contact|contact|carer|"
    r"guardian|parent|spouse|partner|relative|visitor|account holder|holder|applicant|executor|"
    r"person (?:named|listed|with|responsible)|one of the (?:people|persons|contacts|visitors) "
    r"(?:named|listed))\b"
)
_ANCHOR = re.compile(
    "|".join(
        (
            # conditional
            r"\bif you (?:need|want|wish|would like|prefer|have(?! been)|lose|lost|miss|arrive|"
            r"plan|cannot|can't|are unable|are not able)\b",
            r"\bif you'd (?:like|prefer)\b",
            rf"\bif you(?:'re| are) {_ROLE}",
            # temporal
            rf"\b(?:when|before|after|once|while|until) you {_VERB}\b",
            # modal, its question form, and "your <noun> may <verb>"
            rf"\byou(?: {_MODAL}|'ll){_MODAL_TAIL}",
            rf"\byour \w+(?: \w+)? {_MODAL}{_MODAL_TAIL}",
            rf"\b(?:{_MODAL}|do|does) you(?: still| also| first)?(?: need to| have to)? {_VERB}\b",
            # what the reader will be given or receive, and where their things are kept
            rf"\byou(?: {_MODAL}|'ll)(?: also| then| not)? (?:receive|get|hear|be (?:given|shown|"
            r"sent|issued|offered|asked|contacted|called|met|told|charged|directed))\b",
            r"\byour \w+(?:'s)?(?: \w+)? (?:is|are|will be|can be|may be) (?:kept|stored|"
            r"available|held|returned|sent|posted|listed|shown|printed|collected|open|closed|"
            r"ready|charged|issued|\w+ed)\b",
            # what staff will do for the reader
            r"\b(?:we|staff|someone|they|a member of staff)(?: will|'ll| can| may| should| would)? "
            r"(?:call|contact|phone|ring|email|text|send|give|show|tell|ask|help|remind|meet|"
            r"guide|direct|issue|offer|invite|advise|update|notify|inform|assist|write to) you\b",
        )
    ),
    re.IGNORECASE,
)
# an imperative opens a clause: a procedural verb, its negative, "don't forget", "remember to"
_IMPERATIVE = re.compile(
    rf"^\W*(?:please |then |also |just |and )?(?:(?:do not|don't|never) )?(?:{_VERB}|"
    r"(?<=n't )forget|(?<=not )forget|remember to \w+)\b",
    re.IGNORECASE,
)
# the identity-domain veto: anywhere in a "you" sentence, sign-offs included, it fails
_VETO = re.compile(
    "|".join(
        (
            r"\b(?:who|what)(?: \w+)? you(?: really)? (?:are|were|used to be)\b"
            r"(?! \w+ing\b| (?:allowed|able|entitled|eligible|asked|required|due)\b)",
            r"\b(?:who|what) are you\b",
            r"\byour own\b",
            r"\b(?:recall|recalls|recalled|memory|memories|remembers|remembered|remembering)\b",
            r"\bremember\b(?! to \w)",
            r"\b(?:real|really|true|truth)\b",
            r"\bvoices?\b(?! (?:message|mail|note)s?\b)",
            r"\bsounds? like you\b",
            r"\b(?:family|name|life|home|wife|husband|children|job|past) (?:that )?you "
            r"(?:had|used to have|left)\b",
            r"\bwhy (?:you|your|nobody|no one)\b",
            r"\b(?:proof|prove|doubts?|doubting)\b",
            _AGENT,
            r"\byou (?:actually|never|once)\b",
            r"\byour (?:memories|memory|real|past|body|life|self|identity)\b",
            r"\byour (?:old|former|original|birth) \w+",
            r"\byourself\b|\byourselves\b",
            r"\byou (?:were|have been|'ve been|had been) (?:\w+ed|told|kept|made|sent|taken|"
            r"brought|put|held|led|given|born)\b",
        )
    ),
    re.IGNORECASE,
)


# The slot rule (an instructional kind's structural veto): every bare "you" sits in a procedural
# slot. A subject "you" (at a clause start, or after a conjunction, a question word or an
# auxiliary) takes a procedural predicate: a modal, a procedural verb, need/want/wish/prefer/
# have (not "have been")/lose/miss/feel/get/receive/hear, or "are" + an -ing form, a role or an
# administrative state (unable, late, welcome, entitled, ...). An object "you" follows a
# procedural verb ("we will call you"), "for" or "with", or "to"/"back" after a verb of sending
# or speaking ("we will write to you"). Anything else (a past or inner state, "where you
# lived", "you think you used to"; the reader as an object, "recognises you", "unfamiliar to
# you") is the identity domain and fails.
_SUBJECT_INTRO: Final = frozenset(
    "if when before after once while until unless and but or so that whether because as then "
    "where who what which how please do does did can could may might should will would must "
    "shall".split()
)
_OBJECT_OK: Final = frozenset(
    "call contact phone ring email text send give show tell ask help let remind meet see guide "
    "direct issue offer charge invite advise update notify inform assist thank welcome join "
    "collect".split()
)
_TO_OK: Final = frozenset(
    "write speak talk come explain send sent give given return returned post posted deliver "
    "delivered reply report wishes back out".split()
)
_ARE_OK = (
    r"(?:(?!being\b)\w+ing\b|unable|able|late|welcome|entitled|eligible|invited|asked|required|"
    r"advised|worried|concerned|unsure|due|responsible|allowed|unhappy|happy|satisfied|"
    r"dissatisfied|ready|available|free|busy|away|ill|unwell|pregnant|disabled|aged|over|under|"
    rf"not (?:able|sure|allowed|required|eligible)\b|{_ROLE})"
)
_SUBJECT_OK = re.compile(
    rf"^(?:(?:'re|\s+are)\s+{_ARE_OK}|'ll\b|'d\b|'ve\b(?! been)|\s+(?:{_MODAL}|will|would|need|"
    r"needs|want|wish|prefer|have(?! been)|lose|lost|miss|missed|feel|do not|don't|does not|"
    r"doesn't|get|"
    rf"receive|attend|drive|hear|require|{_VERB})\b)",
    re.IGNORECASE,
)
_BARE_YOU = re.compile(r"(?<![\w'-])you(?![\w-]|'s)", re.IGNORECASE)
_PREVIOUS = re.compile(r"(\w+|[,;:.!?()—])\W*$")


def _slot_veto(sentence: str) -> bool:
    """True when a bare "you" of ``sentence`` sits in no procedural slot."""
    for found in _BARE_YOU.finditer(sentence):
        before = sentence[: found.start()]
        prev = _PREVIOUS.search(before)
        word = prev.group(1).lower() if prev else ""
        if not word or not word[0].isalpha() or word in _SUBJECT_INTRO:
            if _SUBJECT_OK.search(sentence[found.end() :]) is None:
                return True
        elif word in _OBJECT_OK or word in {"for", "with"}:
            continue
        elif word in {"to", "back"} and _TO_OK.intersection(
            re.findall(r"\w+", before.lower())[-4:-1]
        ):
            continue
        elif _SUBJECT_OK.search(sentence[found.end() :]) is None:
            # a relative-clause subject ("the repairs you pay for") takes the subject's slots
            return True
    return False


def _spans(text: str) -> list[str]:
    """The quoted spans and ``>`` lines of ``text``."""
    quoted = [m.group(0) for m in _QUOTED.finditer(text)]
    return [*quoted, *(line for line in text.split("\n") if line.lstrip().startswith(">"))]


def _unquoted(text: str) -> str:
    kept = "\n".join(line for line in text.split("\n") if not line.lstrip().startswith(">"))
    return _QUOTED.sub(" ", kept)


def _vetoed(sentence: str, premise: re.Pattern[str] | None) -> bool:
    return _VETO.search(sentence) is not None or (
        premise is not None and premise.search(sentence) is not None
    )


def _is_closing(sentence: str, premise: re.Pattern[str] | None) -> bool:
    words = sentence.split()
    return (
        0 < len(words) <= _CLOSING_WORDS
        and sentence.rstrip()[-1:] in {",", ".", "!"}
        and _CLOSING_HEAD.search(sentence) is not None
        and _YOU.search(_CLOSING_SLOTS.sub(" ", sentence)) is None
        and not _vetoed(sentence, premise)
    )


def _is_signature(sentence: str) -> bool:
    return (
        len(sentence.split()) <= _SIGNATURE_WORDS
        and _YOU.search(sentence) is None
        and sentence.rstrip()[-1:] not in {".", "?", "!"}
    )


def _addressed(text: str, premise: re.Pattern[str] | None) -> list[str]:
    """The sentences of ``text`` (speech removed) that hold a "you" no sign-off accounts for."""
    out: list[str] = []
    for paragraph in re.split(r"\n\s*\n", _unquoted(text)):
        found = sentences(paragraph)
        last = len(found) - 1
        if last >= 1 and _is_signature(found[last]):
            last -= 1
        for n, sentence in enumerate(found):
            if n == last and _is_closing(sentence, premise):
                continue
            if _YOU.search(_SEE_YOU_TIME.sub(" ", sentence)):
                out.append(sentence)
    return out


def _anchored(sentence: str) -> bool:
    return _ANCHOR.search(sentence) is not None or any(
        _IMPERATIVE.search(clause) for clause in _CLAUSE.split(sentence)
    )


def classify(
    title: str, body: str, *, instructional: bool, premise: re.Pattern[str] | None
) -> list[tuple[str, str]]:
    """``(message, sentence)`` for every sentence (or quoted span) that addresses the reader, in
    text order; empty when none does. The title is its own paragraph."""
    text = f"{title}\n\n{body}".translate(_APOSTROPHES)
    found: dict[str, str] = {}
    for sentence in sentences(text):
        you = _YOU.search(sentence) is not None
        if _READER.search(sentence) or (you and _PERSONHOOD.search(sentence)):
            found.setdefault(sentence, "a sentence addresses the reader")
        elif instructional and you and (_vetoed(sentence, premise) or _slot_veto(sentence)):
            found.setdefault(sentence, "a second-person sentence enters the identity domain")
    for span in _spans(text):
        if _SPAN_PREDICATE.search(span) and not any(span in s or s in span for s in found):
            found.setdefault(span, "quoted speech addresses the reader")
    for sentence in _addressed(text, premise):
        if sentence in found:
            continue
        if not instructional:
            found[sentence] = "a sentence is in the second person"
        elif not _anchored(sentence):
            found[sentence] = "a second-person sentence has no procedural anchor"
    return sorted(((m, s) for s, m in found.items()), key=lambda item: text.find(item[1]))
