import psycopg2 #allowing language to send sql commands to server
import os
from dotenv import load_dotenv

load_dotenv() #ensure script can see the database url stored in env file without typing password direcly into code

def get_db_connection(): #(helper function)instead of writing connection code everythime just call get_db
    """Returns a connection to the PostgreSQL database."""
    try: #if postgresql server is down,prevents system from crashing
        conn = psycopg2.connect(os.getenv("DATABASE_URL"))
        return conn
    except Exception as e:
        print(f" Database Connection Error: {e}")
        return None

def init_db():
    """Sets up the table to log Kiosk interactions."""
    conn = get_db_connection()
    if conn:
        cur = conn.cursor() #tells db where to execute the command
        # Create a table for conversation logs - vital for your 'Proof of Work'
        cur.execute('''
            CREATE TABLE IF NOT EXISTS interactions ( 
                id SERIAL PRIMARY KEY,
                input_text TEXT,
                response_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''') #if table is not there it builds it
        conn.commit() #like hitting save,without it table wont be created on disk
        cur.close()
        conn.close()
        print("PostgreSQL: 'interactions' table is ready.")