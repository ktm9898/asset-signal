import os
import json

transcript_path = r'C:\Users\행복한 우리집\.gemini\antigravity-ide\brain\0b76fb01-ee5b-4a9f-a0b6-a5bb66cbbefe\.system_generated\logs\transcript.jsonl'

if os.path.exists(transcript_path):
    with open(transcript_path, 'r', encoding='utf-8', errors='ignore') as f:
        for i, line in enumerate(f):
            if 'QQQ' in line and 'SCHD' in line and '40' in line and '60' in line:
                try:
                    obj = json.loads(line)
                    content = str(obj.get('content', ''))
                    if 'QQQ' in content or 'dropStages' in content:
                        print(f"--- Line {i} ---")
                        print(content[:500])
                except:
                    pass
