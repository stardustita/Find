from __future__ import annotations
import re
from .base import Agent
STOP={"the","a","an","of","and","in","to","is","for","on","with","coin","token"}
BUZZ=("ai","agent","trump","elon","cat","dog","frog","pepe","brain","cyber","moon","banana","chill","wif","hat","girl","baby","grok","fire","king")
class NarrativeAgent(Agent):
    name="narrative"
    def __init__(self, settings=None, store=None, enricher=None): self.s=settings; self.store=store; self.enr=enricher
    def features(self, st):
        meta=st.meta or {}; name=(st.name or "").strip(); sym=(st.symbol or "").strip(); desc=meta.get("description") or ""
        words=[w for w in re.findall(r"[a-z]+", (name+" "+desc).lower()) if w not in STOP and len(w)>2]
        buzz=sum(1 for w in set(words) if any(b in w for b in BUZZ))
        sym_ok=1.0 if 2<=len(sym)<=9 and re.fullmatch(r"[A-Za-z0-9_]+", sym or "") else 0.0
        pen=0.0
        if sym:
            letters=sym.lower(); vowels=sum(1 for c in letters if c in "aeiou")
            if vowels==0 or vowels/len(letters)<0.15: pen=1.0
        social=(1.0 if meta.get("twitter") else 0.0)+(0.6 if meta.get("telegram") else 0.0)+(0.3 if meta.get("website") else 0.0)
        return {"nar_social_score":min(1.0,social/1.9),"nar_has_twitter":1.0 if meta.get("twitter") else 0.0,
                "nar_has_telegram":1.0 if meta.get("telegram") else 0.0,"nar_desc_len":min(len(desc),600),
                "nar_desc_word_cnt":len(words),"nar_buzz_hits":buzz,"nar_symbol_ok":sym_ok,
                "nar_symbol_random_pen":pen,"nar_name_len":len(name),"nar_image_reuse":meta.get("image_reuse",0) or 0,
                "nar_llm_score":(st.narrative or {}).get("llm_score",-1.0)}
