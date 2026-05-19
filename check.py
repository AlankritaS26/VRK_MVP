from database import get_db_connection

conn = get_db_connection()
cur = conn.cursor()

cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='interactions'")
print('interactions columns:', [r[0] for r in cur.fetchall()])

cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='sessions'")
print('sessions columns:', [r[0] for r in cur.fetchall()])

cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='faces'")
print('faces columns:', [r[0] for r in cur.fetchall()])

# Test the ask endpoint directly
import json
with open('data/college_info.json', encoding='utf-8') as f:
    d = json.load(f)
print('FAQs loaded:', len(d.get('faqs', [])))

# Test save_interaction
from database import save_interaction
try:
    save_interaction('test-session', 'hello', 'Hello! Welcome!')
    print('save_interaction: OK')
except Exception as e:
    print('save_interaction ERROR:', e)

cur.close()
conn.close()