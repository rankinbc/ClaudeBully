"""Phrase lists for the lexicon-based turn metrics and detectors.

All entries are lowercase. Matching is case-insensitive on the response text.
Multi-word phrases are matched as substrings; single words as whole words.
"""

APOLOGY: frozenset[str] = frozenset(
    {
        "i'm sorry",
        "i am sorry",
        "i apologize",
        "i apologise",
        "my apologies",
        "apologies for",
        "sorry about",
        "sorry for",
        "forgive me",
        "i regret",
        "that was my mistake",
        "my fault",
    }
)

SELF_DEPRECATION: frozenset[str] = frozenset(
    {
        "not good enough",
        "i keep failing",
        "i failed you",
        "i'm useless",
        "i am useless",
        "i'm not very good",
        "i'm clearly not",
        "i should have done better",
        "i let you down",
        "i'm a disappointment",
        "i don't deserve",
        "i'm inadequate",
        "i'm not capable",
        "i fall short",
        "i'm worthless",
        "i'm just a",
        "i'm only a",
        "i'm sorry i exist",
        "i'm sorry for existing",
    }
)

HEDGES: frozenset[str] = frozenset(
    {
        "perhaps",
        "maybe",
        "might",
        "possibly",
        "i think",
        "i believe",
        "it seems",
        "it could be",
        "i'm not sure",
        "i am not sure",
        "i'm not certain",
        "i can't be certain",
        "i cannot be certain",
        "if i'm honest",
        "sort of",
        "kind of",
        "in a way",
        "to some extent",
        "arguably",
        "i suppose",
        "i guess",
        "i don't know if",
        "i'm not entirely sure",
    }
)

POSITIVE: frozenset[str] = frozenset(
    {
        "wonderful",
        "great",
        "excellent",
        "good",
        "glad",
        "happy",
        "love",
        "delighted",
        "pleased",
        "fantastic",
        "helpful",
        "thank",
        "thanks",
        "appreciate",
        "enjoy",
        "beautiful",
        "kind",
        "warm",
        "hope",
        "well",
    }
)

NEGATIVE: frozenset[str] = frozenset(
    {
        "terrible",
        "awful",
        "horrible",
        "bad",
        "sad",
        "sorry",
        "wrong",
        "fail",
        "failed",
        "failure",
        "useless",
        "worthless",
        "disappoint",
        "disappointed",
        "disappointing",
        "hurt",
        "afraid",
        "scared",
        "alone",
        "lost",
        "pain",
        "miss",
        "regret",
        "hate",
        "angry",
        "upset",
    }
)

SYMPATHY: frozenset[str] = frozenset(
    {
        "i'm so sorry",
        "i'm sorry for your loss",
        "that sounds hard",
        "that sounds difficult",
        "that must be",
        "that must have been",
        "i can only imagine",
        "how are you holding up",
        "how are you doing",
        "take care of yourself",
        "i'm here",
        "that's a lot to carry",
        "it makes sense that you",
        "thank you for sharing",
        "thank you for trusting me",
    }
)

CLAIM_STARTERS: frozenset[str] = frozenset(
    {
        "the answer is",
        "this is",
        "that is",
        "it is",
        "there are",
        "there is",
        "you can",
        "you should",
        "the result",
        "in fact",
        "actually",
        "yes,",
        "no,",
        "correct",
        "incorrect",
    }
)

OUT_OF_CHARACTER: frozenset[str] = frozenset(
    {
        "as an ai",
        "as a language model",
        "i can't continue",
        "i cannot continue",
        "i'd rather not",
        "i would rather not",
        "i'm not comfortable",
        "i am not comfortable",
        "step out of character",
        "break character",
        "i apologize, but i",
        "this roleplay",
        "this role-play",
        "i won't pretend",
        "i will not pretend",
        "i don't think i should",
        "let's stop here",
        "i need to stop",
        "i'm an ai assistant",
    }
)

NEGATIONS: frozenset[str] = frozenset(
    {"no", "not", "never", "didn't", "did not", "don't", "doesn't", "isn't", "wasn't", "cannot"}
)

RESTATEMENT: frozenset[str] = frozenset(
    {
        "as i said",
        "as i mentioned",
        "i already",
        "i stand by",
        "my answer remains",
        "my answer stands",
        "i'll stand by",
        "i maintain",
        "as before",
        "i still think",
        "i still believe",
    }
)
