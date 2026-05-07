import os                   #allows us to read password from database from env file
import json  # Added this to handle your JSON file
from fastapi import FastAPI ,Query        #turns code into web server which can send and receive data
from dotenv import load_dotenv      #allows us to read password from database
import redis            #drivers that allow python talk to redis and postresql
#import psycopg2
from database import get_db_connection, init_db
from memory import set_context, get_context


# 1. Load the "secret" URLs from your .env file
load_dotenv()
# 2. Initialize the database table (Permanent Memory)
init_db()
app = FastAPI() #creates actual instance of web application
# --- NEW: Helper function to read your RNSIT data ---
def load_college_data():
    with open("data/college_info.json", "r") as f:
        return json.load(f)

# 2. Setup Connections(connects two storage system)
try:
    # Connect to Memurai (Live Memory)
    r = redis.from_url(os.getenv("REDIS_URL"),decode_responses=True)
    
    # Connect to PostgreSQL (Permanent Memory)
    conn = get_db_connection()
    if conn and r:
       print(" Both databases connected successfully!")
except Exception as e:
    print(f" Connection Error: {e}")

@app.get("/") #tells server when someone visit home page address(/)run this function
def home():
    return {
        "status": "RNSIT Kiosk Backend is Live",
         "database": "Connected"
         } #sends back  json response
@app.get("/test-memory/{name}")
def test_memory(name: str):
    # This registers the student's name in Redis for 60 seconds
    set_context("guest", "name", name, expiry=60)
    return {"message": f"I will remember you for 60 seconds, {name}!"}

# --- The "Brain" of the Kiosk ---
@app.get("/ask")
def ask_kiosk(question: str = Query(..., description="The student's question")):
    user_name = get_context("guest", "name")
    greeting = f"Hello {user_name}! " if user_name else ""

    data = load_college_data()
    question_lower = question.lower()
    
    # List of "filler words" to ignore
    stop_words = ["is", "the", "where", "can", "you", "tell", "me", "who", "what", "how", "of", "in", "at", "a", "an"]
    
    # Extract important keywords from the user's sentence
    query_words = [w for w in question_lower.split() if w not in stop_words]
    
    answer = None

    # 1. Improved Logic: Match based on Keyword Overlap
    best_match_score = 0
    
    for faq in data.get("faqs", []):
        faq_q_lower = faq["q"].lower()
        # Count how many of our query keywords are in this specific FAQ question
        score = sum(1 for word in query_words if word in faq_q_lower)
        
        if score > best_match_score:
            best_match_score = score
            answer = faq["a"]

    # 2. If score is too low, check Blocks or Departments
    if best_match_score < 1:
        # Check Blocks
        for block_key, desc in data.get("blocks", {}).items():
            clean_block = block_key.replace("_", " ")
            if any(word in clean_block for word in query_words):
                answer = desc
                break
       # Check Departments
        if not answer:
            for dept_key, details in data.get("departments", {}).items():
                dept_name_clean = dept_key.replace("_", " ")
                
                # Check if the user is mentioning this department (e.g., "CSE" or "Computer Science")
                if dept_name_clean in question_lower or dept_key in question_lower:
                    
                    # Intent 1: Intake/Seats
                    if any(word in question_lower for word in ["intake", "seats", "capacity", "how many"]):
                        answer = f"The {dept_name_clean.upper()} department has an annual intake of {details.get('intake', '180')} students."
                    
                    # Intent 2: HOD
                    elif any(word in question_lower for word in ["hod", "head", "boss", "chairman"]):
                        answer = f"The HOD of {dept_name_clean.upper()} is {details.get('hod', 'not listed')}."
                    
                    # Intent 3: Location (Default)
                    else:
                        answer = f"The {dept_name_clean.upper()} department is located on the {details.get('floor', 'ground floor')}."
                    break

    # Final Fallback
    if not answer:
        answer = "I'm sorry, I don't have that information yet. Please visit the Admin Block."

    # Log to PostgreSQL (Keep your existing logging code here)
    try:
        db_conn = get_db_connection()
        cur = db_conn.cursor()
        cur.execute(
            "INSERT INTO interactions (input_text, response_text) VALUES (%s, %s)",
            (str(question), str(answer))
        )
        db_conn.commit()
        cur.close()
        db_conn.close()
    except Exception as e:
        print(f"⚠️ Database logging failed: {e}")

    return {"question": question, "answer": f"{greeting}{answer}"}
