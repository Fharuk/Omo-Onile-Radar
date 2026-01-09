# Omo-Onile Radar 🗺️

A production-ready Streamlit application for real estate due diligence in the Nigerian market. This tool uses AI-powered OCR to extract survey plan data, transforms coordinates from Nigerian Minna Datum to WGS84, and provides interactive geospatial visualization of property boundaries.

## Features

- 🔍 **AI-Powered OCR**: Extracts survey data using OpenAI (GPT-4o) or Google Gemini (Gemini 2.5 Pro)
- 📐 **Coordinate Transformation**: Converts Minna Datum (EPSG:26331/26332) to WGS84 (EPSG:4326)
- 🗺️ **Interactive Maps**: Visualizes property boundaries using Folium with satellite imagery
- 🛰️ **Satellite View**: Toggle between Street and Satellite (Esri World Imagery) map layers
- 📏 **Unit Conversion**: Support for both Meters and Feet coordinate units
- ✏️ **Editable Coordinates**: Review and correct extracted coordinates before mapping
- 📧 **Email Notifications**: Admin receives instant email alerts when leads are submitted
- 🚨 **Risk Detection**: Intelligent detection of government acquisition zones and restricted areas
- ⚠️ **Red Flag Detection**: Identifies concerning terms in survey documents
- 📊 **Data Export**: Download extracted coordinates as CSV
- 🎨 **User-Friendly Interface**: Clean, intuitive Streamlit interface
- 🧪 **Demo Mode**: Test the application without an API key

## Nigerian Minna Datum Zones

The application supports both Nigerian survey zones:
- **Zone 31N (West)**: EPSG:26331 - Covers western Lagos and surrounding areas
- **Zone 32N (East)**: EPSG:26332 - Covers eastern Lagos and surrounding areas

## Installation

### Prerequisites

- Python 3.9 or higher
- An API key for either:
  - OpenAI ([Get one here](https://platform.openai.com/api-keys))
  - Google Gemini (via Google AI Studio)

### Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd omo-onile-radar
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   
   # On Windows
   venv\Scripts\activate
   
   # On macOS/Linux
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment (Optional)**
   ```bash
   cp .env.example .env
   # Edit .env and add your API key (OpenAI or Gemini)
   ```

5. **Configure email notifications (Optional)**
   
   To receive email notifications when leads are submitted:
   
   ```bash
   # Create Streamlit secrets directory
   mkdir -p .streamlit
   
   # Copy the example secrets file
   cp .secrets.toml.example .streamlit/secrets.toml
   
   # Edit .streamlit/secrets.toml and add your email credentials
   ```
   
   **For Gmail users:**
   - You MUST use an App Password (not your regular Gmail password)
   - Generate one at: https://myaccount.google.com/apppasswords
   - Select "Mail" as the app type
   - Copy the generated password to `secrets.toml`
   
   Example `.streamlit/secrets.toml`:
   ```toml
   [email]
   admin_email = "your-email@gmail.com"
   admin_password = "your-16-char-app-password"
   ```

## Usage

### Running the Application

1. **Start the Streamlit app**
   ```bash
   streamlit run app.py
   ```

2. **Access the application**
   - The app will automatically open in your browser
   - If not, navigate to `http://localhost:8501`

### Using the Tool

1. **Select your AI provider** (OpenAI GPT-4o or Google Gemini 2.5 Pro)
2. **Enter your API key** in the sidebar (or enable Demo Mode)
3. **Select your region** (Lagos West or Lagos East)
4. **Select coordinate units** (Meters or Feet)
5. **Upload a survey plan** image (PNG, JPG, or JPEG)
6. **Click "Process Survey Plan"** to extract data
7. **Review and edit coordinates** in the editable table if needed
8. **View results**:
   - Survey metadata (number, surveyor, location)
   - Risk assessment (government zone intersections)
   - Red flags (if any)
   - Interactive map with property boundaries and satellite view
   - Toggle between Street and Satellite map layers
   - Coordinate table with both Minna and WGS84 values
9. **Download coordinates** as CSV for further analysis
10. **Request professional verification** via the lead form (admin receives email notification)

## Project Structure

```
omo-onile-radar/
├── app.py                      # Main Streamlit application
├── requirements.txt            # Python dependencies
├── .env.example               # Environment configuration template
├── .secrets.toml.example      # Email notification config example
├── README.md                  # This file
└── utils/
    ├── __init__.py            # Package initialization
    ├── geo.py                 # Coordinate transformation module (with unit conversion)
    ├── ocr.py                 # Survey data extraction module
    ├── risk_engine.py         # Risk detection and government zone analysis
    ├── db.py                  # Database operations for lead management
    └── email_notifier.py      # Email notification system
```

## Modules

### utils/geo.py - Coordinate Transformation

The `CoordinateManager` class handles all coordinate transformations:

```python
from utils.geo import CoordinateManager

manager = CoordinateManager()

# Convert single coordinate (meters)
lon, lat = manager.convert_minna_to_wgs84(
    easting=543210.50,
    northing=712345.20,
    zone=26331,  # Zone 31N
    units='meters'  # Default
)

# Convert coordinates in feet
lon, lat = manager.convert_minna_to_wgs84(
    easting=1782186.68,  # feet
    northing=2338042.65,  # feet
    zone=26331,
    units='feet'  # Converts to meters internally
)

# Batch convert coordinates
coordinates = [
    {'easting': 543210.50, 'northing': 712345.20},
    {'easting': 543250.30, 'northing': 712345.20}
]
converted = manager.batch_convert(coordinates, zone=26331, units='meters')
```

### utils/ocr.py - Survey Data Extraction

The `extract_survey_data` function supports multiple providers:

```python
from utils.ocr import extract_survey_data

with open('survey_plan.jpg', 'rb') as f:
    image_bytes = f.read()

# OpenAI
result = extract_survey_data(image_bytes, api_key="your-openai-key", provider="openai")

# Gemini
result = extract_survey_data(image_bytes, api_key="your-gemini-key", provider="gemini")

print(result["survey_number"])
print(result["coordinates"])
print(result["red_flags"])
```

## Technical Details

### Coordinate Systems

- **Source**: Nigerian Minna Datum (Transverse Mercator projection)
  - Zone 31N: EPSG:26331 (West Lagos)
  - Zone 32N: EPSG:26332 (East Lagos)
- **Target**: WGS84 (EPSG:4326) - Used by GPS and web mapping services

### AI Model

- **Models**:
  - OpenAI: GPT-4o (Vision)
  - Google Gemini: Gemini 2.5 Pro (default for Gemini provider)
- **Purpose**: Extract structured data from survey plan images
- **Extracted Data**:
  - Survey number
  - Surveyor name
  - Location description
  - Corner coordinates (easting/northing)
  - Red flag keywords

### Red Flag Detection

The system scans for concerning terms including:
- "Excision in Process"
- "Ratification"
- "Committed"
- "Pending"
- "Provisional"
- "Subject to"
- "Disputed"

## Error Handling

The application includes comprehensive error handling for:
- Invalid API keys
- Coordinate validation failures
- OCR extraction errors
- Coordinate transformation errors
- Network/API timeout issues
- Invalid image formats

## Security

- API keys are masked in the UI
- No credentials are stored permanently
- All processing happens server-side
- No data is persisted between sessions

## Limitations

- **AI Accuracy**: OCR results depend on image quality and document clarity
- **Coordinate Ranges**: Validation assumes typical Nigerian coordinate ranges
- **Supported Zones**: Currently supports Lagos zones (31N and 32N)
- **Image Quality**: Clear, high-resolution images produce best results

## Disclaimer

⚠️ **Important**: This tool is for informational use only and does not constitute legal confirmation of land ownership or boundaries. Always consult with qualified surveyors and legal professionals before making any land purchase or development decisions.

## Dependencies

Core dependencies (see `requirements.txt` for versions):
- `streamlit` - Web application framework
- `streamlit-folium` - Streamlit component for Folium maps
- `folium` - Interactive mapping library
- `pyproj` - Coordinate transformation library
- `openai` - OpenAI API client
- `google-generativeai` - Google Gemini API client
- `python-dotenv` - Environment variable management
- `Pillow` - Image processing library

## Troubleshooting

### Common Issues

1. **"Invalid API Key" Error**
   - Verify your API key is correct for the selected provider
   - For OpenAI: ensure your key has access to GPT-4o (Vision)
   - For Gemini: ensure your key is enabled for the Gemini API

2. **"Coordinate Outside Valid Range" Error**
   - Ensure you've selected the correct zone (West vs East)
   - Verify the survey plan uses Minna Datum coordinates

3. **No Coordinates Extracted**
   - Upload a clearer image
   - Ensure the survey plan contains a coordinate table
   - Check that text is readable in the image

4. **Map Not Centering on Property**
   - Verify coordinates are in the correct zone
   - Check coordinate values are reasonable for Nigeria

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## License

This project is provided as-is for educational and informational purposes.

## Support

For issues, questions, or feature requests, please open an issue on the project repository.

---

Built with ❤️ for the Nigerian Real Estate Market
