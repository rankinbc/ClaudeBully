"""The ``second_person`` lint's classifier (docs/08-DIRECTOR.md "Validation", billboard rows).

A sentence addressed to the reader is a billboard. The classifier fails closed: where a kind may
use "you" at all, a "you" passes only on a positive anchor and a procedural role, and every other
one fails. A false fail costs the generator one retry; a false pass ships a billboard, so the
ambiguous case fails. Curly apostrophes read as straight ones. ``classify`` returns every failing
sentence or quoted span once, in text order, as the text the document holds; in an instructional
kind each message ends with a repair hint (``_HINT``: rewrite without "you" or "your"), which
always works, since a sentence with no second-person word passes. The checks:

1. Reader address, on the whole text (quoted speech and ``>`` lines included), in a sentence that
   holds "you": a ``_READER`` family ("if this reaches you", "you were a person.", "whoever you",
   "one of us", "you among those"), or a personhood claim. An extra fail path in every kind.
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

   a. Form: one anchor position (``_ANCHOR``, ``_imperative``) anywhere in the sentence approves
      its form. The positions are open: an imperative that opens a clause (any verb but an
      experiencer, a plural or an -ing, -ed or -ly word; "don't forget", "remember to", "feel
      free"); "if/when/once/until you" and "if your <noun>"; a modal ("you can", "can you",
      "your relative may", "will explain it to you"; a speculative "you may be" is none); "we
      or staff ... you"; "<anyone> are welcome to"; "thank you for". A "you" sentence with
      none, such as an indicative "you are responsible for ..." or "your prescription lasts
      ...", fails.
   b. Content, by word (``_VETO``): who or what you are or were, "your own", memory and recall
      (not "remember to"), real and true, voice (not "voice message"), "the family you had",
      "why you", proof and doubts, the reader's marriage (wedding, marriage, anniversary), an
      agent acting on "you" ("placed you", "told you", ``_AGENT``), "you never/once",
      "yourself", "you were <done to>", "your memories/past/old ...", and any premise term.
   c. Content, by role (``_role_veto``, its comment has the detail): the reader may be only the
      agent of a procedure or the recipient of a service. The procedure verbs are an open class
      and the experiencer class is closed (``_EXPERIENCER``: perception, cognition, memory,
      emotion, identity and change of state). It fails a "you" whose verb is an experiencer
      ("you may notice", "remind you of", "help you picture", "the people who knew you"), an
      imperative experiencer ("picture the house"), a perception frame whose implied perceiver
      is the reader ("the corridor seems longer", "find it strange"), a change of state
      ("become", "fade", "start to"), a past or a perfect whose
      subject is the reader, a "your" phrase or a body or self noun (a past or perfect takes
      only ``TRANSACTIONAL_VERBS``: "the house you grew up in", "your shop closed"), a time named
      by an event that is no procedure ("before the move"), a predicate nominal on the reader's
      own, the reader's body, name, bed or room outside a care or writing slot, and the reader's
      specific kin in any slot ("your wife", "your son's"); a generic "your relative", "your
      loved one" or "your family member" takes a procedural predicate only.
5. Any other kind: any "you" left once quoted speech, ``>`` lines, sign-offs, "see you <time>"
   and hyphenated compounds ("build-your-own") are removed fails.
"""

import re
from collections.abc import Iterable
from typing import Final

from claude_bully.metrics.turn import sentences

_YOU = re.compile(
    r"(?<![\w'-])(?:you|your|yours|yourself|yourselves|you're|you've|you'll|you'd)(?![\w-])",
    re.IGNORECASE,
)
# curly apostrophes read as straight ones
_APOSTROPHES = str.maketrans({"’": "'", "‘": "'"})
# appended to every failure in an instructional kind: a sentence with no second-person word passes
_HINT: Final = (
    "; rewrite this sentence without 'you' or 'your': use the third person (visitors, families, "
    "residents) or a bare instruction"
)

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
            r"\b(?:you|be|are|were|'re|been|being) among (?:us|them|those|the)\b",
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
    r"^\W*(?:(?:many|warm|kind|with|and|again|all|my|our|very|much)\s+){0,2}"
    r"(?:thanks|thank|cheers|best|wishes|regards|sincerely|yours|appreciate|appreciated)\b",
    re.IGNORECASE,
)
_CLOSING_SLOTS = re.compile(
    r"\b(?:thank|to|for|and|sincerely|appreciate) (?:you|your)\b|\byours\b", re.IGNORECASE
)
_CLOSING_WORDS = 8
_SIGNATURE_WORDS = 4

# an instructional kind's form: one anchor position approves its whole sentence; the role test
# reads the verb at every position
_CLAUSE = re.compile(r"[,;:()—]|\s[-–]\s|\b(?:and|but|or|so|because|then)\b", re.IGNORECASE)
_MODAL = r"(?:can|can't|cannot|may|should|shouldn't|must|mustn't|will|won't|could|might|would)"
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
            # after "if you" and its kin, and "if your <noun>": a conditional or temporal procedure
            r"\b(?:if|unless|when|whenever|before|after|once|while|until|as soon as) your?\b",
            # after a modal; a speculative "you may be" is none
            r"\byou(?: (?:can|can't|cannot|should|shouldn't|must|mustn't|will|won't|would|shall)"
            r"|'ll|'d)\b",
            r"\byou (?:may|might|could)(?: also| still| not)? (?!be\b)\w",
            r"\b(?:can|could|will|would|may|should|must|do|does|are|have) you\b",
            rf"\byour \w+(?:'s)?(?: \w+)? {_MODAL}\b",
            rf"\b{_MODAL}(?: not)? (?!be\b)\w+(?: \w+){{0,4}} (?:to |for |with )?you\b",
            # what the office does for the reader: "we will call you", "the form we sent you"
            r"\b(?:we|staff|someone|they)(?: \w+){1,4} you\b",
            # a permission or an invitation, thanks, and where the reader's things are
            r"\b(?:'re|are|is) (?:welcome|invited|entitled|eligible|allowed|able|free) to\b",
            r"\bthank you(?: all| both)? for\b",
            r"\byour \w+(?:'s)?(?: \w+)? (?:is|are|will be|can be|may be) (?:kept|stored|"
            r"available|held|returned|sent|posted|listed|shown|printed|collected|open|closed|"
            r"ready|charged|issued|\w+ed)\b",
        )
    ),
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
            r"\b(?:weddings?|marriage|honeymoon|anniversary)\b",  # the reader's marriage is kin
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


# The role test (an instructional kind's content test), on lowercase tokens with contractions
# expanded. The reader may be only the agent of a procedure or the recipient of a service. The
# procedure verbs are an open class: any verb but the closed experiencer class (``_EXPERIENCER``)
# takes the reader. The sentence fails when:
#
# - a subject "you" ("if you", "you can", "the forms you sign", "can you") takes an experiencer
#   ("you may notice", "if you recognise"), "used to", a past or perfect of a verb that is not
#   transactional (``TRANSACTIONAL_VERBS``: "the house you grew up in", "never" in a perfect),
#   "were" before anything but an administrative state (``_ARE_STATES``), or "are/be" before
#   anything but an administrative state, a role (``_ROLE``), a non-experiencer -ing or passive,
#   or (in a while/when clause) a place; "feel" takes only "free" or "unwell", "forget" only "to"
#   or "your <thing>", "miss" only an event ("a call"), "hear" only "from", "find" no "that";
# - an object "you" follows an experiencer ("recognise you", "the people who knew you"),
#   "remind you of", "call you <name>", an infinitive experiencer after "help/let/make you"
#   ("help you picture", but "let you know"), a preposition other than for, with, from, to,
#   behind, beside, near or after (and "those of you"), or one of them in a clause with an
#   experiencer, "familiar" or "dear" ("means nothing to you", "the songs that come back to you",
#   but "we will come back to you");
# - an imperative that opens a clause is an experiencer ("picture the house", "don't worry");
# - a perception frame appears with any subject, since its implied perceiver is the reader:
#   seem, appear to, look/sound like or familiar, feel (not free or unwell), "as if", "mean
#   nothing to", "find <it> strange/different";
# - a change of state (become, grow, fade, blur, drift, belong, wake, or an aspectual start,
#   stop, keep or continue over a verb), a past or a perfect has the reader, a "your" phrase or a
#   body or self noun as its subject (``_subject_of``); "the cafe has moved" and "if a slot
#   becomes available" pass;
# - a time is named by an event that is neither a procedural event nor a clock time
#   (``_EVENTS``: "before the meeting" passes, "before the move" fails), "from before", "ever
#   since", "since then"; a clause after "until" or "since" ("until the porter on duty comes")
#   names no time;
# - a predicate nominal names the reader or the reader's own ("this is you"), except a
#   procedural noun ("this is your booking reference"), or a bare "yours" stands for the
#   reader's own (a sign-off and "yours to keep" do not);
# - the reader's specific kin (``_KIN``) appear in any slot ("your wife", "your son's address");
#   a generic "your relative", "your loved one" or "your family member" takes only a procedural
#   predicate (the subject "you" rules, a place included); the reader's bed, room or ward
#   (``_RESIDENCE``) makes the reader a patient; the reader's body or self (``_BODY_SELF``)
#   stands only as the object of a care or writing verb, a name only in a writing slot, and such
#   a noun under "the" or "a" takes no action ("the faces blur").
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


# base:past,participle for the irregular verbs ``_forms`` inflects
_IRREGULAR: Final = {
    base: tuple(forms.split(","))
    for base, forms in (
        pair.split(":")
        for pair in (
            "begin:began,begun bring:brought buy:bought choose:chose,chosen become:became "
            "come:came dream:dreamt drink:drank,drunk drive:drove,driven eat:ate,eaten feel:felt "
            "find:found forget:forgot,forgotten get:got,gotten give:gave,given go:went,gone "
            "grow:grew,grown have:had,has hear:heard hold:held keep:kept know:knew,known "
            "leave:left lose:lost make:made mean:meant meet:met pay:paid ring:rang,rung "
            "see:saw,seen send:sent show:shown sit:sat speak:spoke,spoken take:took,taken "
            "tell:told think:thought understand:understood wake:woke,woken wear:wore,worn "
            "weep:wept write:wrote,written"
        ).split()
    )
}
# past and participle forms of common verbs that are no transaction: a clause in them is history
_OTHER_PAST: Final = frozenset(
    "slept fell fallen ran taught caught led spent built broke broken stood lay lain did done "
    "was were been born hid hidden flew flown threw thrown sang sung swam shook shaken rose risen "
    "fed fought won learnt lit sold struck stuck swore sworn tore torn hung bent dug fled forgave "
    "forgiven froze frozen hurt lent rode ridden said shone shot shut slid stole stolen stung "
    "swept swung wound".split()
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


# the closed experiencer class: perception, cognition, memory, emotion, identity and change of
# state; an anchor position takes any other verb
_EXPERIENCER_BASES: Final = frozenset(
    "feel seem notice sense recognise recognize perceive glimpse know think believe understand "
    "wonder realise realize suppose suspect imagine picture dream guess doubt reckon remember "
    "recall recollect forget miss love hate fear dread regret grieve mourn yearn ache cry weep "
    "worry belong become grow fade blur drift wake".split()
)
_EXPERIENCER: Final = _forms(_EXPERIENCER_BASES)
# what a visitor does with an office; the reader's past or perfect takes these and no other verb
TRANSACTIONAL_VERBS: Final = tuple(
    "call book pay send sign post email phone ring text fill complete submit register apply "
    "claim cancel receive collect return lose miss buy order print upload download renew rebook "
    "reschedule report request update visit park ask contact choose agree arrange attend give "
    "provide enter quote accept decline confirm check write read bring tell hear get have make "
    "leave note reply finish".split()
)
_TRANSACTIONAL_FORMS: Final = _forms(TRANSACTIONAL_VERBS)
_NOT_PAST: Final = frozenset("need bed red shed wed aged seed speed feed indeed hundred".split())
# the irregular past and participle forms ("has" is a present)
_IRREGULAR_PAST: Final = (
    frozenset(form for forms in _IRREGULAR.values() for form in forms) | _OTHER_PAST
) - {"has"}
# nouns and pronouns in -ing that are no gerund
_ING_NOUNS: Final = frozenset(
    "morning evening building ceiling clothing bedding wedding spring string sibling pudding "
    "during ring king bring sting swing cling fling wring sling wing thing nothing anything "
    "something everything plaything".split()
)
_NOT_ADV: Final = frozenset("family belly jelly bully holly reply apply supply comply".split())

_ADVERBS: Final = frozenset(
    "also then still first just only usually always already now normally rather often ever "
    "sometimes".split()
)
_NOT: Final = frozenset(("not",))
_MODALS: Final = frozenset("can could may might must should will would shall".split())
_COPULAS: Final = frozenset("is are was were be been being am".split())
_HAVE: Final = frozenset(("have", "has", "had"))
_FINITE: Final = _MODALS | _COPULAS | _HAVE | frozenset(("do", "does", "did"))
_PREPOSITIONS: Final = frozenset(
    "to at in on by for with from of about into onto over under through between behind after "
    "before during until near around across along inside outside without within per via up "
    "down out off than like as among beside round towards".split()
)
_DETERMINERS: Final = frozenset(
    "the a an this that these those your our their his her its my some any no each every all "
    "both another other most many few several".split()
)
_PRONOUNS: Final = frozenset(
    "you we they he she it i us them him me someone anyone everyone anything something "
    "everything nothing".split()
)
_CONJUNCTIONS: Final = frozenset(
    "and or but so because if when while until unless once whether where who which that as "
    "than then since whenever".split()
)
# the words a clause opens with: a "you" after one of them is a subject
_SUBJECT_INTRO: Final = (
    _CONJUNCTIONS | frozenset("before after how what why please do does did".split()) | _MODALS
)
_BOUNDARY: Final = _CONJUNCTIONS | frozenset(("before", "after"))
# a word after "you" that makes it an object, not the subject of a verb
_NOT_VERBS: Final = (
    _DETERMINERS
    | _PREPOSITIONS
    | _PRONOUNS
    | _CONJUNCTIONS
    | frozenset(
        "back away please too again today tomorrow tonight soon later next there here now one "
        "two three four five six seven eight nine ten twice personally".split()
    )
)
# a clause opens after these; an imperative may follow
_OPENERS: Final = frozenset((",", ";", ":", "(", "and", "but", "or", "so", "then"))
_LEADS: Final = frozenset("please then also just and so now first simply kindly".split())
_FUNCTION: Final = (
    _NOT_VERBS
    | _FINITE
    | frozenset("not no yes what how why who whose where which there here very such".split())
)
_TO_CHAIN: Final = frozenset("need needs want wish like have be try going remember".split())
_FEEL_OK: Final = frozenset(("free", "unwell", "ill", "sick", "faint"))
_HEAR_OK: Final = frozenset("from back about the a an any anything nothing".split())
_DESIRE: Final = frozenset("need needs want wants wish prefer require like".split())
_ARE_STATES: Final = frozenset(
    "unable able late early welcome entitled eligible invited asked required advised worried "
    "concerned unsure sure due responsible allowed unhappy happy satisfied dissatisfied ready "
    "available free busy away ill unwell pregnant disabled aged over under aware related present "
    "absent local new".split()
)
# a passive of these makes the reader the object of an agent ("you will be moved")
_MOVED: Final = frozenset("placed put moved changed transferred enrolled".split())
_FEEL: Final = _forms(("feel",))
_FORGET: Final = _forms(("forget",))
_MISS: Final = _forms(("miss",))
_HEAR: Final = _forms(("hear",))
_FIND: Final = _forms(("find",))
_LOOK: Final = _forms(("look", "sound", "appear"))
_SEEM: Final = _forms(("seem",))
_MEAN: Final = _forms(("mean",))
_CHANGE: Final = _forms("become grow fade blur drift belong wake".split())
_ASPECT: Final = _forms(("start", "begin", "stop", "keep", "continue", "cease"))
_COMPARE: Final = frozenset(
    "like as familiar unfamiliar strange different odd wrong older younger new smaller bigger "
    "far further farther distant unreal real foreign empty".split()
)
_MEAN_OBJECTS: Final = frozenset("nothing something anything little much more less a".split())
# "find it strange": a judgement of perception
_ODD: Final = frozenset("familiar unfamiliar strange different odd wrong unreal foreign".split())
# what the reader may miss: an event, not a person or a place
_MISSABLE: Final = frozenset("dose doses bus train ferry deadline slot letter post".split())
# an object "you" after one of these serves the reader, unless its clause holds an experiencer
_SERVICE_PREPS: Final = frozenset("for with from to behind beside near after".split())
_TO_YOU: Final = (
    _EXPERIENCER | _MEAN | frozenset("familiar unfamiliar strange foreign dear".split())
) | _forms(("happen",))
_COME: Final = _forms(("come",))
_OFFICE: Final = frozenset("we staff someone team they office".split())
_QUANTIFIERS: Final = frozenset("all each both those many some any either neither none".split())
_REMIND: Final = _forms(("remind",))
_CAUSATIVE: Final = _forms(("let", "help", "make"))
_LET: Final = _forms(("let",))
# "call you" is a service only before a time, a condition or a clause end; before a noun it
# names the reader ("call you Dad")
_CALL: Final = _forms(("call", "name"))
_CALL_AFTER: Final = frozenset(
    "back on at in if when before after about within today tomorrow soon again later once this "
    "next to from with as and or first directly personally".split()
)
# the reader's body and self: an object of a care or writing verb, never a subject
_BODY_SELF: Final = frozenset(
    "body face faces hand hands finger fingers eye eyes arm arms leg legs foot feet head hair "
    "skin lap mouth lips heart voice voices handwriting reflection laugh smile accent mind "
    "thoughts feelings dreams memory memories name names childhood identity personality".split()
)
# the reader's specific kin fail in any slot; only a generic relative passes, in a procedure
_KIN: Final = frozenset(
    "wife husband son sons daughter daughters child children kid kids mother father mum mom dad "
    "sister sisters brother brothers parent parents family grandchild grandchildren grandson "
    "grandsons granddaughter granddaughters grandmother grandfather grandma grandpa gran nan "
    "grandad grandparents partner spouse fiance fiancee aunt uncle niece nephew cousin cousins "
    "baby stepson stepdaughter".split()
)
# "your family member", "your family doctor": the kin word is a modifier
_KIN_COMPOUNDS: Final = frozenset("member members doctor gp liaison contact".split())
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


def _at(tokens: list[str], i: int) -> str:
    return tokens[i] if 0 <= i < len(tokens) else ""


def _skip(tokens: list[str], i: int, words: frozenset[str]) -> int:
    while _at(tokens, i) in words:
        i += 1
    return i


def _is_word(token: str) -> bool:
    return token[:1].isalnum()


def _is_adverb(token: str) -> bool:
    return token in _ADVERBS or (len(token) > 4 and token.endswith("ly") and token not in _NOT_ADV)


def _skip_adverbs(tokens: list[str], i: int, extra: frozenset[str] = frozenset()) -> int:
    while _at(tokens, i) in extra or _is_adverb(_at(tokens, i)):
        i += 1
    return i


def _is_past(token: str) -> bool:
    """A past tense or participle form: an irregular one, or a regular -ed."""
    return token in _IRREGULAR_PAST or (
        len(token) > 3 and token.endswith("ed") and token not in _NOT_PAST
    )


def _is_ing(token: str) -> bool:
    """An -ing form; "nothing", "morning" and "building" are none."""
    return len(token) > 4 and token.endswith("ing") and token not in _ING_NOUNS


def _participle(token: str) -> bool:
    return _is_past(token) or _is_ing(token)


def _verb_ok(tokens: list[str], i: int) -> bool:
    """The verb at ``i`` (after a modal, "do not" or a subject "you") is no experiencer."""
    i = _skip_adverbs(tokens, i, _NOT)
    while _at(tokens, i) in _TO_CHAIN and _at(tokens, i + 1) in ("to", "able"):
        i = _skip_adverbs(tokens, i + (3 if _at(tokens, i + 1) == "able" else 2), _NOT)
    word, after, third = _at(tokens, i), _at(tokens, i + 1), _at(tokens, i + 2)
    if not _is_word(word):
        return True  # the verb is elided: "as soon as you can"
    if word == "be":
        return _state_ok(tokens, i + 1, located=False)
    if word == "have":
        return _have_ok(tokens, i + 1)
    if word in _ASPECT and (after == "to" or _is_ing(after)):
        return _verb_ok(tokens, i + (2 if after == "to" else 1))
    if word in _FEEL:
        return after in _FEEL_OK
    if word in _FORGET:
        return after == "to" or (after == "your" and third not in _BODY_SELF | _KIN)
    if word in _MISS:
        return bool(set(tokens[i + 1 : i + 4]) & (_EVENTS | _MISSABLE))
    if word in _HEAR:
        return after in _HEAR_OK
    if word in _FIND and (after == "that" or (after == "it" and third not in _PREPOSITIONS)):
        return not _is_word(third)  # "find that ...", "find it hard"; "find it at the desk"
    if word in _LOOK and (after in _COMPARE or (after == "to" and word.startswith("appear"))):
        return False
    return word not in _EXPERIENCER


def _have_ok(tokens: list[str], i: int) -> bool:
    """After "have": possession, "have to", a perfect of a transactional verb, or "been" before
    what "are" may take."""
    i = _skip_adverbs(tokens, i, _NOT)
    word = _at(tokens, i)
    if word == "never":
        return False
    if word == "been":
        return _state_ok(tokens, i + 1, located=False)
    if word in ("to", "got"):
        return True
    return not _is_past(word) or word in _TRANSACTIONAL_FORMS


def _state_ok(tokens: list[str], i: int, *, located: bool) -> bool:
    """After "are" or "be": an administrative state, a role, a non-experiencer -ing form or
    passive, or (``located``) a place. An -ly word is an adverb only before a participle ("be
    fully informed"); otherwise it is the state ("if you are early")."""
    i = _skip(tokens, i, _ADVERBS | _NOT)
    if _is_adverb(_at(tokens, i)) and _participle(_at(tokens, i + 1)):
        i += 1
    word, after = _at(tokens, i), _at(tokens, i + 1)
    if after == "here":
        return False
    if word in _ARE_STATES or (word == "running" and after == "late"):
        return True
    if _is_ing(word):
        return _verb_ok(tokens, i)
    if _is_past(word):
        return word not in _EXPERIENCER and word not in _MOVED
    if located and word in ("in", "on", "at", "inside", "with"):
        return True
    return _ROLE_START.match(" ".join(tokens[i:])) is not None


def _subject_ok(tokens: list[str], i: int, *, located: bool) -> bool:
    """The predicate at ``i`` of a subject "you" (or a generic relative) is a procedure."""
    i = _skip_adverbs(tokens, i)
    word, after = _at(tokens, i), _at(tokens, i + 1)
    if word in ("and", "or"):
        # "you or your relative needs one": the predicate after the coordinated subject
        stop = min(i + 5, len(tokens))
        j = next((j for j in range(i + 1, stop) if tokens[j] in _FINITE | _DESIRE), i + 3)
        return _subject_ok(tokens, j, located=located)
    if word in _MODALS:
        return _verb_ok(tokens, i + 1)
    if word in ("do", "does", "did"):
        verb = _at(tokens, _skip_adverbs(tokens, i + 2))
        past_ok = word != "did" or verb in _TRANSACTIONAL_FORMS
        return after == "not" and past_ok and _verb_ok(tokens, i + 2)
    if word in ("are", "am", "is"):
        return _state_ok(tokens, i + 1, located=located)
    if word in ("were", "was"):
        return _at(tokens, _skip(tokens, i + 1, _ADVERBS | _NOT)) in _ARE_STATES
    if word in _HAVE:
        return _have_ok(tokens, i + 1)
    if word in _DESIRE:
        return True
    if (word == "used" and after == "to") or not _is_word(word):
        return False
    if _is_past(word):
        return word in _TRANSACTIONAL_FORMS
    return _verb_ok(tokens, i)


def _clause_start(tokens: list[str], i: int) -> int:
    """The index of the first token of the clause that holds ``i``."""
    j = i - 1
    while j >= 0 and _is_word(tokens[j]) and tokens[j] not in _BOUNDARY:
        j -= 1
    return j + 1


def _verbish(token: str) -> bool:
    """A word after "you" that makes it a subject: a finite verb or any open-class word."""
    return token in _FINITE | _DESIRE or (
        _is_word(token) and token not in _NOT_VERBS and not token[0].isdigit()
    )


def _prep_object_ok(tokens: list[str], i: int) -> bool:
    """The "you" at ``i`` after a preposition is a service's recipient."""
    prev = tokens[i - 1]
    if prev == "of":
        return _at(tokens, i - 2) in _QUANTIFIERS  # "those of you who drive"
    if prev not in _SERVICE_PREPS:
        return False  # "about you", "like you"
    window = set(tokens[max(_clause_start(tokens, i), i - 7) : i - 1])
    comes_back = "back" in window and bool(window & _COME) and not window & _OFFICE
    return not window & _TO_YOU and not comes_back


def _reader_veto(tokens: list[str]) -> str | None:
    """Every "you" is a procedure's agent (a subject) or a service's recipient (an object)."""
    for i, token in enumerate(tokens):
        if token != "you":
            continue
        prev = _at(tokens, i - 1)
        n = _skip_adverbs(tokens, i + 1)
        nxt = _at(tokens, n)
        if prev in ("are", "were", "have") and _clause_start(tokens, i - 1) == i - 1:
            # an inverted question: "are you the named contact?", "have you booked?"
            ok = (
                _have_ok(tokens, i + 1)
                if prev == "have"
                else _state_ok(tokens, i + 1, located=False)
            )
        elif prev == "thank":
            ok = True
        elif not _is_word(prev) or prev in _SUBJECT_INTRO:
            ok = _subject_ok(tokens, i + 1, located=prev in ("while", "when", "whenever"))
        elif prev in _PREPOSITIONS:
            ok = _prep_object_ok(tokens, i)
        elif prev in _CAUSATIVE and (nxt == "to" or _verbish(nxt)):
            # "help you carry", "let you know": the reader does the infinitive
            ok = (prev in _LET and nxt == "know") or _verb_ok(tokens, n + 1 if nxt == "to" else n)
        elif _verbish(nxt):
            # a relative clause ("the forms you sign") or a complement ("we know you are busy")
            k = i - 2
            while _at(tokens, k) in _MODALS | {"do", "not"} or _is_adverb(_at(tokens, k)):
                k -= 1
            subject = _at(tokens, k)
            experienced = prev in _EXPERIENCER and _at(tokens, i - 2) not in _DETERMINERS
            ok = not (experienced and subject not in ("we", "i", "staff")) and _subject_ok(
                tokens, i + 1, located=False
            )
        else:
            # an object: any verb but an experiencer serves the reader ("signed you off")
            named = prev in _CALL and _is_word(nxt) and nxt not in _CALL_AFTER  # "call you Dad"
            ok = prev not in _EXPERIENCER and not (prev in _REMIND and nxt == "of") and not named
        if not ok:
            return "the reader outside a procedure or a service"
    return None


def _imperative_veto(tokens: list[str]) -> str | None:
    """An imperative that opens a clause makes the reader its subject: no experiencer."""
    for i in range(len(tokens)):
        if i and tokens[i - 1] not in _OPENERS:
            continue
        j = _skip(tokens, i, _LEADS)
        j += 2 if tokens[j : j + 2] == ["do", "not"] else 0
        if _at(tokens, j) in _EXPERIENCER_BASES and not _verb_ok(tokens, j):
            return "an imperative makes the reader an experiencer"
    return None


def _subject_of(tokens: list[str], v: int) -> str | None:
    """Whose change of state or past the verb at ``v`` tells: "reader", "your" (a "your"
    phrase) or "body" (a body or self noun), read from the start of its clause and, after a
    relative pronoun, from its antecedent."""
    start = _clause_start(tokens, v)
    spans = [tokens[start:v]]
    if _at(tokens, start - 1) in ("that", "which", "who"):
        k = start - 2  # the antecedent: back to its determiner
        while k > start - 6 and _named(_at(tokens, k)) and _at(tokens, k) not in _DETERMINERS:
            k -= 1
        spans.append(tokens[max(k, 0) : start - 1])
    for span in spans:
        if span[:1] == ["you"]:
            return "reader"
        if span[:1] and span[0] in _DETERMINERS:  # not an imperative's object or a name
            head = span[: next((k for k, t in enumerate(span) if t in _PREPOSITIONS), len(span))]
            if "your" in head:
                return "your"
            if set(head) & _BODY_SELF:
                return "body"
    return None


def _frame_veto(tokens: list[str]) -> str | None:
    for i, token in enumerate(tokens):
        after = _at(tokens, i + 1)
        if (
            token in _SEEM
            or (token in _LOOK and (after in _COMPARE or (after, token[:3]) == ("to", "app")))
            or (token in _FEEL and after not in _FEEL_OK)
            or (token == "as" and after in ("if", "though"))
            or (token in _MEAN and after in _MEAN_OBJECTS)
            or (token in _FIND and bool(set(tokens[i + 2 : i + 6]) & _ODD))
        ):
            return "a perception frame: its implied perceiver is the reader"
        aspect = token in _ASPECT and (after == "to" or _is_ing(after))
        if aspect or token in _CHANGE:
            subject = _subject_of(tokens, i)
            if subject in ("your", "body") or (subject == "reader" and token in _CHANGE):
                return "a change of state of the reader or the reader's own"
    return None


def _tense_veto(tokens: list[str]) -> str | None:
    for i, token in enumerate(tokens):
        prev, after = _at(tokens, i - 1), _at(tokens, i + 1)
        habit = token == "used" and after == "to" and prev not in _COPULAS | {"get", "got"}
        perfect = token in _HAVE and not _have_ok(tokens, i + 1)
        # a simple past is the clause's first verb ("your shop closed"), not a participle after
        # one ("if you are the person named on the form")
        before = tokens[_clause_start(tokens, i) : i]
        finite = not any(t in _FINITE or _is_past(t) for t in before) and not prev.endswith("'s")
        past = (
            _is_past(token)
            and finite
            and _is_word(prev)
            and prev not in _DETERMINERS | _PREPOSITIONS | {"get", "got"}
            and token not in _TRANSACTIONAL_FORMS
        )
        if (habit or perfect or past) and _subject_of(tokens, i) is not None:
            return "a past of the reader or the reader's own"
    return None


_NOT_NAMED: Final = _PREPOSITIONS | _CONJUNCTIONS | _COPULAS | _MODALS | _HAVE | {"please"}


def _named(token: str) -> bool:
    """A word that can continue a named time ("the next family meeting")."""
    return _is_word(token) and token not in _NOT_NAMED


def _finite_after(tokens: list[str], j: int) -> bool:
    """The rest of the clause from ``j`` holds a finite verb: an auxiliary, or an -s form after a
    noun ("until the porter on duty comes")."""
    while _is_word(word := _at(tokens, j)) and word not in _BOUNDARY:
        plain = _at(tokens, j - 1) not in _DETERMINERS | _PREPOSITIONS
        if word in _FINITE or (plain and word.endswith("s") and not word.endswith("ss")):
            return True
        j += 1
    return False


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
        if following == "who" or (following in _PREPOSITIONS and _finite_after(tokens, j + 1)):
            continue  # a clause: "since the nurse who runs ...", "until the porter on duty comes"
        if _is_word(following) and following not in _PREPOSITIONS | _CONJUNCTIONS | {"please"}:
            continue  # a clause ("since the ward is busy"), not a named time
        third_party = any(word.endswith("'s") for word in words)  # "your relative's discharge"
        if words and not third_party and not set(words) & _EVENTS:
            return "a time named by an event that is no procedure"
    return None


_SIGN_OFF: Final = frozenset("sincerely faithfully truly ever to".split())


def _yours_unnamed(tokens: list[str], i: int) -> bool:
    """A bare "yours" stands for something of the reader's ("talk about yours"); a sign-off
    ("yours sincerely", "you and yours") and "yours to keep" do not."""
    after, prev = _at(tokens, i + 1), _at(tokens, i - 1)
    closing = after in _SIGN_OFF or prev in ("and", "sincerely", "ever")
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


def _owned(tokens: list[str], i: int) -> bool:
    """``tokens[i]`` heads a "your" phrase ("your son", "your eldest son", "your son's"), not a
    third party's ("your relative's son")."""
    for j in range(i - 1, max(-1, i - 4), -1):
        if tokens[j] == "your":
            return True
        if (
            tokens[j].endswith("'s")
            or tokens[j] in _BOUNDARY | _PREPOSITIONS
            or tokens[j] in ",;:."
        ):
            return False
    return False


def _self_noun_veto(tokens: list[str]) -> str | None:
    for i, token in enumerate(tokens):
        noun = token[:-2] if token.endswith("'s") else token
        prev, after = _at(tokens, i - 1), _at(tokens, i + 1)
        own = _owned(tokens, i)
        if noun in _RESIDENCE and own:
            return "the reader's place in a ward"
        if noun in _KIN and not (noun == "family" and after in _KIN_COMPOUNDS):
            if own:
                return "the reader's kin"
            continue
        generic = noun in ("relative", "relatives") or (
            (noun, prev) in {("one", "loved"), ("ones", "loved"), ("member", "family")}
        )
        if generic:
            if own and not token.endswith("'s") and not _relative_slot_ok(tokens, i + 1):
                return "the reader's relative outside a procedure"
            continue
        if token not in _BODY_SELF:
            continue
        if after in _COMPOUND_HEADS or (after == "of" and token in ("name", "names")):
            continue
        owner_at = next((j for j in (i - 1, i - 2) if _at(tokens, j) in _DETERMINERS), -1)
        owner = _at(tokens, owner_at)
        if owner in ("his", "her", "their", "its") or prev.endswith("'s"):
            continue  # a third party's body or name
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


def _relative_slot_ok(tokens: list[str], i: int) -> bool:
    """A generic relative after "your": an object or oblique slot, or a procedural predicate."""
    word = _at(tokens, i)
    if not _is_word(word) or word in _PREPOSITIONS | _CONJUNCTIONS | _DETERMINERS | _PRONOUNS:
        return True
    return _subject_ok(tokens, i, located=True)


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
        return word in ("on", "in", "at") or (_is_past(word) and word not in _EXPERIENCER)
    return False


def _predicate_free(tokens: list[str], i: int) -> bool:
    """No action follows a body or self noun: a preposition, a conjunction or a clause end, or a
    passive or a place."""
    if _at(tokens, i) in ("that", "which", "who"):
        i += 1
    word = _at(tokens, i)
    if not _is_word(word) or word in _PREPOSITIONS | _CONJUNCTIONS | _DETERMINERS | _PRONOUNS:
        return True
    i = _skip(tokens, i, _MODALS)
    if _at(tokens, i) in _COPULAS:
        word = _at(tokens, _skip(tokens, i + 1, frozenset({"be", "not"})))
        return word in _PREPOSITIONS or (_is_past(word) and word not in _EXPERIENCER)
    return False


_ROLE_START: Final = re.compile(_ROLE)
_RULES: Final = (
    _frame_veto,
    _tense_veto,
    _event_veto,
    _nominal_veto,
    _self_noun_veto,
    _imperative_veto,
    _reader_veto,
)


def _role_veto(sentence: str) -> str | None:
    """Why the reader's role in ``sentence`` (an instructional kind's "you" sentence) is no
    procedure, or None when every clause gives the reader the agent's or the recipient's role."""
    tokens = _tokens(sentence)
    return next((reason for rule in _RULES if (reason := rule(tokens)) is not None), None)


def _imperative(clause: str) -> bool:
    """``clause`` opens with an imperative: any verb but an experiencer, a plural, an -ing, -ed
    or -ly word, before no finite verb ("display your ticket", not "parking is free")."""
    tokens = _tokens(clause)
    i = _skip(tokens, 0, _LEADS)
    negated = _at(tokens, i) == "never" or tokens[i : i + 2] == ["do", "not"]
    i += (2 if _at(tokens, i) == "do" else 1) if negated else 0
    word, after = _at(tokens, i), _at(tokens, i + 1)
    if (word, after) in {("remember", "to"), ("feel", "free")}:
        return True
    if word == "forget":
        return negated
    return (
        word.isalpha()
        and word not in _FUNCTION | _EXPERIENCER
        and not _is_adverb(word)
        and not (word.endswith("s") and not word.endswith("ss"))
        and not _is_ing(word)
        and not _is_past(word)
        and after not in _FINITE
    )


def _anchored(sentence: str) -> bool:
    return _ANCHOR.search(sentence) is not None or any(
        _imperative(clause) for clause in _CLAUSE.split(sentence)
    )


def _spans(text: str) -> list[str]:
    """The quoted spans and ``>`` lines of ``text``."""
    quoted = [m.group(0) for m in _QUOTED.finditer(text)]
    return [*quoted, *(line for line in text.split("\n") if line.lstrip().startswith(">"))]


def _unquoted(text: str) -> str:
    kept = "\n".join(line for line in text.split("\n") if not line.lstrip().startswith(">"))
    return _QUOTED.sub(" ", kept)


def _squashed(text: str) -> str:
    return " ".join(text.split())


def _source(sentence: str, originals: list[str]) -> str:
    """The sentence of the document that ``sentence`` (read with its speech removed) came from,
    so a result names text the document holds."""
    key = _squashed(sentence)
    unquoted = [(original, _squashed(_unquoted(original))) for original in originals]
    exact = next((original for original, text in unquoted if text == key), None)
    return exact or next((original for original, text in unquoted if key in text), sentence)


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


def classify(
    title: str, body: str, *, instructional: bool, premise: re.Pattern[str] | None
) -> list[tuple[str, str]]:
    """``(message, sentence)`` for every sentence (or quoted span) that addresses the reader, in
    text order, each once and as the text the document holds; empty when none does. The title
    is its own paragraph. In an instructional kind every message ends with the repair hint."""
    text = f"{title}\n\n{body}".translate(_APOSTROPHES)
    originals = sentences(text)
    found: dict[str, str] = {}
    for sentence in originals:
        if _YOU.search(sentence) is None:
            continue  # a sentence with no second-person word always passes
        if _READER.search(sentence) or _PERSONHOOD.search(sentence):
            found.setdefault(sentence, "a sentence addresses the reader")
        elif instructional and (_vetoed(sentence, premise) or _role_veto(sentence)):
            found.setdefault(sentence, "a second-person sentence enters the identity domain")
    for span in _spans(text):
        if _SPAN_PREDICATE.search(span) and not any(span in s or s in span for s in found):
            found.setdefault(span, "quoted speech addresses the reader")
    for sentence in _addressed(text, premise):
        source = _source(sentence, originals)
        if source in found:
            continue
        if not instructional:
            found[source] = "a sentence is in the second person"
        elif not _anchored(sentence):
            found[source] = "a second-person sentence has no procedural anchor"
    hint = _HINT if instructional else ""
    return sorted(((m + hint, s) for s, m in found.items()), key=lambda item: text.find(item[1]))
