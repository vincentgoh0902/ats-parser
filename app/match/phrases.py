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


def candidates(text: str) -> list[list[str]]:
    out = []
    for chunk in SPLIT_RE.split(text):
        run = []
        for tok in TOKEN_RE.findall(chunk):
            if tok.lower() in STOPWORDS or tok.isdigit():
                if run:
                    out.append(run)
                run = []
            else:
                run.append(tok)
        if run:
            out.append(run)
    return [c for c in out if len(c) <= MAX_WORDS]


def extract(text: str, limit: int = 10) -> list[dict]:
    """Top phrases by RAKE score. The caller drops those overlapping known skills."""
    cands = candidates(text)
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
