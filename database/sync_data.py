import firebase_admin
from firebase_admin import credentials, firestore
from firebase_admin.firestore import client as FirestoreClient
from DB_manager import DBManager
import time
from datetime import datetime
import logging

# --- Configuration ---
# IMPORTANT: Update this path to your actual service account key file
SERVICE_ACCOUNT_KEY_PATH = "../secret/carbide-ego-364204-08d4ce68b592.json" 
# Use the updated DBManager
DB = DBManager("main.db")
LOG_FILE = "sync.log"

logging.basicConfig(filename=LOG_FILE, level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

def initialize_firebase():
    """Initializes Firebase Admin SDK."""
    try:
        cred = credentials.Certificate(SERVICE_ACCOUNT_KEY_PATH)
        firebase_admin.initialize_app(cred)
        return firestore.client()
    except FileNotFoundError:
        logging.error(f"Service account key not found at: {SERVICE_ACCOUNT_KEY_PATH}")
        print("ERROR: Service account key not found. Check SERVICE_ACCOUNT_KEY_PATH.")
        return None
    except Exception as e:
        logging.error(f"Firebase initialization error: {e}")
        return None

def fetch_users_from_firestore(db):
    """Retrieves all documents from the Users collection."""
    logging.info("Starting Firestore user data pull.")
    users_data = []
    
    try:
        # Get a reference to the 'Users' collection
        users_ref = db.collection('Users')
        
        # Fetch all documents in the collection
        docs = users_ref.stream()
        
        for doc in docs:
            Line_uid = doc.id
            data = doc.to_dict()
            
            # Map Firestore data to SQLite structure
            sqlite_user_data = {
                "user_id": data.get("user_id", ""),
                "cname": data.get("cname", ""),
                "cpass": data.get("cpass", ""),
                "Line_uid": Line_uid
            }
            users_data.append(sqlite_user_data)
            
        logging.info(f"Successfully retrieved {len(users_data)} users from Firestore.")
        return users_data
        
    except Exception as e:
        logging.error(f"Error fetching users from Firestore: {e}")
        return []

def sync_users_to_sqlite(users_data):
    """Updates the local SQLite database with user data."""
    if not users_data:
        logging.info("No user data to sync to SQLite.")
        return
        
    update_count = 0
    for user in users_data:
        try:
            DB.upsert_user(user)
            update_count += 1
        except Exception as e:
            logging.error(f"Error upserting user {user['user_id']} to SQLite: {e}")
            
    DB.commit()
    logging.info(f"Completed SQLite user sync. {update_count} records processed.")

    

def sync_courses_to_firestore(db_firestore: FirestoreClient):
    """Fetches all courses from SQLite and pushes them to the 'Courses' collection in Firestore."""
    logging.info("Starting Firestore course data push.")
    courses = DB.fetch_all_courses_for_sync()
    batch = db_firestore.batch()
    
    for course in courses:
        course_id = course.pop('course_id') # Use course_id as the Document ID
        course_ref = db_firestore.collection('Courses').document(course_id)
        
        # Data structure matches Firestore schema: Courses/{course_id}
        data = {
            'name': course.get('name', ''),
            'courseNumber': course.get('courseNumber', ''),
            'thumbnail': course.get('thumbnail', ''),
            'semester': course.get('semester', '')
        }
        batch.set(course_ref, data, merge=True) # Use merge=True to update existing fields
        
    try:
        batch.commit()
        logging.info(f"Successfully synced {len(courses)} courses to Firestore.")
    except Exception as e:
        logging.error(f"Error committing course batch to Firestore: {e}")

def sync_assignments_to_firestore(db_firestore: FirestoreClient):
    """
    Fetches all user assignments from SQLite and pushes them under 
    Users/{Line_uid}/Assignment/{assignment_id} in Firestore.
    """
    logging.info("Starting Firestore assignment data push.")
    users = DB.fetch_all_users_for_sync()
    total_assignments_synced = 0
    
    for user in users:
        user_id = user['user_id']
        assignments = DB.fetch_user_assignments_for_sync(user_id)
        
        if not assignments:
            continue
            
        # We process assignments in batches per user
        batch = db_firestore.batch()
        user_assignment_collection_ref = db_firestore.collection('Users').document(user['Line_uid']).collection('Assignment')

        for assignment in assignments:
            assignment_id = assignment.pop('assignment_id') # Use assignment_id as the Document ID
            assignment_ref = user_assignment_collection_ref.document(assignment_id)
            
            # Convert ISO string back to Firestore Timestamp object
            due_date_ts = assignment.get("due_date")

                
            # Data structure matches Firestore schema: Users/{Line_uid}/Assignment/{assignment_id}
            data = {
                'due_date': due_date_ts,
                'status': assignment.get('status', 'ASSIGNED'),
                'name': assignment.get('name', 'Untitled Assignment'),
                'course_id': assignment.get('course_id', '')
            }
            batch.set(assignment_ref, data, merge=True)
            total_assignments_synced += 1

        try:
            batch.commit()
        except Exception as e:
            logging.error(f"Error committing assignment batch for user {user_id}: {e}")
            
    logging.info(f"Completed assignment sync. Total {total_assignments_synced} assignments processed.")

def run_pull_sync(db_firestore: FirestoreClient):
    """Main function to run the pull synchronization process."""
    start_time = time.time()
    
    if not db_firestore:
        return
        
    # 1. Fetch data from Firestore
    users_data = fetch_users_from_firestore(db_firestore)
    
    # 2. Sync data to SQLite
    sync_users_to_sqlite(users_data)
    
    end_time = time.time()
    logging.info(f"PULL SYNC FINISHED. Total time: {end_time - start_time:.2f} seconds.")
    
def run_push_sync(db_firestore: FirestoreClient):
    """Main function to run the push synchronization process."""
    start_time = time.time()

    if not db_firestore:
        return
        
    # 1. Sync Course metadata (Global data)
    sync_courses_to_firestore(db_firestore)
    
    # 2. Sync User-specific Assignment data (Nested data)
    sync_assignments_to_firestore(db_firestore)
    
    end_time = time.time()
    logging.info(f"PUSH SYNC FINISHED. Total time: {end_time - start_time:.2f} seconds.")

if __name__ == "__main__":
    db_firestore = initialize_firebase()
    run_push_sync(db_firestore)
    run_pull_sync(db_firestore)
    DB.close()