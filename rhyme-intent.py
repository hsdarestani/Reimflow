"""Stable phrase decomposition for the Reimflow phonetic search pipeline.

Preserve the user's exact query, and expose the final word as a SECOND
rhyme target; this is not a spelling-based rhyme classifier.
"""
import re

TOKEN_RE=re.compile(r"[^\W\d_]+(?:['’\-][^\W\d_]+)*",re.UNICODE)

def search_intent(query):
    original=str(query or "").strip()
    tokens=TOKEN_RE.findall(original)
    anchor=tokens[-1] if tokens else original
    prefix=" ".join(tokens[:-1]) if len(tokens)>1 else ""
    return {
        "query_exact":original,
        "end_word":anchor,
        "prefix":prefix,
        "is_phrase":len(tokens)>1,
        "targets":(["full_phrase","end_word","phrase_variation"] if len(tokens)>1 else ["end_word"]),
        "notes":(
            "Analyze the whole phrase AND its final stressed word independently. "
            "Anchor-only matches are useful and MUST be allowed, labeled end_word. "
            "Also construct natural lyric phrases that match full flow; do not invent nonsense."
            if len(tokens)>1 else
            "Match the audible stress-to-end rhyme, not spelling or syllable count."
        )
    }
