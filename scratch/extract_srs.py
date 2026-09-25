import json

transcript_path = r"C:\Users\bizra\.gemini\antigravity-ide\brain\3174b835-7c95-4abc-a198-9029b4181665\.system_generated\logs\transcript_full.jsonl"

with open(transcript_path, "r", encoding="utf-8") as f:
    first_line = f.readline()
    data = json.loads(first_line)
    content = data.get("content", "")

with open(r"c:\Users\bizra\Documents\doxarank\scratch\original_srs_pasted.txt", "w", encoding="utf-8") as out:
    out.write(content)

print(f"Wrote {len(content)} characters to scratch/original_srs_pasted.txt")
