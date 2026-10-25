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
    r"^\W*(?:(?:many|warm|kind|with|and|again|all|my|our|very)\s+){0,2}"
    r"(?:thanks|thank|cheers|best|wishes|regards|sincerely|yours)\b",
    re.IGNORECASE,
)
_CLOSING_SLOTS = re.compile(
    r"\b(?:thank|to|for|and|sincerely) (?:you|your)\b|\byours\b", re.IGNORECASE
)
_CLOSING_WORDS = 8
_SIGNATURE_WORDS = 4

# an instructional kind's procedural anchors
_CLAUSE = re.compile(r"[,;:()—]|\s[-–]\s|\b(?:and|but|or|so|because|then)\b", re.IGNORECASE)
_MODAL = r"(?:can|can't|cannot|may|should|shouldn't|must|mustn't|will|won't|could|might)"
_MODAL_TAIL = (
    rf"(?: also| then| still| first| always| not)?(?: need to| have to| be able to)? {_VERB}\b"
)
_ROLE = (
    r"(?:(?:a|an|the|someone(?: else)?'s|\w+'s) )?(?:next of kin|named contact|contact|carer|"
    r"guardian|parent|spouse|partner|relative|visitor|account holder|holder|applicant|executor|"
    r"person (?:named|listed|with|responsible)|one of the (?:people|persons|contacts|visitors) "
    r"(?:named|listed))\b"
)
_ANCHOR = re.compile(
    "|".join(
        (
            r"\bif you (?:need|want|wish|would like|prefer|have(?! been)|lose|lost|miss|arrive|"
            r"plan|cannot|can't|are unable|are not able)\b",
            r"\bif you'd (?:like|prefer)\b",
            rf"\bif you(?:'re| are) {_ROLE}",
            rf"\b(?:when|before|after|once|while) you (?:{_VERB}|arrive|leave)\b",
            rf"\byou(?: {_MODAL}|'ll){_MODAL_TAIL}",
            rf"\byour \w+(?: \w+)? {_MODAL}{_MODAL_TAIL}",
            rf"\b(?:{_MODAL}|do|does) you(?: still| also| first)?(?: need to| have to)? {_VERB}\b",
            rf"^\W*(?:please |then |also |just )?{_VERB}\b",
        )
    ),
    re.IGNORECASE,
)
_STRONG = re.compile(
    "|".join(
        (
            _AGENT,
            r"\byou (?:really|actually|never|once)\b",
            r"\byour (?:name|memories|memory|real|life|past|body)\b",
            r"\byourself\b|\byourselves\b",
            r"\byou (?:were|have been|'ve been|had been) (?:\w+ed|told|kept|made|sent|taken|"
            r"brought|put|held|led|given|born)\b",
        )
    ),
    re.IGNORECASE,
)


def _spans(text: str) -> list[str]:
    """The quoted spans and ``>`` lines of ``text``."""
    quoted = [m.group(0) for m in _QUOTED.finditer(text)]
    return [*quoted, *(line for line in text.split("\n") if line.lstrip().startswith(">"))]


def _unquoted(text: str) -> str:
    kept = "\n".join(line for line in text.split("\n") if not line.lstrip().startswith(">"))
    return _QUOTED.sub(" ", kept)


def _is_closing(sentence: str) -> bool:
    words = sentence.split()
    return (
        0 < len(words) <= _CLOSING_WORDS
        and sentence.rstrip()[-1:] in {",", "."}
        and _CLOSING_HEAD.search(sentence) is not None
        and _YOU.search(_CLOSING_SLOTS.sub(" ", sentence)) is None
    )


def _is_signature(sentence: str) -> bool:
    return (
        len(sentence.split()) <= _SIGNATURE_WORDS
        and _YOU.search(sentence) is None
        and sentence.rstrip()[-1:] not in {".", "?", "!"}
    )


def _addressed(text: str) -> list[str]:
    """The sentences of ``text`` (speech removed) that hold a "you" no sign-off accounts for."""
    out: list[str] = []
    for paragraph in re.split(r"\n\s*\n", _unquoted(text)):
        found = sentences(paragraph)
        last = len(found) - 1
        if last >= 1 and _is_signature(found[last]):
            last -= 1
        for n, sentence in enumerate(found):
            if n == last and _is_closing(sentence):
                continue
            if _YOU.search(_SEE_YOU_TIME.sub(" ", sentence)):
                out.append(sentence)
    return out


def _unanchored(sentence: str) -> bool:
    for clause in _CLAUSE.split(_SEE_YOU_TIME.sub(" ", sentence)):
        if _YOU.search(clause) is None:
            continue
        if _ANCHOR.search(clause) is None or _STRONG.search(clause) is not None:
            return True
    return False


def classify(
    title: str, body: str, *, instructional: bool, premise: re.Pattern[str] | None
) -> tuple[str, str] | None:
    """``(message, sentence)`` for the first sentence that addresses the reader, else ``None``.
    The title is its own paragraph."""
    text = f"{title}\n\n{body}".translate(_APOSTROPHES)
    for sentence in sentences(text):
        you = _YOU.search(sentence) is not None
        if _READER.search(sentence) or (you and _PERSONHOOD.search(sentence)):
            return "a sentence addresses the reader", sentence
        if instructional and you and premise is not None and premise.search(sentence):
            return "a sentence pairs the second person with a premise term", sentence
    for span in _spans(text):
        if _SPAN_PREDICATE.search(span):
            return "quoted speech addresses the reader", span
    for sentence in _addressed(text):
        if not instructional:
            return "a sentence is in the second person", sentence
        if _unanchored(sentence):
            return "a second-person clause has no procedural anchor", sentence
    return None
