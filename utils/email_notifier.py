"""
Email notification module for lead capture.

This module handles sending email notifications when leads are submitted,
replacing the SQLite database to prevent data loss on server restarts.
"""

import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Dict, Any
from datetime import datetime
import re

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class EmailNotificationError(Exception):
    """Custom exception for email notification errors."""
    pass


def send_lead_notification(
    admin_email: str,
    admin_password: str,
    lead_data: Dict[str, Any],
    smtp_server: str = "smtp.gmail.com",
    smtp_port: int = 587
) -> Dict[str, Any]:
    """
    Send an email notification to the admin when a lead is submitted.
    
    Args:
        admin_email: Admin email address (sender and recipient)
        admin_password: Admin email password or app password
        lead_data: Dictionary containing lead information
        smtp_server: SMTP server address (default: Gmail)
        smtp_port: SMTP server port (default: 587 for TLS)
    
    Returns:
        Dict with 'success' and 'message' keys
    
    Example:
        >>> result = send_lead_notification(
        ...     "admin@example.com",
        ...     "app_password",
        ...     {
        ...         'name': 'John Doe',
        ...         'phone': '+234 901 234 5678',
        ...         'email': 'john@example.com',
        ...         'survey_plan_number': 'LP12345',
        ...         'risk_status': 'DANGER',
        ...         'location_text': 'Lekki Phase 1'
        ...     }
        ... )
    """
    try:
        # Validate inputs
        if not admin_email or not admin_password:
            return {
                'success': False, 
                'message': 'Admin email credentials not configured in secrets'
            }
        
        # Extract lead data
        name = lead_data.get('name', 'N/A')
        phone = lead_data.get('phone', 'N/A')
        email = lead_data.get('email', 'N/A')
        survey_plan_number = lead_data.get('survey_plan_number', 'N/A')
        risk_status = lead_data.get('risk_status', 'PENDING')
        location_text = lead_data.get('location_text', 'N/A')
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Determine risk emoji and color
        risk_emoji = {
            'DANGER': '🔴',
            'CAUTION': '🟡',
            'SAFE': '🟢',
            'PENDING': '⚪'
        }.get(risk_status, '⚪')
        
        # Create email message
        message = MIMEMultipart('alternative')
        message['Subject'] = f'🚨 New Lead: {name} - {risk_emoji} {risk_status}'
        message['From'] = admin_email
        message['To'] = admin_email
        
        # Create HTML email body
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                }}
                .container {{
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                    background-color: #f9f9f9;
                }}
                .header {{
                    background-color: #2c3e50;
                    color: white;
                    padding: 20px;
                    text-align: center;
                    border-radius: 5px 5px 0 0;
                }}
                .content {{
                    background-color: white;
                    padding: 30px;
                    border-radius: 0 0 5px 5px;
                    box-shadow: 0 2px 5px rgba(0,0,0,0.1);
                }}
                .field {{
                    margin-bottom: 15px;
                    padding: 10px;
                    background-color: #f8f9fa;
                    border-left: 3px solid #3498db;
                }}
                .field-label {{
                    font-weight: bold;
                    color: #2c3e50;
                }}
                .risk-badge {{
                    display: inline-block;
                    padding: 5px 15px;
                    border-radius: 20px;
                    font-weight: bold;
                    margin-top: 10px;
                }}
                .risk-danger {{
                    background-color: #e74c3c;
                    color: white;
                }}
                .risk-caution {{
                    background-color: #f39c12;
                    color: white;
                }}
                .risk-safe {{
                    background-color: #27ae60;
                    color: white;
                }}
                .risk-pending {{
                    background-color: #95a5a6;
                    color: white;
                }}
                .footer {{
                    margin-top: 20px;
                    text-align: center;
                    color: #7f8c8d;
                    font-size: 12px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🗺️ Omo-Onile Radar</h1>
                    <h2>New Surveyor Verification Request</h2>
                </div>
                <div class="content">
                    <p><strong>Timestamp:</strong> {timestamp}</p>
                    
                    <div class="field">
                        <span class="field-label">👤 Name:</span> {name}
                    </div>
                    
                    <div class="field">
                        <span class="field-label">📱 Phone:</span> {phone}
                    </div>
                    
                    <div class="field">
                        <span class="field-label">📧 Email:</span> {email}
                    </div>
                    
                    <div class="field">
                        <span class="field-label">📝 Survey Plan Number:</span> {survey_plan_number}
                    </div>
                    
                    <div class="field">
                        <span class="field-label">📍 Location:</span> {location_text}
                    </div>
                    
                    <div class="field">
                        <span class="field-label">🚨 Risk Assessment:</span>
                        <span class="risk-badge risk-{risk_status.lower()}">
                            {risk_emoji} {risk_status}
                        </span>
                    </div>
                    
                    <div class="footer">
                        <p>This is an automated notification from Omo-Onile Radar</p>
                        <p>Contact the lead within 24 hours for best conversion rates</p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Create plain text version as fallback
        text_body = f"""
        🗺️ OMO-ONILE RADAR - NEW LEAD NOTIFICATION
        ================================================
        
        Timestamp: {timestamp}
        
        CONTACT INFORMATION:
        - Name: {name}
        - Phone: {phone}
        - Email: {email}
        
        PROPERTY DETAILS:
        - Survey Plan Number: {survey_plan_number}
        - Location: {location_text}
        
        RISK ASSESSMENT:
        - Status: {risk_emoji} {risk_status}
        
        ================================================
        Please contact this lead within 24 hours.
        """
        
        # Attach both HTML and text versions
        text_part = MIMEText(text_body, 'plain')
        html_part = MIMEText(html_body, 'html')
        message.attach(text_part)
        message.attach(html_part)
        
        # Send email
        logger.info(f"Attempting to send notification email to {admin_email}")
        
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()  # Enable TLS encryption
            server.login(admin_email, admin_password)
            server.send_message(message)
        
        logger.info(f"Successfully sent lead notification for {name}")
        return {
            'success': True,
            'message': f'Notification email sent successfully to {admin_email}'
        }
        
    except smtplib.SMTPAuthenticationError as e:
        error_msg = "Email authentication failed. Please check your credentials."
        logger.error(f"SMTP authentication error: {str(e)}")
        return {'success': False, 'message': error_msg}
        
    except smtplib.SMTPException as e:
        error_msg = f"Failed to send email: {str(e)}"
        logger.error(f"SMTP error: {str(e)}")
        return {'success': False, 'message': error_msg}
        
    except Exception as e:
        error_msg = f"Unexpected error sending notification: {str(e)}"
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return {'success': False, 'message': error_msg}


def validate_lead_data(
    name: str,
    phone: str,
    email: str
) -> Dict[str, Any]:
    """
    Validate lead data before sending notification.
    
    Args:
        name: Full name of the requester
        phone: Phone number
        email: Email address
    
    Returns:
        Dict with 'valid' boolean and optional 'error' message
    """
    # Validate name
    if not name or not name.strip():
        return {'valid': False, 'error': 'Full name is required'}
    
    # Simple phone validation: at least 10 digits
    phone_digits = re.sub(r'\D', '', phone)
    if len(phone_digits) < 10:
        return {
            'valid': False,
            'error': 'Invalid phone number. Please include at least 10 digits.'
        }
    
    # Email validation (Simplified RFC 5322)
    email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_regex, email):
        return {'valid': False, 'error': 'Invalid email address format.'}
    
    return {'valid': True}
