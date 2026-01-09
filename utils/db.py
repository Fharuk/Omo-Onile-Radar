import sqlite3
import logging
import os
import re
from datetime import datetime
from typing import List, Dict, Any, Optional

# Constants
DB_PATH = os.environ.get('DB_PATH', './omo_onile.db')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def init_db() -> None:
    """
    Initializes the SQLite database and creates the requests table if it doesn't exist.
    
    Idempotent: if table exists, it won't be recreated.
    """
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    phone TEXT NOT NULL,
                    email TEXT NOT NULL,
                    survey_plan_number TEXT,
                    risk_status TEXT DEFAULT 'PENDING',
                    location_text TEXT,
                    status TEXT DEFAULT 'PENDING',
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    notes TEXT
                )
            ''')
            conn.commit()
            logger.info("Database initialized successfully at %s", DB_PATH)
    except sqlite3.Error as e:
        logger.error("Error initializing database: %s", e)
        raise

def save_request(
    name: str, 
    phone: str, 
    email: str, 
    survey_plan_number: Optional[str] = None, 
    risk_status: Optional[str] = None, 
    location_text: Optional[str] = None
) -> Dict[str, Any]:
    """
    Validates inputs and saves a new surveyor verification request to the database.
    
    Args:
        name: Full name of the requester
        phone: Phone number
        email: Email address
        survey_plan_number: Extracted survey plan number
        risk_status: Risk status at time of request (DANGER/CAUTION/SAFE)
        location_text: Location text from survey
        
    Returns:
        Dict with 'success', 'id' (if successful), and 'message'.
    """
    # Validation
    if not name or not name.strip():
        return {'success': False, 'message': 'Full name is required'}
    
    # Simple phone validation: at least 10 digits
    phone_digits = re.sub(r'\D', '', phone)
    if len(phone_digits) < 10:
        return {'success': False, 'message': 'Invalid phone number. Please include at least 10 digits.'}
    
    # Email validation (Simplified RFC 5322)
    email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_regex, email):
        return {'success': False, 'message': 'Invalid email address format.'}

    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO requests (
                    name, phone, email, survey_plan_number, risk_status, location_text
                ) VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                name.strip(), 
                phone.strip(), 
                email.strip(), 
                survey_plan_number, 
                risk_status, 
                location_text
            ))
            request_id = cursor.lastrowid
            conn.commit()
            logger.info("New lead captured: ID %d, Name: %s", request_id, name)
            return {'success': True, 'id': request_id, 'message': 'Request saved'}
    except sqlite3.Error as e:
        logger.error("Error saving request to database: %s", e)
        return {'success': False, 'message': f'Database error: {str(e)}'}

def get_all_requests() -> List[Dict[str, Any]]:
    """
    Retrieves all lead requests from the database.
    
    Returns:
        List of dictionaries containing row data, ordered by newest first.
    """
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM requests ORDER BY timestamp DESC')
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    except sqlite3.Error as e:
        logger.error("Error retrieving requests from database: %s", e)
        return []

def update_request_status(request_id: int, new_status: str, notes: Optional[str] = None) -> Dict[str, Any]:
    """
    Updates the administrative status and notes for a specific request.
    
    Args:
        request_id: The ID of the request to update
        new_status: New status (PENDING, CONTACTED, COMPLETED, REJECTED)
        notes: Optional admin notes
        
    Returns:
        Dict with 'success' and 'message'
    """
    allowed_statuses = ['PENDING', 'CONTACTED', 'COMPLETED', 'REJECTED']
    if new_status not in allowed_statuses:
        return {'success': False, 'message': f'Invalid status. Must be one of {allowed_statuses}'}

    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            if notes is not None:
                cursor.execute('''
                    UPDATE requests 
                    SET status = ?, notes = ?
                    WHERE id = ?
                ''', (new_status, notes, request_id))
            else:
                cursor.execute('''
                    UPDATE requests 
                    SET status = ?
                    WHERE id = ?
                ''', (new_status, request_id))
            
            if cursor.rowcount == 0:
                return {'success': False, 'message': f'Request with ID {request_id} not found'}
                
            conn.commit()
            logger.info("Request %d status updated to %s", request_id, new_status)
            return {'success': True, 'message': 'Status updated successfully'}
    except sqlite3.Error as e:
        logger.error("Error updating request status: %s", e)
        return {'success': False, 'message': f'Database error: {str(e)}'}
