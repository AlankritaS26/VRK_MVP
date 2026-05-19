from database import get_db_connection

conn = get_db_connection()
cur = conn.cursor()

# Add session_id column if missing
try:
    cur.execute("ALTER TABLE interactions ADD COLUMN IF NOT EXISTS session_id VARCHAR(50)")
    conn.commit()
    print("session_id column added!")
except Exception as e:
    print("session_id:", e)

# Verify
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='interactions'")
print("interactions columns now:", [r[0] for r in cur.fetchall()])

cur.close()
conn.close()