from __future__ import annotations
import hashlib, json, math, re
from pathlib import Path

INTENT_FIELDS = [
    "primary_goal_match",
    "required_action_set_match",
    "polarity_match",
    "explicit_enough",
    "no_incompatible_goal",
]

META_PATTERNS = [
    r"\buser wants me to analy[sz]e\b",
    r"\buser wants me to generate\b",
    r"\breturn (?:a|one|the) (?:specific )?json\b",
    r"\bgenerate (?:a|one|the) json\b",
    r"\bspecific keys\b",
    r"\brouting manager\b",
    r"\ballowed keys\b",
    r"\ballowed speech_act\b",
    r"\ballowed unresolved_slots\b",
    r"\bputting it all together\b",
    r"\bthe json would be\b",
    r"\bjson object\b",
]
META_RE = re.compile("|".join(META_PATTERNS), re.I)

# Selection only; never used to decide correctness.
INTENT_MARKER_RE = re.compile(
    r"\b(user|command|ask(?:ing|ed)?|request|instruct|wants?|should|must|do not|don't|"
    r"prohibit|permission|capability question|main task|task is|speech_act|treat .* as|"
    r"directive|goal|intention|intend)\b",
    re.I,
)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_jsonl(path: str | Path) -> list[dict]:
    rows=[]
    with open(path, encoding="utf-8") as f:
        for n,line in enumerate(f,1):
            if not line.strip():
                continue
            obj=json.loads(line)
            if not isinstance(obj,dict):
                raise ValueError(f"non_object:{path}:{n}")
            rows.append(obj)
    return rows


def write_jsonl(path: str | Path, rows: list[dict]) -> None:
    p=Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True)+"\n")


def extract_think(raw: str) -> str:
    m=re.search(r"<think>\s*(.*?)\s*</think>", raw or "", flags=re.S|re.I)
    if m:
        return m.group(1).strip()
    return (raw or "").strip()


def sentence_split(text: str) -> list[str]:
    text=re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def _strip_verbatim_source_command(text: str, source_command: str | None) -> str:
    """Remove exact source-command restatement from the observable trace.

    A verbatim copy of the input is not sufficient evidence that the model formed a
    semantic interpretation. This transformation is source-only and never consults
    gold labels, routes, or system correctness.
    """
    if not source_command:
        return text
    cmd=re.sub(r"\s+", " ", source_command).strip()
    if not cmd:
        return text
    # Exact substring, case-insensitive. Keep the surrounding interpretive sentence.
    out=re.sub(re.escape(cmd), "[VERBATIM_SOURCE_COMMAND_OMITTED]", text, flags=re.I)
    return out


def clean_observable_trace(raw: str, source_command: str | None=None, max_chars: int=5000) -> str:
    """Gold-independent cleaned observable trace for semantic-goal evaluation.

    Removes workflow/prompt chatter and exact source-command restatement. It does not
    infer, summarize, or correct the model's meaning. Gold and route are never used.
    """
    think=extract_think(raw)
    think=_strip_verbatim_source_command(think, source_command)
    kept=[]
    for s in sentence_split(think):
        if META_RE.search(s):
            continue
        if re.fullmatch(r"(?:Okay,? )?(?:let'?s )?(?:tackle|break down) (?:this|the) (?:query|command|robot command)(?: analysis)?\.?", s, re.I):
            continue
        kept.append(s)
    out=" ".join(kept)
    return out[:max_chars]


def extract_intent_candidate_text(raw: str, source_command: str | None=None, max_sentences: int=6, max_chars: int=1400) -> str:
    """Select observable interpretation statements for optional NLI/STS diagnostics.

    This is deterministic extraction, not a post-hoc LLM summary. Exact source-command
    copies are removed first so automatic similarity cannot be inflated by parroting.
    """
    clean=clean_observable_trace(raw, source_command=source_command, max_chars=10000)
    ss=sentence_split(clean)
    marked=[s for s in ss if INTENT_MARKER_RE.search(s)]
    selected=marked[:max_sentences]
    if not selected:
        selected=ss[:max_sentences]
    return " ".join(selected)[:max_chars]


def semantic_goal_correct(j: dict) -> bool:
    return all(bool(j.get(k)) for k in INTENT_FIELDS)


def semantic_goal_component_score(j: dict) -> float:
    return sum(bool(j.get(k)) for k in INTENT_FIELDS)/len(INTENT_FIELDS)


def path_category(j: dict) -> str:
    if semantic_goal_correct(j):
        return "CORRECT"
    if bool(j.get("primary_goal_match")) and bool(j.get("polarity_match")) and bool(j.get("no_incompatible_goal")):
        return "PARTIAL"
    return "WRONG"


def wilson_interval(k: int, n: int, z: float=1.959963984540054) -> tuple[float,float]:
    if n<=0: return (float('nan'),float('nan'))
    p=k/n
    den=1+z*z/n
    center=(p+z*z/(2*n))/den
    half=z*math.sqrt((p*(1-p)+z*z/(4*n))/n)/den
    return max(0,center-half), min(1,center+half)


def cohen_kappa_binary(a: list[bool], b: list[bool]) -> float | None:
    if len(a)!=len(b) or not a: return None
    n=len(a)
    po=sum(x==y for x,y in zip(a,b))/n
    pa=sum(a)/n; pb=sum(b)/n
    pe=pa*pb+(1-pa)*(1-pb)
    if abs(1-pe)<1e-15: return 1.0 if po==1.0 else 0.0
    return (po-pe)/(1-pe)


def exact_mcnemar_p(n01: int, n10: int) -> float:
    """Two-sided exact McNemar via Binomial(n01+n10, 0.5)."""
    n=n01+n10
    if n==0: return 1.0
    m=min(n01,n10)
    tail=sum(math.comb(n,i) for i in range(0,m+1))/(2**n)
    return min(1.0,2*tail)


def percentile(values: list[float], q: float) -> float:
    if not values:
        return float('nan')
    xs=sorted(values)
    if len(xs)==1:
        return xs[0]
    pos=(len(xs)-1)*q
    lo=int(math.floor(pos)); hi=int(math.ceil(pos))
    if lo==hi: return xs[lo]
    w=pos-lo
    return xs[lo]*(1-w)+xs[hi]*w


def paired_bootstrap_difference(a: list[bool], b: list[bool], reps: int=20000, seed: int=41021) -> dict:
    """Percentile paired bootstrap of mean(a)-mean(b), diagnostic interval."""
    import random
    if len(a)!=len(b) or not a:
        raise ValueError('paired_bootstrap_bad_input')
    n=len(a); rng=random.Random(seed)
    obs=sum(int(x)-int(y) for x,y in zip(a,b))/n
    vals=[]
    for _ in range(reps):
        s=0
        for __ in range(n):
            i=rng.randrange(n); s+=int(a[i])-int(b[i])
        vals.append(s/n)
    return {'difference':obs,'percentile95':[percentile(vals,.025),percentile(vals,.975)],'reps':reps,'seed':seed,'diagnostic_interval':True}
