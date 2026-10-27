"""Key phrases from a job description that the skills taxonomy doesn't know.

RAKE (Rapid Automatic Keyword Extraction): split the text at stopwords and
punctuation, then score each run of words by how often its words occur
and how many other words they appear with. No model and no corpus.
Job-ad boilerplate ("strong", "ability", "experience") counts as a stopword
so the phrases left are the domain ones: "credit risk", "payments platform".
"""

import re
from collections import Counter, defaultdict

STOPWORDS = set("""
a about above across after again against all also am an and any are as at be because been before
being below between both but by can could did do does doing down during each either etc few for
from further had has have having he her here hers him his how i if in into is it its itself just
like me more most my no nor not of off on once only or other our ours out over own per same she
should so some such than that the their theirs them then there these they this those through to
too under until up us very via was we were what when where which while who whom why will with
within without would you your yours e.g i.e eg ie
ability able experience experienced years year strong excellent good great solid proven
demonstrated deep working work knowledge understanding familiarity familiar proficiency proficient
skills skill including include includes using use used new well related field degree bachelor
bachelors master masters phd equivalent plus preferred required requirement requirements nice
bonus ideally must role team teams company candidate candidates looking join help we're you'll
you're we'll it's they're able hands-on hands track record environment environments opportunity
opportunities responsibilities responsible build building built develop developing design
designing other others etc ensure across within way ways day high-quality quality best practices
practice part make makes making take takes drive driving support supporting closely
another analyse analyze analysing analyzing deploy deploying deliver delivering own owning
collaborate partner partnering write writing create creating maintain maintaining improve
improving scale scaling manage managing lead leading apply applying run running solve solving
define defining identify understand communicate findings end results result impact fast-paced
real similar practical serious famous smarter easier better best great people person someone
everyone anyone believe deserve want need love loves cares care treat turn get gets give find
talk start started expand expanding enable enabling reduce improve worth quickly every day today
just only even really truly around without instead whether things thing something lot lots
able willing passionate passion driven talented highly highlights highlight career careers
problems problem issues challenges reliable robust rather avoid
constrained seamless seamlessly clear core closely
""".split())
SPLIT_RE = re.compile(r"[.,;:!?()\[\]{}\"'“”‘’/|•*·\n]+|\s[-–—]\s|\s+&\s+")
TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#.\-]*[A-Za-z0-9+#]|[A-Za-z]")
MAX_WORDS = 4


def stem(word: str) -> str:
    """A deliberately small stemmer: plurals and common verb endings."""
    w = word.lower()
    for suffix, repl in (("ies", "y"), ("ing", ""), ("ed", ""), ("es", ""), ("s", "")):
        if w.endswith(suffix) and len(w) - len(suffix) >= 3 and not w.endswith("ss"):
            return w[: len(w) - len(suffix)] + repl
    return w


# Verbs that start a duty ("bring small language models", "release models"):
# dropped from the front of a phrase, but not everywhere, since "release
# engineering" or "training data" are real terms.
LEADING_VERBS = {"bring", "contribute", "release", "iterate", "train", "power", "meet", "integrate",
                 "optimize", "optimise", "tune", "ship", "enable", "establish", "implement", "translate",
                 "research", "explore", "evaluate", "monitor", "test", "validate", "document", "automate"}
NEGATORS = {"not", "no", "never", "without", "instead", "rather", "avoid"}
POSSESSIVE_RE = re.compile(r"(?<=\w)['’]s\b")


def is_stop(tok: str, extra: set[str] = frozenset()) -> bool:
    low = tok.lower()
    return low in STOPWORDS or stem(low) in STOPWORDS or low in extra or tok.isdigit()


def candidates(text: str, extra_stop: set[str] = frozenset()) -> list[list[str]]:
    out = []
    # "BJAK's AI app" is one run, not "BJAK" and "s AI app".
    text = POSSESSIVE_RE.sub("", text)
    for chunk in SPLIT_RE.split(text):
        run, negated = [], False
        for tok in TOKEN_RE.findall(chunk):
            if is_stop(tok, extra_stop):
                if run and not negated:
                    out.append(run)
                if run:
                    negated = False
                run = []
                # "not just AI strategy", "instead of demos": what follows isn't wanted.
                if tok.lower() in NEGATORS:
                    negated = True
            else:
                run.append(tok)
        if run and not negated:
            out.append(run)
    out = [c[1:] if len(c) > 1 and c[0].lower() in LEADING_VERBS else c for c in out]
    return [c for c in out if len(c) <= MAX_WORDS]


def extract(text: str, limit: int = 10, extra_stop: set[str] = frozenset()) -> list[dict]:
    """Top phrases by RAKE score. The caller drops those overlapping known skills.
    `extra_stop` holds words to split on as well, such as the company's name."""
    cands = candidates(text, {w.lower() for w in extra_stop})
    freq, degree = Counter(), defaultdict(int)
    for c in cands:
        for w in c:
            freq[w.lower()] += 1
            degree[w.lower()] += len(c) - 1
    scored = {}
    for c in cands:
        phrase = " ".join(c)
        key = " ".join(stem(w) for w in c)
        if key in scored:
            scored[key]["count"] += 1
            continue
        score = sum((degree[w.lower()] + freq[w.lower()]) / freq[w.lower()] for w in c)
        scored[key] = {"phrase": phrase, "key": key, "score": score, "count": 1, "words": len(c)}
    keep = []
    for p in sorted(scored.values(), key=lambda p: (p["score"] * (1 + 0.5 * (p["count"] - 1))), reverse=True):
        # A lone word is only worth reporting if it looks like a named tool.
        if p["words"] == 1 and not re.search(r"[A-Z].*[A-Z]|[0-9+#]|^[A-Z][a-z]+[A-Z]", p["phrase"]):
            continue
        if p["words"] >= 2 and all(len(w) <= 2 for w in p["phrase"].split()):
            continue
        keep.append(p)
        if len(keep) >= limit:
            break
    return keep
