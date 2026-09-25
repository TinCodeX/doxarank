import json

lines_to_check = [0, 171, 769, 788, 790, 875, 958]

with open(r'c:\Users\bizra\Documents\doxarank\scratch\serp_snippets_out.txt', 'w', encoding='utf-8') as out:
    with open(r'C:\Users\bizra\.gemini\antigravity-ide\brain\3174b835-7c95-4abc-a198-9029b4181665\.system_generated\logs\transcript_full.jsonl', 'r', encoding='utf-8') as f:
        for idx, line in enumerate(f):
            if idx in lines_to_check:
                data = json.loads(line)
                content = data.get('content', '')
                if not content and 'tool_calls' in data:
                    content = str(data.get('tool_calls'))
                out.write(f"\n{'='*30} LINE {idx} {'='*30}\n")
                pos = 0
                while True:
                    pos = content.lower().find('serp snippet', pos)
                    if pos == -1:
                        break
                    snippet = content[max(0, pos-150):min(len(content), pos+400)]
                    out.write(f"[{pos}]: {snippet}\n{'-'*40}\n")
                    pos += len('serp snippet') + 50
