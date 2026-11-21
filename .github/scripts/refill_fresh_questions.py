#!/usr/bin/env python3
"""Generate original Odia CPET MCQs into a public, downloadable pool.
AI-generated practice, NOT verified previous-year questions. No user data sent.
"""
import datetime as dt
import difflib
import hashlib
import json
import os
import random
import re
import time
import unicodedata
import urllib.request
import urllib.error
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "fresh-questions" / "odia-ai-v1.json"
TOPICS = [
    ("ANCIENT_MEDIEVAL", "Sarala Das, Panchasakha, ancient and medieval Odia literature"),
    ("MODERN_POETRY", "Radhanath Ray, Gangadhar Meher, Madhusudan Rao, modern Odia poetry"),
    ("PROSE_DRAMA", "Fakir Mohan Senapati, Gopinath Mohanty, Odia novels, short stories, drama"),
    ("GRAMMAR_LINGUISTICS", "Odia grammar, sandhi, samasa, cases, linguistics, orthography"),
    ("LITERARY_CRITICISM", "Rasa, dhvani, rhetoric, literary theory, Sanskrit/Western criticism"),
]
API = "https://text.pollinations.ai/openai"
OVH = "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/chat/completions"
LIMIT = int(os.environ.get("TARGET_QUESTIONS", "150"))
ATTEMPTS = int(os.environ.get("MAX_REQUESTS", "25"))
PAUSE = float(os.environ.get("PAUSE_SECONDS", "13"))

def canon(s):
    s = unicodedata.normalize("NFKC",str(s)).lower()
    s = re.sub(r"\(?\s*(?:ପ୍ରଶ୍ନ|question)\s*[0-9୦-୯]+\s*\)?", "", s)
    return re.sub(r"[\W_]+", "", s, flags=re.UNICODE)

def similar(a,b):
    ca,cb=canon(a),canon(b)
    if not ca or not cb:
        return False
    if ca == cb:
        return True
    if min(len(ca),len(cb)) < 12:
        return False
    # Minimize changing answer order as a superficial 'new' question.
    return difflib.SequenceMatcher(None, ca, cb).ratio() >= 0.89

def valid(q,topic):
    if not isinstance(q,dict):
        return None
    stem = str(q.get("stem") or q.get("question") or "").strip()
    stem = re.sub(r"\s*[\(（]\s*(?:ପ୍ରଶ୍ନ|question)\s*[0-9୦-୯]+\s*[\)）]\s*", " ", stem, flags=re.I).strip()
    options=q.get("options")
    index=q.get("correctIndex")
    if type(index) is not int or index not in range(4):
        return None
    if not isinstance(options,list) or len(options)!=4:
        return None
    opts=[str(o).strip() for o in options]
    if len(stem)<12 or len(stem)>450 or not any("\u0b00"<=c<="\u0b7f" for c in stem):
        return None
    if any(len(o)<2 or len(o)>190 for o in opts):
        return None
    if len({canon(x) for x in opts})!=4:
        return None
    explanation=str(q.get("explanation") or "").strip()
    if not explanation or len(explanation)>700:
        return None
    item={
        "id":"ai-"+hashlib.sha256(canon(stem).encode()).hexdigest()[:20],
        "topicKey":topic,
        "stem":stem,
        "options":opts,
        "correctIndex":index,
        "explanation":explanation,
        "topicTag":str(q.get("topicTag") or "Odia CPET")[:100],
    }
    return item

def parse_answer(raw):
    answer = json.loads(raw)["choices"][0]["message"].get("content","")
    if isinstance(answer,list):
        answer="".join(p.get("text","") for p in answer if isinstance(p,dict))
    if not isinstance(answer,str):
        return []
    begin,end=answer.find("{"),answer.rfind("}")
    if begin<0 or end<=begin:
        return []
    try:
        body=json.loads(answer[begin:end+1])
    except json.JSONDecodeError:
        return []
    items=body.get("questions",[])
    return items if isinstance(items,list) else []

def query(topic,focus,provider):
    prompt=(
        f"Produce exactly 10 NEW original multiple-choice questions for Odisha CPET MA Odia, "
        f"on this focused subtopic: {focus}. Difficulty moderate-hard. "
        "Use natural correct Odia script. Use 4 distinct plausible answer choices, "
        "integer correctIndex 0-3, and one-sentence accurate explanation in Odia. "
        "Avoid trivia without verifiable answers and don't invent names or titles. "
        'Respond ONLY as JSON {"questions":[{"stem":"...",'
        '"options":["...","...","...","..."],"correctIndex":0,'
        '"explanation":"...","topicTag":"..."}]}. '
        f"Select diverse syllabus facts. Request ID={uuid.uuid4().hex}."
    )
    base={"messages":[{"role":"system","content":"Output JSON only; no Markdown."},
          {"role":"user","content":prompt}],
          "stream":False,"temperature":0.7,"max_tokens":6000,
          "model":"openai" if provider=="pollinations" else "Meta-Llama-3_3-70B-Instruct"}
    endpoint=API if provider=="pollinations" else OVH
    req=urllib.request.Request(endpoint,json.dumps(base).encode("utf-8"),
        headers={"Content-Type":"application/json","Accept":"application/json","User-Agent":"JyotiAcademyQuestionPool/1.0"})
    with urllib.request.urlopen(req,timeout=70) as result:
        return parse_answer(result.read(300000).decode("utf-8"))

def main():
    OUT.parent.mkdir(parents=True,exist_ok=True)
    current=json.loads(OUT.read_text()) if OUT.exists() else {"version":1,"questions":[]}
    saved=list(current.get("questions",[]))
    seen=[x["stem"] for x in saved]
    print("Already stored",len(saved),"questions")
    total_new=0
    for i in range(ATTEMPTS):
        if len(saved)>=LIMIT:
            break
        topic,focus=TOPICS[i%len(TOPICS)]
        providers=["pollinations","ovh"] if i%4 != 3 else ["ovh","pollinations"]
        questions=None
        for provider in providers:
            try:
                questions=query(topic,focus,provider)
                print(i,provider, "returned",len(questions))
                if questions:
                    break
            except urllib.error.HTTPError as exc:
                print(i,provider,"HTTP",exc.code)
                if exc.code==429:
                    time.sleep(8)
            except Exception as exc:
                print(i,provider, type(exc).__name__,str(exc)[:120])
        if questions:
            got=0
            for q in questions:
                candidate=valid(q,topic)
                if candidate is None or any(similar(candidate["stem"],s) for s in seen):
                    continue
                saved.append(candidate)
                seen.append(candidate["stem"])
                got+=1
            total_new+=got
            print("Accepted",got,"total",len(saved))
        if i+1<ATTEMPTS:
            time.sleep(PAUSE)
    payload={
        "version":1,
        "kind":"ai_generated_original_practice_not_pyq",
        "updatedAt":dt.datetime.now(dt.timezone.utc).isoformat(),
        "count":len(saved),
        "questions":saved[:4000],
    }
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n")
    print("New unique questions this run:",total_new,"total:",len(saved))
    if not saved:
        raise SystemExit("No valid AI questions yet. The workflow can retry later.")

if __name__=="__main__":
    main()
