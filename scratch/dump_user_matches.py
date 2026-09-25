import glob
import json
import os

brain_dir = r"C:\Users\bizra\.gemini\antigravity-ide\brain"
files = glob.glob(os.path.join(brain_dir, "*", ".system_generated", "logs", "transcript*.jsonl"))

keywords = ["serp snippet", "pagespeed", "broken link", "amharic fidel", "original srs", "original doxarank srs"]

matches = []

for fpath in files:
    try:
        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
            for lno, line in enumerate(f):
                if '"USER_INPUT"' in line:
                    lower = line.lower()
                    for kw in keywords:
                        if kw in lower:
                            conv = fpath.split(os.sep)[-4]
                            data = json.loads(line)
                            content = data.get("content", "")
                            matches.append((conv, kw, fpath, lno, content))
                            break
    except Exception as e:
        pass

out_path = r"c:\Users\bizra\Documents\doxarank\scratch\all_user_matches.txt"
with open(out_path, "w", encoding="utf-8") as out:
    out.write(f"Total matches: {len(matches)}\n")
    for conv, kw, fpath, lno, content in matches:
        out.write(f"\n{'='*70}\nCONV: {conv} | KW: {kw} | File: {fpath} | Line: {lno}\n{'='*70}\n")
        out.write(content + "\n")

print(f"Wrote {len(matches)} matches to {out_path}")
