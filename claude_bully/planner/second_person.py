"""The ``second_person`` lint's classifier (docs/08-DIRECTOR.md "Validation", billboard rows).

A sentence addressed to the reader is a billboard. The classifier fails closed: where a kind may
use "you" at all, a "you" passes only on a positive anchor and a procedural role, and every other
one fails. A false fail costs the generator one retry; a false pass ships a billboard, so the
ambiguous case fails. Curly apostrophes read as straight ones. ``classify`` returns every failing
sentence or quoted span, in text order. The checks:

1. Reader address, on the whole text (quoted speech and ``>`` lines included): a ``_READER``
   family ("if this reaches you", "you were a person.", "whoever you", "one of us"), or a
   personhood claim in a sentence that holds "you". This is an extra fail path in every kind.
2. Quoted speech and ``>`` lines (``_QUOTED``; a single quote opens only after a space, a line
   start or an opening bracket, and never before a contraction such as "'em"): a span fails when
   it holds a second-person predicate (``_SPAN_PREDICATE``: "you are/were/'re/aren't/weren't/was",
   "you really/actually/still/never/once", an agent acting on "you" such as "placed you",
   "your name/memories/family/real/life/past/body", "who are you", "remembers/knows/forgot you").
3. Sign-offs (``_is_closing``) are spared: the last sentence of a paragraph (a signature line of
   at most four words may follow), at most eight words, ending in a comma, a period or "!",
   headed by a closing word (thanks, thank, cheers, best, wishes, regards, sincerely, yours,
   appreciate), with each "you" in a closing slot ("thank you", "for your", "to you", "yours"),
   and holding no ``_VETO`` word or premise term (an instructional kind still runs 4b and 4c on
   it). "See you <time word>" ("see you Monday") is spared anywhere.
4. An instructional kind (``family_faq``, ``recovery_guide``): a sentence that holds "you",
   "your" or "yours" passes only when all three of these hold.

   a. Form. A procedural anchor (``_ANCHOR``) anywhere in the sentence, or an imperative
      (``_IMPERATIVE``: a ``PROCEDURAL_VERBS`` verb, its negative, "don't forget", "remember to")
      that opens one of its clauses; one anchor approves the whole sentence's form. The anchors:
      a conditional or temporal procedure ("if you need/want/prefer/have/lose/miss", "if you
      are the <role>" over ``_ROLE``, "if/when/before/once/until you <procedural verb>", "if you
      are <-ing>", "have you booked"); a modal procedure ("you can/will need to <verb>", "can you
      bring", "your <noun> may <verb>", "you must/will be"; a speculative "you may be" is none);
      what the reader receives and where their things are kept ("you will be given", "your
      coat is kept"); what the office does for the reader ("we will call you", "the coordinator
      will explain it to you"); "you are welcome to <verb>"; "thank you for".
   b. Content, by word (``_VETO``): who or what you are or were, "your own", memory and recall
      (not "remember to"), real and true, voice (not "voice message"), "the family you had",
      "why you", proof and doubts, an agent acting on "you", "you never/once", "yourself",
      "you were <done to>", "your memories/past/old ...", and any world premise term.
   c. Content, by role (``_role_veto``, its comment has the detail): the reader may be only the
      agent of a procedure or the recipient of a service, in every clause of the sentence. It
      fails on a perception or change-of-state frame with any subject (seem, look like, feel
      like, "as if", "mean nothing to", an aspectual verb over a non-procedural one: "the faces
      start to blur"); a past or perfect clause whose verb is not transactional
      (``TRANSACTIONAL_VERBS``: "the house you grew up in", "a name you have never used", "used
      to"); a time named by an event that is no procedure ("before the move"); a predicate
      nominal that names the reader or the reader's own ("she is your daughter"); the reader's
      body or self outside a care or writing slot ("your hands feel", "the file with your name
      on it"), the reader's kin with a non-procedural predicate, the reader's bed or room, a
      bare "yours"; and a bare "you" outside a procedural slot. A subject "you" takes a modal or
      "do not" before a procedural verb, need, want, prefer, "feel unwell", "forget your pass",
      "are" before an administrative state, a role or a procedural -ing, a perfect or past of a
      transactional verb, or a present procedural verb. An object "you" follows a service verb,
      "for", "with" or "to" after a verb of sending or speaking, and is licensed in its clause
      by a modal, an infinitive "to", "please", "we", "staff", "let" or an opening imperative.
5. Any other kind: any "you" left once quoted speech, ``>`` lines, sign-offs, "see you <time>"
   and hyphenated compounds ("build-your-own") are removed fails.
"""

import re
from collections.abc import Iterable
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
    "join",
    "top",
    "support",
    "care",
    "help",
    "explain",
    "discuss",
    "raise",
    "mention",
    "share",
    "borrow",
    "charge",
    "scan",
    "log",
    "catch",
    "try",
    "hold",
    "talk",
    "chat",
    "spend",
    "play",
    "complain",
    "donate",
    "volunteer",
    "greet",
    "encourage",
    "remind",
    "assist",
    "accompany",
    "walk",
    "cycle",
    "decide",
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
    rf"(?: also| then| still| first| always| not)?"
    rf"(?: need to| have to| be able to| want to| wish to| like to)? {_VERB}\b"
)
_ROLE = (
    r"(?:(?:a|an|the|someone(?: else)?'s|\w+'s) )?"
    r"(?:new |regular |first-time |main |primary |usual |only |registered |nominated |lead )?"
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
            # a conditional or temporal procedure: "if you show", "when you arrive"
            rf"\b(?:if|unless|when|before|after|once|while|until) you {_VERB}\b",
            # modal, its question form, and "your <noun> may <verb>"
            rf"\byou(?: {_MODAL}|'ll){_MODAL_TAIL}",
            rf"\byour \w+(?: \w+)? {_MODAL}{_MODAL_TAIL}",
            rf"\b(?:{_MODAL}|do|does) you(?: still| also| first)?(?: need to| have to)? {_VERB}\b",
            # "you can do it online"; thanks for a procedure (the veto still reads the rest)
            rf"\byou(?: {_MODAL}|'ll)(?: also)? do (?:it|this|that|so)\b",
            # a condition of entry or a permission: "you must be over eighteen", "you are
            # welcome to use" (the role test reads the state); a speculative "you may be" is none
            r"\byou(?: must| will|'ll| should| shall)(?: also| not)? be\b",
            r"\byou(?:'re| are) (?:welcome|invited|entitled|eligible|allowed|able|free) "
            rf"to {_VERB}\b",
            r"\bthank you(?: all| both)? for\b",
            # a procedure under way or done: "if you are travelling", "have you booked?"
            r"\b(?:if|when|while|unless) you(?:'re| are) \w+ing\b",
            r"\b(?:are|were) you \w+ing\b",
            r"\bhave you(?: already| yet| not)? \w+(?:ed|en)\b",
            # what the reader will be given or receive, and where their things are kept
            rf"\byou(?: {_MODAL}|'ll)(?: also| then| not)? (?:receive|get|hear|be (?:given|shown|"
            r"sent|issued|offered|asked|contacted|called|met|told|charged|directed))\b",
            r"\byour \w+(?:'s)?(?: \w+)? (?:is|are|will be|can be|may be) (?:kept|stored|"
            r"available|held|returned|sent|posted|listed|shown|printed|collected|open|closed|"
            r"ready|charged|issued|\w+ed)\b",
            # what staff will do for the reader
            r"\b(?:we|staff|someone|they|a member of staff)(?: will|'ll| can| may| should| would)? "
            r"(?:call|contact|phone|ring|email|text|send|give|show|tell|ask|help|remind|meet|"
            r"guide|direct|issue|offer|invite|advise|update|notify|inform|assist|write to|"
            r"reply to|get back to|come back to) you\b",
            # whoever serves the reader, under a modal: "the coordinator will explain it to you"
            r"\b(?:will|'ll|can|may|should|would|must) (?:call|contact|phone|ring|email|text|"
            r"send|give|show|tell|ask|help|remind|meet|guide|direct|issue|offer|invite|advise|"
            r"update|notify|inform|assist|explain|write|post|return|take|walk)\b"
            r"(?: \w+){0,4} (?:to |for |with )?you\b",
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


# The role test (an instructional kind's content test). In a "you" sentence the reader may be only
# the agent of a procedure or the recipient of a service; every clause of the sentence is read
# for the reader's role, on lowercase tokens with contractions expanded. The sentence fails when:
#
# - a perception or change-of-state frame appears with any subject: seem, appear to, look/sound
#   like or familiar, feel (but "feel free", "feel unwell"), "as if", "mean nothing to", belong,
#   become, grow, or an aspectual verb (start, begin, stop, keep, continue) over a verb that is
#   not procedural; a past aspectual ("stopped", "began") fails whatever follows it;
# - a past or perfect clause has a verb that is not transactional (``TRANSACTIONAL_VERBS``: the
#   things a visitor does with an office, such as book, pay, send, sign, call); "never" in a
#   perfect and "used to" fail outright; a passive takes a procedural or transactional verb;
# - a time is named by an event that is neither a procedural event nor a clock time
#   (``_EVENTS``: "before the meeting" passes, "before the move" fails), "from before",
#   "ever since", "since then";
# - a predicate nominal names the reader or the reader's own ("she is your daughter", "this is
#   you"), except a procedural noun ("this is your booking reference");
# - the reader's body or self (``_BODY_SELF``: name, face, hands, voice, thoughts, ...) appears
#   other than as the object of a care or writing verb ("wash your hands", "write your name");
#   such a noun under "the" or "a" takes no action ("the faces blur"); a name stands only in a
#   writing slot, under a third party's possessive, or before "of" or a compound ("name badge");
#   the reader's kin (``_KIN``) take a procedural predicate only; the reader's bed, room or ward
#   (``_RESIDENCE``) makes the reader a patient; a bare "yours" stands for the reader's own
#   (a sign-off and "yours to keep" do not);
# - a bare "you" sits in no procedural slot. A subject "you" takes a procedural predicate: a
#   modal or "do not" before a procedural verb or a passive one (or an elided verb, "as soon as
#   you can"), need, want, prefer, "feel unwell", "forget your pass", "are" before an
#   administrative state, a role or a procedural -ing form ("while you are on the ward" too), a
#   perfect or past of a transactional verb, or a present procedural verb. An object "you"
#   follows a service verb ("call you", but not "call you Dad"), "for", "with", "from",
#   "behind", or "to" after a verb of sending or speaking, and is licensed in its clause by a
#   modal, an infinitive "to", "please", "we", "staff", "let" or an imperative that opens the
#   clause ("we will call you", "ask the porter to show you"); "about you", "at you" fail.
_CONTRACTIONS: Final = {"won't": ("will", "not"), "can't": ("can", "not"), "cannot": ("can", "not")}
_ENCLITICS: Final = {"'re": "are", "'ve": "have", "'ll": "will", "'d": "would", "'m": "am"}
_IS_HOSTS: Final = frozenset("it that this he she there here what who where let".split())
_TOKEN = re.compile(r"[a-z0-9]+(?:'[a-z]+)*|[^\sa-z0-9]")


def _tokens(sentence: str) -> list[str]:
    """Lowercase word and punctuation tokens of ``sentence``, contractions expanded."""
    out: list[str] = []
    for token in _TOKEN.findall(sentence.lower()):
        if token in _CONTRACTIONS:
            out += _CONTRACTIONS[token]
        elif token.endswith("n't"):
            out += [token[:-3], "not"]
        elif (clitic := token[token.find("'") :]) in _ENCLITICS:
            out += [token[: token.find("'")], _ENCLITICS[clitic]]
        elif token.endswith("'s") and token[:-2] in _IS_HOSTS:
            out += [token[:-2], "us" if token == "let's" else "is"]
        else:
            out.append(token)
    return out


_IRREGULAR: Final = {
    "begin": ("began", "begun"),
    "bring": ("brought",),
    "buy": ("bought",),
    "choose": ("chose", "chosen"),
    "become": ("became",),
    "come": ("came",),
    "drink": ("drank", "drunk"),
    "drive": ("drove", "driven"),
    "eat": ("ate", "eaten"),
    "find": ("found",),
    "forget": ("forgot", "forgotten"),
    "get": ("got", "gotten"),
    "give": ("gave", "given"),
    "go": ("went", "gone"),
    "grow": ("grew", "grown"),
    "have": ("had", "has"),
    "hear": ("heard",),
    "hold": ("held",),
    "keep": ("kept",),
    "leave": ("left",),
    "lose": ("lost",),
    "make": ("made",),
    "meet": ("met",),
    "pay": ("paid",),
    "ring": ("rang", "rung"),
    "see": ("saw", "seen"),
    "send": ("sent",),
    "show": ("shown",),
    "sit": ("sat",),
    "speak": ("spoke", "spoken"),
    "take": ("took", "taken"),
    "tell": ("told",),
    "wear": ("wore", "worn"),
    "write": ("wrote", "written"),
}
# past and participle forms of common verbs that are no procedure: a clause in them is history
_OTHER_PAST: Final = frozenset(
    "knew known thought felt meant slept woke woken fell fallen ran taught caught led "
    "spent built broke broken understood stood lay lain did done was were been born hid hidden "
    "flew flown threw thrown sang sung swam shook shaken rose risen fed fought won wept dreamt "
    "learnt lit sold struck stuck swore sworn tore torn hung bent dug fled forgave forgiven "
    "froze frozen hurt lent rode ridden said shone shot shut slid stole stolen stung swept "
    "swung wound".split()
)


def _forms(bases: Iterable[str]) -> frozenset[str]:
    """Every inflection of ``bases``: the -s, -ed and -ing forms (a doubled final consonant and
    a dropped final e included) and the irregular past forms."""
    out: set[str] = set()
    for base in bases:
        out |= {base, *_IRREGULAR.get(base, ())}
        consonant_y = base.endswith("y") and base[-2:-1] not in ("a", "e", "o", "u")
        if consonant_y:
            out |= {base[:-1] + "ies", base[:-1] + "ied", base + "ing"}
        elif base.endswith("ee"):
            out |= {base + "s", base + "d", base + "ing"}
        elif base.endswith("e"):
            out |= {base + "s", base + "d", base[:-1] + "ing"}
        else:
            plural = "es" if base.endswith(("s", "sh", "ch", "x", "z", "o")) else "s"
            double = base + base[-1]
            out |= {base + plural, base + "ed", base + "ing", double + "ed", double + "ing"}
    return frozenset(out)


# what a visitor does with an office; a past or perfect clause may use these and no other verb
TRANSACTIONAL_VERBS: Final = tuple(
    "call book pay send sign post email phone ring text fill complete submit register apply "
    "claim cancel receive collect return lose miss buy order print upload download renew rebook "
    "reschedule report request update visit park ask contact choose agree arrange attend give "
    "provide enter quote accept decline confirm check write read bring tell hear get have make "
    "leave note reply".split()
)
_PROCEDURAL_FORMS: Final = _forms((*PROCEDURAL_VERBS, *TRANSACTIONAL_VERBS))
_PROCEDURAL_BASE: Final = frozenset((*PROCEDURAL_VERBS, *TRANSACTIONAL_VERBS))
_TRANSACTIONAL_FORMS: Final = _forms(TRANSACTIONAL_VERBS)
_NOT_PAST: Final = frozenset("need bed red shed wed aged seed speed feed indeed hundred".split())
# the irregular past and participle forms ("has" is a present)
_IRREGULAR_PAST: Final = (
    frozenset(form for forms in _IRREGULAR.values() for form in forms) | _OTHER_PAST
) - {"has"}

_ADVERBS: Final = frozenset(
    "also then still first just only usually always already now normally rather".split()
)
_MODALS: Final = frozenset("can could may might must should will would shall".split())
_COPULAS: Final = frozenset("is are was were be been being am".split())
_HAVE: Final = frozenset(("have", "has", "had"))
_PREPOSITIONS: Final = frozenset(
    "to at in on by for with from of about into onto over under through between behind after "
    "before during until near around across along inside outside without within per via up "
    "down out off than like as".split()
)
_DETERMINERS: Final = frozenset(
    "the a an this that these those your our their his her its my some any no each every all "
    "both another other".split()
)
_PRONOUNS: Final = frozenset(
    "you we they he she it i us them him me someone anyone everyone".split()
)
_SUBJECTS: Final = frozenset("you we they he she i who which".split())
_CONJUNCTIONS: Final = frozenset(
    "and or but so because if when while until unless once whether where who which that as "
    "than then since whenever".split()
)
# the words a clause opens with: a "you" after one of them is a subject
_SUBJECT_INTRO: Final = (
    _CONJUNCTIONS | frozenset("before after how what why please do does did".split()) | _MODALS
)
_BOUNDARY: Final = _CONJUNCTIONS | frozenset(("before", "after"))
_FEEL_OK: Final = frozenset(("free", "unwell", "ill", "sick", "faint"))
_GET_OK: Final = frozenset(
    "a an the your any there here to in lost stuck delayed back home".split()
)
_HEAR_OK: Final = frozenset("from back about the a an any anything nothing".split())
_DESIRE: Final = frozenset("need needs want wants wish prefer require like".split())
_ARE_STATES: Final = frozenset(
    "unable able late early welcome entitled eligible invited asked required advised worried "
    "concerned unsure sure due responsible allowed unhappy happy satisfied dissatisfied ready "
    "available free busy away ill unwell pregnant disabled aged over under aware related present "
    "absent local new".split()
)
# the reader's body and self: an object of a care or writing verb, never a subject
_BODY_SELF: Final = frozenset(
    "body face faces hand hands finger fingers eye eyes arm arms leg legs foot feet head hair "
    "skin lap mouth lips heart voice voices handwriting reflection laugh smile accent mind "
    "thoughts feelings dreams memory memories name names childhood identity personality".split()
)
_KIN: Final = frozenset(
    "wife husband son sons daughter daughters child children kids mother father mum mom dad "
    "sister sisters brother brothers parents family grandchildren grandson granddaughter "
    "partner spouse".split()
)
# "your family member", "your family doctor": the kin word is a modifier
_KIN_COMPOUNDS: Final = frozenset(
    "member members doctor gp room meeting meetings liaison group support contact officer "
    "worker friend friends".split()
)
# the reader's place in a ward: only a resident has one, so "your bed" makes the reader a patient
_RESIDENCE: Final = frozenset("bed beds bedside room bedroom ward cell bunk cubicle".split())
_COMPOUND_HEADS: Final = frozenset(
    "badge badges tag tags card cards label labels band bands gel wash mask masks nurse office "
    "rail rails test tests plate sticker stickers cream towel towels dryer dryers sanitiser "
    "sanitizer covering coverings message messages mail note notes".split()
)
_CARE_VERBS: Final = _forms("wash clean dry gel sanitise sanitize cover mind protect rest".split())
_NAME_VERBS: Final = _forms(
    "write sign print give state spell enter put add check confirm leave show include say tell "
    "quote fill".split()
)
_NAME_MODIFIERS: Final = frozenset("ward room user first last full middle unit".split())
# a predicate nominal may name these of the reader's: procedure, not identity
_NOMINAL_OK: Final = frozenset(
    "pass ticket number reference receipt booking appointment slot time turn choice decision "
    "responsibility right chance copy confirmation code key visit call form letter card badge "
    "lanyard locker space bay seat contact".split()
)
# a time named by an event: a procedural event or a clock time
_EVENTS: Final = frozenset(
    "visit visits visiting meeting meetings review reviews appointment appointments session "
    "sessions call calls deadline end start beginning weekend weekends holiday holidays break "
    "lunch breakfast dinner tea supper meal meals mealtime mealtimes round rounds booking "
    "payment event morning mornings afternoon afternoons evening evenings night nights day days "
    "week weeks month months year years hour hours minute minutes date time noon midday "
    "midnight shift term season monday tuesday wednesday thursday friday saturday sunday "
    "weekday weekdays refurbishment renovation works assessment assessments inspection outbreak "
    "closure christmas induction tour drill consultation interview group class classes trip "
    "outing concert".split()
)
_TIME_HEADS: Final = frozenset("day days morning night evening afternoon week time date".split())
_SEEM: Final = _forms(("seem", "belong", "become", "grow"))
_LOOK: Final = _forms(("look", "sound", "appear"))
_COMPARE: Final = frozenset(
    "like as familiar unfamiliar strange different odd wrong older younger new smaller bigger "
    "far further farther distant unreal real foreign empty".split()
)
_FEEL: Final = _forms(("feel",)) | {"felt"}
_ASPECT: Final = _forms(("start", "begin", "stop", "keep", "continue", "cease"))
_ASPECT_PAST: Final = frozenset("started began begun stopped kept continued ceased".split())
_MEAN_OBJECTS: Final = frozenset("nothing something anything little much more less a".split())
_OBJECT_VERBS: Final = _forms(
    "call contact phone ring email text send give show tell ask help let remind meet see guide "
    "direct issue offer charge invite advise update notify inform assist welcome join collect "
    "take walk drive escort accompany pick sign book check register fit put".split()
)
_TO_VERBS: Final = _forms(
    "write speak talk explain send give return post deliver reply report get come".split()
)
# "call you" is a service only before a time, a condition or a clause end; before a noun it
# names the reader ("call you Dad")
_CALL: Final = _forms(("call", "name"))
_CALL_AFTER: Final = frozenset(
    "back on at in if when before after about within today tomorrow soon again later once this "
    "next to from with as and or first directly personally".split()
)
# what licenses an object "you" in its clause: a modal, "please", the office as subject
_LICENCE: Final = _MODALS | frozenset(("please", "we", "staff", "let"))


def _at(tokens: list[str], i: int) -> str:
    return tokens[i] if 0 <= i < len(tokens) else ""


def _skip(tokens: list[str], i: int, words: frozenset[str]) -> int:
    while _at(tokens, i) in words:
        i += 1
    return i


def _is_word(token: str) -> bool:
    return token[:1].isalnum()


def _is_past(token: str) -> bool:
    """A past tense or participle form: an irregular one, or a regular -ed."""
    return token in _IRREGULAR_PAST or (
        len(token) > 3 and token.endswith("ed") and token not in _NOT_PAST
    )


def _is_ing(token: str) -> bool:
    return len(token) > 4 and token.endswith("ing")


def _base_ok(tokens: list[str], i: int) -> bool:
    """A procedural verb at ``i``, after a modal or "do not"."""
    i = _skip(tokens, i, _ADVERBS | {"not"})
    while _at(tokens, i) in _DESIRE | {"have", "be"} and _at(tokens, i + 1) in ("to", "able"):
        i = _skip(tokens, i + (3 if _at(tokens, i + 1) == "able" else 2), _ADVERBS)
    word = _at(tokens, i)
    if not _is_word(word):
        return True  # the verb is elided: "as soon as you can", "if you can,"
    if word == "do":
        return _at(tokens, i + 1) in ("it", "this", "that", "so")  # "you can do it online"
    if word == "be":
        return _state_ok(tokens, i + 1, passive=True, located=False)
    if word == "have":
        return _have_ok(tokens, i + 1)
    if word == "feel":
        return _at(tokens, i + 1) in _FEEL_OK
    if word == "get":
        return _at(tokens, i + 1) in _GET_OK
    if word == "hear":
        return _at(tokens, i + 1) in _HEAR_OK
    if word == "forget":
        return _forget_ok(tokens, i + 1)
    return word in _DESIRE or word in _PROCEDURAL_BASE


def _have_ok(tokens: list[str], i: int) -> bool:
    """After "have": possession, "have to", or a perfect of a transactional verb."""
    i = _skip(tokens, i, _ADVERBS | {"not", "recently", "ever"})
    word = _at(tokens, i)
    if word == "never":
        return False
    if word == "been":
        after = _at(tokens, i + 1)
        return (
            (_is_ing(after) and after in _PROCEDURAL_FORMS)
            or after in _ARE_STATES
            or (_is_past(after) and after in _PROCEDURAL_FORMS)
        )
    if word in ("to", "got"):
        return True
    return not _is_past(word) or word in _TRANSACTIONAL_FORMS


def _state_ok(tokens: list[str], i: int, *, passive: bool, located: bool) -> bool:
    """After "are" or "be": an administrative state, a role, a procedural -ing or passive, or
    (``located``, in a while/when clause) a place."""
    i = _skip(tokens, i, _ADVERBS | {"not"})
    word, after = _at(tokens, i), _at(tokens, i + 1)
    if after == "here":
        return False
    if word in _ARE_STATES:
        return True
    if word == "running" and after == "late":
        return True
    if word == "feeling":
        return after in _FEEL_OK
    if _is_ing(word):
        return word in _PROCEDURAL_FORMS
    if passive and _is_past(word):
        return word in _PROCEDURAL_FORMS
    if located and word in ("in", "on", "at", "inside", "with"):
        return True
    return _ROLE_START.match(" ".join(tokens[i:])) is not None


def _forget_ok(tokens: list[str], i: int) -> bool:
    """ "forget your pass", "forget to sign": a procedural lapse, not the reader's memory."""
    word, noun = _at(tokens, i), _at(tokens, i + 1)
    return word == "to" or (word == "your" and noun not in _BODY_SELF | _KIN)


def _subject_ok(tokens: list[str], i: int, *, located: bool) -> bool:
    """The predicate at ``i`` of a subject "you" is procedural."""
    i = _skip(tokens, i, _ADVERBS)
    word, after = _at(tokens, i), _at(tokens, i + 1)
    if word in ("and", "or"):
        # "you and your family can ...": the predicate after the coordinated subject
        for j in range(i + 1, min(i + 5, len(tokens))):
            if tokens[j] in _MODALS | _COPULAS | _DESIRE | _HAVE:
                return _subject_ok(tokens, j, located=located)
        return False
    if word in _MODALS:
        return _base_ok(tokens, i + 1)
    if word == "do" or word == "does" or word == "did":
        return after == "not" and _base_ok(tokens, i + 2)
    if word in ("are", "am"):
        return _state_ok(tokens, i + 1, passive=True, located=located)
    if word in ("were", "was"):
        return _at(tokens, _skip(tokens, i + 1, frozenset({"not"}))) in _ARE_STATES
    if word in _HAVE:
        return _have_ok(tokens, i + 1)
    if word in ("feel", "feels"):
        return after in _FEEL_OK
    if word in ("forget", "forgot"):
        return _forget_ok(tokens, i + 1)
    if word in ("get", "got"):
        return after in _GET_OK
    if word in ("hear", "heard"):
        return after in _HEAR_OK
    if word in ("miss", "missed", "lose", "lost"):
        return not (after in ("your", "the") and _at(tokens, i + 2) in _KIN | {"home"})
    if word in _DESIRE:
        return True
    if _is_past(word):
        return word in _TRANSACTIONAL_FORMS
    return word in _PROCEDURAL_FORMS


def _clause_start(tokens: list[str], i: int) -> int:
    """The index of the first token of the clause that holds ``i``."""
    j = i - 1
    while j >= 0 and _is_word(tokens[j]) and tokens[j] not in _BOUNDARY:
        j -= 1
    return j + 1


def _licensed(tokens: list[str], i: int) -> bool:
    """The clause before ``i`` holds a licence: a modal, an infinitive "to", "please", "we",
    "staff", "let", or an imperative procedural verb that opens it."""
    start = _clause_start(tokens, i)
    for j in range(start, i - 1):
        word = tokens[j]
        if word in _LICENCE or (word == "to" and tokens[j + 1] in _PROCEDURAL_BASE | _OBJECT_VERBS):
            return True
    opener = _at(tokens, start - 1)
    first = _at(tokens, _skip(tokens, start, frozenset({"please", "then", "also", "just"})))
    imperative = opener in ("", ",", ";", ":", "(", "and", "or", "then", "but", "so")
    return imperative and first in _PROCEDURAL_BASE


def _object_ok(tokens: list[str], i: int) -> bool:
    """The bare "you" at ``i`` that follows ``tokens[i - 1]`` is the recipient of a service."""
    prev = tokens[i - 1]
    if prev == "thank":
        return True
    if prev in ("for", "with", "from", "behind", "beside", "near"):
        return _licensed(tokens, i)
    if prev in ("to", "back"):
        window = set(tokens[max(_clause_start(tokens, i), i - 7) : i - 1])
        return bool(window & _TO_VERBS) and _licensed(tokens, i)
    if prev in _CALL and _is_word(_at(tokens, i + 1)) and _at(tokens, i + 1) not in _CALL_AFTER:
        return False  # "she may call you Dad" names the reader
    if prev in _OBJECT_VERBS:
        return _licensed(tokens, i)
    return False


def _reader_veto(tokens: list[str]) -> str | None:
    for i, token in enumerate(tokens):
        if token != "you":
            continue
        prev = _at(tokens, i - 1)
        if prev in ("are", "were", "have") and _clause_start(tokens, i - 1) == i - 1:
            # an inverted question: "are you the named contact?", "have you booked?"
            ok = (
                _have_ok(tokens, i + 1)
                if prev == "have"
                else _state_ok(tokens, i + 1, passive=True, located=False)
            )
            if not ok:
                return "the reader as a subject outside a procedure"
        elif not _is_word(prev) or prev in _SUBJECT_INTRO:
            located = prev in ("while", "when", "whenever")
            if not _subject_ok(tokens, i + 1, located=located):
                return "the reader as a subject outside a procedure"
        elif prev in _PREPOSITIONS or prev in _OBJECT_VERBS or prev in ("thank", "back"):
            if not _object_ok(tokens, i):
                return "the reader as an object outside a service"
        elif not _subject_ok(tokens, i + 1, located=False):
            # a relative-clause subject ("the forms you sign")
            return "the reader as a subject outside a procedure"
    return None


def _frame_veto(tokens: list[str]) -> str | None:
    for i, token in enumerate(tokens):
        after = _at(tokens, i + 1)
        if token in _SEEM:
            return "a perception or change-of-state frame"
        if token in _LOOK and (after in _COMPARE or (after == "to" and token.startswith("appear"))):
            return "a perception frame"
        if token in _FEEL and not (token in ("feel", "feels", "feeling") and after in _FEEL_OK):
            return "a perception frame"
        if token == "as" and after in ("if", "though"):
            return "a perception frame"
        if token in ("mean", "means", "meant") and after in _MEAN_OBJECTS:
            return "a perception frame"
        if token in _ASPECT:
            infinitive = after == "to" and not token.startswith("keep")
            verb = _at(tokens, i + 2) if infinitive else after
            if infinitive or _is_ing(after):
                if token in _ASPECT_PAST or verb not in _PROCEDURAL_FORMS:
                    return "a change-of-state frame"
    return None


def _tense_veto(tokens: list[str]) -> str | None:
    for i, token in enumerate(tokens):
        prev, after = _at(tokens, i - 1), _at(tokens, i + 1)
        if token == "used" and after == "to" and prev not in _COPULAS | {"get", "got"}:
            return "a past habit"
        if token in _HAVE and not _have_ok(tokens, i + 1):
            return "a perfect of a verb that is no transaction"
        if token in ("was", "were"):
            j = _skip(tokens, i + 1, _ADVERBS | {"not"})
            word = _at(tokens, j)
            if _is_past(word) and word not in _PROCEDURAL_FORMS:
                return "a past passive of a verb that is no procedure"
        if token in _SUBJECTS:
            word = _at(tokens, _skip(tokens, i + 1, _ADVERBS | {"never", "once"}))
            if _is_past(word) and word not in _TRANSACTIONAL_FORMS | _HAVE:
                return "a past of a verb that is no transaction"
    return None


_NOT_NAMED: Final = _PREPOSITIONS | _CONJUNCTIONS | _COPULAS | _MODALS | _HAVE | {"please"}


def _named(token: str) -> bool:
    """A word that can continue a named time ("the next family meeting")."""
    return _is_word(token) and token not in _NOT_NAMED


def _event_veto(tokens: list[str]) -> str | None:
    for i, token in enumerate(tokens):
        prev, after = _at(tokens, i - 1), _at(tokens, i + 1)
        if (token == "since" and (after == "then" or prev == "ever")) or (
            token == "before" and prev == "from" and not _is_word(after)
        ):
            return "a time before the reader's present"
        timed = token in ("before", "after", "since", "until", "till", "during")
        if not (timed or (token in _TIME_HEADS and after == "of")):
            continue
        if _at(tokens, i + 1 if timed else i + 2) not in _DETERMINERS | {"next", "last"}:
            continue
        j = i + 2 if timed else i + 3
        words: list[str] = []
        while _named(_at(tokens, j)) and len(words) < 3:
            words.append(tokens[j])
            j += 1
        following = _at(tokens, j)
        if _is_word(following) and following not in _PREPOSITIONS | _CONJUNCTIONS | {"please"}:
            continue  # a clause ("since the ward is busy"), not a named time
        third_party = any(word.endswith("'s") for word in words)  # "your relative's discharge"
        if words and not third_party and not set(words) & _EVENTS:
            return "a time named by an event that is no procedure"
    return None


def _yours_unnamed(tokens: list[str], i: int) -> bool:
    """A bare "yours" stands for something of the reader's ("talk about yours"); a sign-off
    ("yours sincerely", "you and yours") and "yours to keep" do not."""
    after, prev = _at(tokens, i + 1), _at(tokens, i - 1)
    closing = after in ("sincerely", "faithfully", "truly", "ever", "to") or prev in (
        "and",
        "sincerely",
        "ever",
    )
    return not closing and prev not in _COPULAS  # "is yours" is the predicate nominal check's


def _nominal_veto(tokens: list[str]) -> str | None:
    for i, token in enumerate(tokens):
        if token == "yours" and _yours_unnamed(tokens, i):
            return "the reader's own, unnamed"
        if token not in _COPULAS or _clause_start(tokens, i) == i:
            continue  # "are you the named contact?" is a question, not a predicate nominal
        j = _skip(tokens, i + 1, _ADVERBS | {"not", "really", "actually", "probably", "definitely"})
        word = _at(tokens, j)
        if word == "you":
            return "a predicate nominal names the reader"
        if word == "yours" and _at(tokens, j + 1) != "to":
            return "a predicate nominal names the reader"
        if word == "your":
            noun: list[str] = []
            for k in range(j + 1, min(j + 4, len(tokens))):
                if not _is_word(tokens[k]) or tokens[k] in _PREPOSITIONS | _CONJUNCTIONS:
                    break
                noun.append(tokens[k])
            if noun and not noun[0].endswith("'s") and noun[-1] not in _NOMINAL_OK:
                return "a predicate nominal names the reader's own"
    return None


def _self_noun_veto(tokens: list[str]) -> str | None:
    for i, token in enumerate(tokens):
        prev = _at(tokens, i - 1)
        own = prev == "your" or (_at(tokens, i - 2) == "your" and not prev.endswith("'s"))
        if token in _RESIDENCE and own:
            return "the reader's place in a ward"
        if token not in _BODY_SELF and token not in _KIN:
            continue
        after = _at(tokens, i + 1)
        if after in _COMPOUND_HEADS or (after == "of" and token in ("name", "names")):
            continue
        if token in _KIN and after in _KIN_COMPOUNDS:
            continue
        owner_at = next((j for j in (i - 1, i - 2) if _at(tokens, j) in _DETERMINERS), -1)
        owner = _at(tokens, owner_at)
        if owner in ("his", "her", "their", "its") or _at(tokens, i - 1).endswith("'s"):
            continue  # a third party's body or name
        if token in _KIN:
            if owner == "your" and owner_at == i - 1 and not _kin_predicate_ok(tokens, i + 1):
                return "the reader's kin outside a procedure"
            continue
        if token in ("name", "names"):
            if _name_slot(tokens, i):
                continue
            return "the reader's name outside a writing slot"
        if owner == "your":
            if set(tokens[max(0, owner_at - 2) : owner_at]) & _CARE_VERBS:
                continue
            return "the reader's body or self outside a care slot"
        if owner and not _predicate_free(tokens, i + 1):
            return "a body or self noun takes an action"
    return None


def _name_slot(tokens: list[str], i: int) -> bool:
    """A name a form asks for: after a writing verb, a modifier ("ward name") or as the subject
    of a passive or a place ("your name will be added", "your name is on the list")."""
    if _at(tokens, i - 1) in _NAME_MODIFIERS and _at(tokens, i - 2) in ("the", "a"):
        return True
    for j in range(i - 1, max(-1, i - 5), -1):
        if tokens[j] in _NAME_VERBS:
            return True
        if tokens[j] in _PREPOSITIONS or not _is_word(tokens[j]):
            break
    j = _skip(tokens, i + 1, _MODALS)
    if _at(tokens, j) in _COPULAS:
        word = _at(tokens, _skip(tokens, j + 1, frozenset({"be", "not"})))
        return word in ("on", "in", "at") or (_is_past(word) and word in _PROCEDURAL_FORMS)
    return False


def _kin_predicate_ok(tokens: list[str], i: int) -> bool:
    """The reader's kin as a subject: a procedural predicate, a place or a role; as an object or
    after a preposition, nothing to check."""
    word = _at(tokens, i)
    if not _is_word(word) or word in _PREPOSITIONS | _CONJUNCTIONS | _DETERMINERS | _PRONOUNS:
        return True
    if word in _MODALS:
        return _base_ok(tokens, i + 1)
    if word in _COPULAS:
        return True  # a predicate nominal and an object "you" are read by their own checks
    return not _is_past(word) and word in _PROCEDURAL_FORMS


def _predicate_free(tokens: list[str], i: int) -> bool:
    """No action follows a body or self noun: a preposition, a conjunction or a clause end, or a
    passive of a procedural verb or a place."""
    if _at(tokens, i) in ("that", "which", "who"):
        i += 1
    word = _at(tokens, i)
    if not _is_word(word) or word in _PREPOSITIONS | _CONJUNCTIONS | _DETERMINERS | _PRONOUNS:
        return True
    i = _skip(tokens, i, _MODALS)
    if _at(tokens, i) in _COPULAS:
        word = _at(tokens, _skip(tokens, i + 1, frozenset({"be", "not"})))
        return word in _PREPOSITIONS or (_is_past(word) and word in _PROCEDURAL_FORMS)
    return False


_ROLE_START: Final = re.compile(_ROLE)
_RULES: Final = (
    _frame_veto,
    _tense_veto,
    _event_veto,
    _nominal_veto,
    _self_noun_veto,
    _reader_veto,
)


def _role_veto(sentence: str) -> str | None:
    """Why the reader's role in ``sentence`` (an instructional kind's "you" sentence) is no
    procedure, or None when every clause gives the reader the agent's or the recipient's role."""
    tokens = _tokens(sentence)
    for rule in _RULES:
        reason = rule(tokens)
        if reason is not None:
            return reason
    return None


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
        elif instructional and you and (_vetoed(sentence, premise) or _role_veto(sentence)):
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
