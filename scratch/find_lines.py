import json

with open(r'C:\Users\bizra\.gemini\antigravity-ide\brain\3174b835-7c95-4abc-a198-9029b4181665\.system_generated\logs\transcript_full.jsonl', 'r', encoding='utf-8') as f:
    for idx, line in enumerate(f):
        if 'SERP snippet' in line or 'SERP Snippet' in line or 'serp snippet' in line:
            data = json.loads(line)
            role = data.get('source', '')
            t = data.get('type', '')
            content = data.get('content', '')
            print(f'Line {idx}: role={role}, type={t}, len={len(content)}')
