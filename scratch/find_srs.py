import glob
import json
import os

brain_dir = r"C:\Users\bizra\.gemini\antigravity-ide\brain"
files = glob.glob(os.path.join(brain_dir, "*", ".system_generated", "logs", "transcript*.jsonl"))
print(f"Found {len(files)} transcript files")

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
                            pos = content.lower().find(kw)
                            matches.append((conv, kw, fpath, lno, content))
                            break
    except Exception as e:
        pass

print(f"Total user inputs found: {len(matches)}")
for conv, kw, fpath, lno, content in matches:
    print(f"\n=== CONV: {conv} (kw: {kw}) ===")
    print(f"File: {fpath} (line {lno})")
    print(content[:1500])
    if len(content) > 1500:
        print("...\n" + content[1500:3000])
    if len(content) > 3000:
        print("...\n" + content[3000:5000])
