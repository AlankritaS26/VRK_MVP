import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

def get_db_connection():
    try:
        conn = psycopg2.connect(os.getenv("DATABASE_URL"))
        return conn
    except Exception as e:
        print(f"Database Connection Error: {e}")
        return None

def init_db():
    conn = get_db_connection()
    if conn:
        cur = conn.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS interactions (
                id SERIAL PRIMARY KEY,
                session_id VARCHAR(50),
                input_text TEXT,
                response_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS faces (
                id SERIAL PRIMARY KEY,
                face_id VARCHAR(50) UNIQUE NOT NULL,
                name VARCHAR(100) NOT NULL,
                label_int INTEGER UNIQUE NOT NULL,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                visit_count INTEGER DEFAULT 1
            );
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id SERIAL PRIMARY KEY,
                session_id VARCHAR(50) UNIQUE NOT NULL,
                face_id VARCHAR(50) REFERENCES faces(face_id) ON DELETE SET NULL,
                user_name VARCHAR(100),
                is_returning BOOLEAN DEFAULT FALSE,
                visit_count INTEGER DEFAULT 1,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ended_at TIMESTAMP
            );
        ''')
        conn.commit()
        cur.close()
        conn.close()
        print("PostgreSQL: all tables ready.")

def get_all_faces():
    conn = get_db_connection()
    if not conn: return {}
    try:
        cur = conn.cursor()
        cur.execute("SELECT label_int, face_id, name, registered_at, last_seen, visit_count FROM faces")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        result = {}
        for row in rows:
            result[row[0]] = {
                "face_id":     row[1],
                "name":        row[2],
                "registered":  str(row[3]),
                "last_seen":   str(row[4]),
                "visit_count": row[5]
            }
        return result
    except Exception as e:
        print(f"get_all_faces error: {e}")
        return {}

def save_face(label_int, face_id, name):
    conn = get_db_connection()
    if not conn: return
    try:
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO faces (label_int, face_id, name)
            VALUES (%s, %s, %s)
            ON CONFLICT (face_id) DO UPDATE
            SET name = EXCLUDED.name, last_seen = CURRENT_TIMESTAMP
        ''', (label_int, face_id, name))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"save_face error: {e}")

def update_face_seen(face_id):
    conn = get_db_connection()
    if not conn: return
    try:
        cur = conn.cursor()
        cur.execute('''
            UPDATE faces
            SET last_seen = CURRENT_TIMESTAMP, visit_count = visit_count + 1
            WHERE face_id = %s
        ''', (face_id,))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"update_face_seen error: {e}")

def get_face_by_id(face_id):
    conn = get_db_connection()
    if not conn: return None
    try:
        cur = conn.cursor()
        cur.execute("SELECT face_id, name, label_int, visit_count FROM faces WHERE face_id = %s", (face_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            return {"face_id": row[0], "name": row[1], "label_int": row[2], "visit_count": row[3]}
        return None
    except Exception as e:
        print(f"get_face_by_id error: {e}")
        return None

def delete_face_by_name(name):
    conn = get_db_connection()
    if not conn: return False
    try:
        cur = conn.cursor()
        cur.execute("SELECT face_id FROM faces WHERE LOWER(name) = LOWER(%s)", (name,))
        rows = cur.fetchall()
        if not rows:
            cur.close()
            conn.close()
            return False
        cur.execute("DELETE FROM faces WHERE LOWER(name) = LOWER(%s)", (name,))
        conn.commit()
        cur.close()
        conn.close()
        return [r[0] for r in rows]
    except Exception as e:
        print(f"delete_face error: {e}")
        return False

def get_next_label_int():
    conn = get_db_connection()
    if not conn: return 0
    try:
        cur = conn.cursor()
        cur.execute("SELECT COALESCE(MAX(label_int), -1) + 1 FROM faces")
        result = cur.fetchone()[0]
        cur.close()
        conn.close()
        return result
    except Exception as e:
        print(f"get_next_label_int error: {e}")
        return 0

def save_session(session_id, face_id, user_name, is_returning, visit_count):
    conn = get_db_connection()
    if not conn: return
    try:
        cur = conn.cursor()
        # Use None instead of empty string for face_id to avoid FK constraint failure
        fid = face_id if face_id and face_id.strip() else None
        cur.execute('''
            INSERT INTO sessions (session_id, face_id, user_name, is_returning, visit_count)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (session_id) DO UPDATE
            SET visit_count = EXCLUDED.visit_count,
                is_returning = EXCLUDED.is_returning,
                user_name = EXCLUDED.user_name,
                ended_at = NULL
        ''', (session_id, fid, user_name, is_returning, visit_count))
        conn.commit()
        cur.close()
        conn.close()
        print(f"[DB] Session saved/updated: {session_id} user={user_name}")
    except Exception as e:
        print(f"save_session error: {e}")

def end_session(session_id):
    conn = get_db_connection()
    if not conn: return
    try:
        cur = conn.cursor()
        cur.execute("UPDATE sessions SET ended_at = CURRENT_TIMESTAMP WHERE session_id = %s", (session_id,))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"end_session error: {e}")

def save_interaction(session_id, question, answer):
    conn = get_db_connection()
    if not conn: return
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO interactions (session_id, input_text, response_text) VALUES (%s, %s, %s)",
            (session_id, question, answer)
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"save_interaction error: {e}")
def save_face_image(face_id, image_index, image_bytes):
    conn = get_db_connection()
    if not conn: return
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO face_images (face_id, image_index, image_data) VALUES (%s, %s, %s)",
            (face_id, image_index, psycopg2.Binary(image_bytes))
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"save_face_image error: {e}")

def load_face_images(face_id):
    conn = get_db_connection()
    if not conn: return []
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT image_data FROM face_images WHERE face_id = %s ORDER BY image_index",
            (face_id,)
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [bytes(row[0]) for row in rows]
    except Exception as e:
        print(f"load_face_images error: {e}")
        return []

def delete_face_images(face_id):
    conn = get_db_connection()
    if not conn: return
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM face_images WHERE face_id = %s", (face_id,))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"delete_face_images error: {e}")
        
def get_admission_fee_by_branch(search_term: str):
    """Searches the management fees table for a specific branch matching keywords."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Using ILIKE for case-insensitive partial matching
        query = """
            SELECT branch_full_name, annual_fee, instalment_1, instalment_2 
            FROM public.management_program_fees 
            WHERE LOWER(branch_full_name) LIKE %s OR LOWER(branch_code) LIKE %s;
        """
        cursor.execute(query, (f"%{search_term}%", f"%{search_term}%"))
        return cursor.fetchone() # Returns a single row if found
    except Exception as e:
        print(f"Error querying management fees: {e}")
        return None
    finally:
        cursor.close()
        conn.close()

def get_admission_requirements(quota_type: str):
    """Fetches all mandatory documents required for a specific entry quota."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        query = """
            SELECT document_name, copies_required 
            FROM public.admission_requirements 
            WHERE LOWER(quota_type) = LOWER(%s);
        """
        cursor.execute(query, (quota_type,))
        return cursor.fetchall() # Returns list of document tuples
    except Exception as e:
        print(f"Error querying requirements: {e}")
        return []
    finally:
        cursor.close()
        conn.close()
