import glob
import json
import os

brain_dir = r"C:\Users\bizra\.gemini\antigravity-ide\brain"
files = glob.glob(os.path.join(brain_dir, "*", ".system_generated", "logs", "transcript*.jsonl"))

terms = ["pagespeed", "broken link", "serp snippet", "fidel"]

results = []
for fpath in files:
    try:
        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
            for lno, line in enumerate(f):
                lower = line.lower()
                for term in terms:
                    if term in lower:
                        conv = fpath.split(os.sep)[-4]
                        data = json.loads(line)
                        src = data.get("source", "")
                        t = data.get("type", "")
                        c = data.get("content", "")
                        results.append((conv, lno, src, t, term, len(c)))
                        break
    except Exception:
        pass

print(f"Total occurrences: {len(results)}")
for r in results:
    print(r)
