with open(r'c:\Users\bizra\Documents\doxarank\scratch\audit_response_3174.md', 'r', encoding='utf-8') as f:
    text = f.read()

keywords = ['### 7. SERP Snippet', '### 8. PageSpeed', '### 9. Single-page', '### 10. Amharic']

with open(r'c:\Users\bizra\Documents\doxarank\scratch\tools_audit_details.txt', 'w', encoding='utf-8') as out:
    for kw in keywords:
        pos = text.find(kw)
        if pos != -1:
            out.write(f"\n{'='*30} {kw} {'='*30}\n")
            out.write(text[pos:pos+1500])
            out.write("\n")
        else:
            out.write(f"NOT FOUND: {kw}\n")
