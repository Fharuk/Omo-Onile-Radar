"""
Survey data extraction module using OpenAI Vision API.

This module uses OpenAI's GPT-4 Vision model to extract structured data from
survey plan images, including coordinates, survey metadata, and potential red flags.
"""

import base64
import json
import logging
import time
from typing import Dict, Any, Optional, List
from io import BytesIO
from openai import OpenAI, OpenAIError, APIError, RateLimitError, APITimeoutError
try:
    import google.generativeai as genai
    GOOGLE_AI_AVAILABLE = True
except ImportError:
    GOOGLE_AI_AVAILABLE = False
    genai = None

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class OCRError(Exception):
    """Custom exception for OCR processing errors."""
    pass


class OCRValidationError(Exception):
    """Custom exception for OCR result validation errors."""
    pass


def encode_image_to_base64(image_bytes: bytes) -> str:
    """
    Encode image bytes to base64 string for API transmission.
    
    Args:
        image_bytes: Raw image bytes
    
    Returns:
        Base64-encoded string representation of the image
    
    Raises:
        OCRError: If encoding fails
    """
    try:
        return base64.b64encode(image_bytes).decode('utf-8')
    except Exception as e:
        error_msg = f"Failed to encode image to base64: {str(e)}"
        logger.error(error_msg)
        raise OCRError(error_msg)


def validate_extraction_result(data: Dict[str, Any]) -> bool:
    """
    Validate the structure of extracted survey data.
    
    Args:
        data: Dictionary containing extracted survey data
    
    Returns:
        True if validation passes
    
    Raises:
        OCRValidationError: If validation fails
    """
    required_fields = ['survey_number', 'surveyor_name', 'location_text', 'coordinates', 'red_flags']
    
    # Check for required fields
    missing_fields = [field for field in required_fields if field not in data]
    if missing_fields:
        raise OCRValidationError(
            f"Missing required fields in extraction result: {', '.join(missing_fields)}"
        )
    
    # Validate coordinates structure
    if not isinstance(data['coordinates'], list):
        raise OCRValidationError(
            f"'coordinates' must be a list, got {type(data['coordinates']).__name__}"
        )
    
    # Validate each coordinate entry
    for idx, coord in enumerate(data['coordinates']):
        if not isinstance(coord, dict):
            raise OCRValidationError(
                f"Coordinate {idx} must be a dictionary, got {type(coord).__name__}"
            )
        
        if 'easting' not in coord or 'northing' not in coord:
            raise OCRValidationError(
                f"Coordinate {idx} missing 'easting' or 'northing' key"
            )
        
        # Try to convert to float to ensure they're numeric
        try:
            float(coord['easting'])
            float(coord['northing'])
        except (TypeError, ValueError) as e:
            raise OCRValidationError(
                f"Coordinate {idx} has invalid numeric values: {str(e)}"
            )
    
    # Validate red_flags is a list
    if not isinstance(data['red_flags'], list):
        raise OCRValidationError(
            f"'red_flags' must be a list, got {type(data['red_flags']).__name__}"
        )
    
    logger.info("Extraction result validation passed")
    return True


def extract_survey_data(
    image_bytes: bytes, 
    api_key: str,
    provider: str = 'openai',
    max_retries: int = 3,
    retry_delay: int = 2,
    use_demo_data: bool = False
) -> Dict[str, Any]:
    """
    Extract survey data from a survey plan image using OpenAI Vision API.
    
    This function uses GPT-4 Vision to analyze survey plan images and extract:
    - Survey number and identification
    - Surveyor name and credentials
    - Location information
    - Coordinate pairs (easting and northing)
    - Red flags indicating potential issues
    
    The function includes retry logic for handling transient API failures such as
    rate limits or temporary network issues.
    
    Args:
        image_bytes: Raw bytes of the survey plan image
        api_key: API key for the selected provider
        provider: AI provider to use ('openai' or 'gemini'). Defaults to 'openai'
        max_retries: Maximum number of retry attempts for transient failures
        retry_delay: Delay in seconds between retries (doubles after each attempt)
        use_demo_data: If True, bypass API and return hardcoded demo data
    
    Returns:
        Dictionary containing:
            - survey_number (str): Survey plan identification number
            - surveyor_name (str): Name of the surveyor or surveying firm
            - location_text (str): Location description of the property
            - coordinates (list): List of coordinate dictionaries with 'easting' and 'northing'
            - red_flags (list): List of concerning terms found in the document
            - error (str, optional): Error message if extraction failed
    
    Raises:
        OCRError: If extraction fails after all retries
        OCRValidationError: If extracted data doesn't match expected structure
    
    Examples:
        >>> with open('survey_plan.jpg', 'rb') as f:
        ...     image_data = f.read()
        >>> result = extract_survey_data(image_data, 'sk-...')
        >>> print(result['survey_number'])
        'LS/123/2023'
    """
    if use_demo_data:
        logger.info("Using demo data mode - bypassing OpenAI API")
        return {
            'survey_number': 'DEMO-2024-001',
            'surveyor_name': 'Demo Surveyor & Associates',
            'location_text': 'Lekki, Lagos - Restricted Zone Test Case',
            'coordinates': [
                {'easting': 700000, 'northing': 651500},  # Inside Lekki Gov Zone
                {'easting': 701000, 'northing': 651500},
                {'easting': 701000, 'northing': 650500},
                {'easting': 700000, 'northing': 650500}
            ],
            'red_flags': ['Overlaps with Government Acquisition Zone'],
            'demo_mode': True
        }
    
    # Demo mode validation - require API key and image for non-demo mode
    if not api_key:
        provider_name = "OpenAI" if provider == "openai" else "Google Gemini"
        error_msg = f"{provider_name} API key is required"
        logger.error(error_msg)
        return {'error': error_msg}
    
    if not image_bytes:
        error_msg = "Image bytes are required"
        logger.error(error_msg)
        return {'error': error_msg}
    
    # Route to appropriate AI provider
    if provider == 'gemini':
        if not GOOGLE_AI_AVAILABLE:
            error_msg = "Google Gemini package is not installed. Please install with: pip install google-generativeai"
            logger.error(error_msg)
            return {'error': error_msg}
        
        try:
            logger.info("Using Google Gemini for OCR extraction")
            return extract_with_gemini(image_bytes, api_key)
        except OCRError:
            raise
        except Exception as e:
            error_msg = f"Unexpected error with Gemini: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {'error': error_msg}
    
    # Default to OpenAI
    try:
        # Encode image to base64
        base64_image = encode_image_to_base64(image_bytes)
        logger.info(f"Image encoded to base64, size: {len(base64_image)} characters")
        
        # Initialize OpenAI client
        client = OpenAI(api_key=api_key)
        
        # Construct the system prompt for survey data extraction
        system_prompt = """You are an expert Surveyor with extensive experience in Nigerian land surveying and documentation. 

Your task is to analyze survey plan images and extract structured information. Extract the following information into valid JSON format:

1. 'survey_number': The survey plan number or reference (e.g., "LS/1234/2023", "Plan No. 456")
2. 'surveyor_name': The name of the surveyor or surveying firm who prepared the plan
3. 'location_text': The location description of the property (e.g., "Plot 5, Block A, Lekki Phase 1, Lagos")
4. 'coordinates': A list of coordinate pairs. Each coordinate should be a dictionary with:
   - 'easting': The easting coordinate value (X coordinate in meters)
   - 'northing': The northing coordinate value (Y coordinate in meters)
5. 'red_flags': Scan the document for concerning terms or phrases that might indicate issues with the property title or survey. Look for words or phrases such as:
   - "Excision in Process"
   - "Ratification"
   - "Committed"
   - "Pending"
   - "Provisional"
   - "Subject to"
   - "Disputed"
   - Any other terms suggesting incomplete or problematic status

IMPORTANT INSTRUCTIONS:
- If any field cannot be found, use an empty string "" for text fields or empty list [] for list fields
- Coordinates should be extracted carefully - they are typically found in coordinate tables or at plot corners
- Extract ALL coordinate pairs you can find (typically 3-8 for land plots)
- Numbers in coordinates often have 6-7 digits
- Return ONLY valid JSON, no additional text or explanations
- Do not include any markdown formatting

Example output format:
{
  "survey_number": "LS/1234/2023",
  "surveyor_name": "John Doe & Associates",
  "location_text": "Plot 5, Block A, Lekki Phase 1, Lagos",
  "coordinates": [
    {"easting": 543210.50, "northing": 712345.20},
    {"easting": 543250.30, "northing": 712345.20},
    {"easting": 543250.30, "northing": 712385.40},
    {"easting": 543210.50, "northing": 712385.40}
  ],
  "red_flags": ["Excision in Process"]
}"""
        
        # Attempt extraction with retry logic
        last_error = None
        current_delay = retry_delay
        
        for attempt in range(max_retries):
            try:
                logger.info(f"Attempting OCR extraction (attempt {attempt + 1}/{max_retries})")
                
                # Make API call
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {
                            "role": "system",
                            "content": system_prompt
                        },
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Please analyze this survey plan image and extract the requested information in JSON format."
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{base64_image}"
                                    }
                                }
                            ]
                        }
                    ],
                    max_tokens=2000,
                    temperature=0.1  # Low temperature for more consistent extraction
                )
                
                # Extract content from response
                content = response.choices[0].message.content
                logger.info("Received response from OpenAI API")
                logger.debug(f"Response content: {content}")
                
                # Parse JSON response
                # Remove markdown code blocks if present
                content = content.strip()
                if content.startswith("```json"):
                    content = content[7:]
                if content.startswith("```"):
                    content = content[3:]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()
                
                try:
                    extracted_data = json.loads(content)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse JSON response: {str(e)}")
                    logger.error(f"Response content: {content}")
                    raise OCRError(f"Failed to parse API response as JSON: {str(e)}")
                
                # Validate the extracted data structure
                validate_extraction_result(extracted_data)
                
                logger.info(
                    f"Successfully extracted survey data: "
                    f"{len(extracted_data.get('coordinates', []))} coordinates found"
                )
                
                return extracted_data
                
            except RateLimitError as e:
                last_error = e
                logger.warning(f"Rate limit hit on attempt {attempt + 1}: {str(e)}")
                if attempt < max_retries - 1:
                    logger.info(f"Retrying in {current_delay} seconds...")
                    time.sleep(current_delay)
                    current_delay *= 2  # Exponential backoff
                    
            except APITimeoutError as e:
                last_error = e
                logger.warning(f"API timeout on attempt {attempt + 1}: {str(e)}")
                if attempt < max_retries - 1:
                    logger.info(f"Retrying in {current_delay} seconds...")
                    time.sleep(current_delay)
                    current_delay *= 2
                    
            except APIError as e:
                # Check if it's a transient error
                if e.status_code and e.status_code >= 500:
                    last_error = e
                    logger.warning(f"Server error on attempt {attempt + 1}: {str(e)}")
                    if attempt < max_retries - 1:
                        logger.info(f"Retrying in {current_delay} seconds...")
                        time.sleep(current_delay)
                        current_delay *= 2
                else:
                    # Non-transient API error, don't retry
                    raise OCRError(f"OpenAI API error: {str(e)}")
        
        # If we've exhausted all retries
        error_msg = f"Failed to extract survey data after {max_retries} attempts: {str(last_error)}"
        logger.error(error_msg)
        raise OCRError(error_msg)
        
    except OCRError:
        # Re-raise OCR-specific errors
        raise
        
    except OCRValidationError:
        # Re-raise validation errors
        raise
        
    except OpenAIError as e:
        error_msg = f"OpenAI API error: {str(e)}"
        logger.error(error_msg)
        raise OCRError(error_msg)
        
    except Exception as e:
        error_msg = f"Unexpected error during survey data extraction: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise OCRError(error_msg)


def extract_with_gemini(image_bytes: bytes, api_key: str) -> Dict[str, Any]:
    """
    Extract survey data using Google Gemini Vision API.
    
    Args:
        image_bytes: Raw bytes of the survey plan image
        api_key: Google API key for Gemini
    
    Returns:
        Dictionary containing extracted survey data
    
    Raises:
        OCRError: If extraction fails
    """
    try:
        # Configure Gemini API
        genai.configure(api_key=api_key)
        
        # Use the appropriate Gemini model (default to 1.5 Flash for speed and cost)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # Convert image bytes to a format suitable for Gemini
        from PIL import Image
        image = Image.open(BytesIO(image_bytes))
        
        # System prompt for survey data extraction (same as OpenAI)
        system_prompt = """You are an expert Surveyor with extensive experience in Nigerian land surveying and documentation. 

Your task is to analyze survey plan images and extract structured information. Extract the following information into valid JSON format:

1. 'survey_number': The survey plan number or reference (e.g., \"LS/1234/2023\", \"Plan No. 456\")
2. 'surveyor_name': The name of the surveyor or surveying firm who prepared the plan
3. 'location_text': The location description of the property (e.g., \"Plot 5, Block A, Lekki Phase 1, Lagos\")
4. 'coordinates': A list of coordinate pairs. Each coordinate should be a dictionary with:
   - 'easting': The easting coordinate value (X coordinate in meters)
   - 'northing': The northing coordinate value (Y coordinate in meters)
5. 'red_flags': Scan the document for concerning terms or phrases that might indicate issues with the property title or survey. Look for words or phrases such as:
   - \"Excision in Process\"
   - \"Ratification\"
   - \"Committed\"
   - \"Pending\"
   - \"Provisional\"
   - \"Subject to\"
   - \"Disputed\"
   - Any other terms suggesting incomplete or problematic status

IMPORTANT INSTRUCTIONS:
- If any field cannot be found, use an empty string \"\" for text fields or empty list [] for list fields
- Coordinates should be extracted carefully - they are typically found in coordinate tables or at plot corners
- Extract ALL coordinate pairs you can find (typically 3-8 for land plots)
- Numbers in coordinates often have 6-7 digits
- Return ONLY valid JSON, no additional text or explanations
- Do not include any markdown formatting

Example output format:
{
  \"survey_number\": \"LS/1234/2023\",
  \"surveyor_name\": \"John Doe & Associates\",
  \"location_text\": \"Plot 5, Block A, Lekki Phase 1, Lagos\",
  \"coordinates\": [
    {\"easting\": 543210.50, \"northing\": 712345.20},
    {\"easting\": 543250.30, \"northing\": 712345.20},
    {\"easting\": 543250.30, \"northing\": 712385.40},
    {\"easting\": 543210.50, \"northing\": 712385.40}
  ],
  \"red_flags\": [\"Excision in Process\"]
}"""
        
        # Prepare the prompt for Gemini
        prompt = f"{system_prompt}\n\nPlease analyze this survey plan image and extract the requested information in JSON format."
        
        # Generate content with image
        response = model.generate_content([prompt, image])
        
        # Extract the text response
        content = response.text
        logger.info("Received response from Google Gemini API")
        logger.debug(f"Response content: {content}")
        
        # Parse JSON response - CRITICAL: Strip markdown code blocks if present
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:].strip()
        elif content.startswith("```"):
            content = content[3:].strip()
        
        if content.endswith("```"):
            content = content[:-3].strip()
        
        # Parse JSON
        try:
            extracted_data = json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response from Gemini: {str(e)}")
            logger.error(f"Response content: {content}")
            raise OCRError(f"Failed to parse Gemini API response as JSON: {str(e)}")
        
        # Validate the extracted data structure
        validate_extraction_result(extracted_data)
        
        logger.info(
            f"Successfully extracted survey data using Gemini: "
            f"{len(extracted_data.get('coordinates', []))} coordinates found"
        )
        
        return extracted_data
        
    except Exception as e:
        error_msg = f"Error during Gemini extraction: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise OCRError(error_msg)


def format_coordinates_summary(coordinates: List[Dict[str, float]]) -> str:
    """
    Format coordinates into a human-readable summary.
    
    Args:
        coordinates: List of coordinate dictionaries
    
    Returns:
        Formatted string summary of coordinates
    """
    if not coordinates:
        return "No coordinates found"
    
    summary_lines = [f"Total coordinates: {len(coordinates)}\n"]
    
    for idx, coord in enumerate(coordinates, 1):
        easting = coord.get('easting', 'N/A')
        northing = coord.get('northing', 'N/A')
        summary_lines.append(f"  Point {idx}: E={easting}, N={northing}")
    
    return "\n".join(summary_lines)
