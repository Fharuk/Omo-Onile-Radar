"""
Omo-Onile Radar - Real Estate Due Diligence Tool for Nigerian Market

A Streamlit application that uses AI-powered OCR to extract survey plan data,
transform coordinates from Nigerian Minna Datum to WGS84, and visualize property
boundaries on an interactive map.
"""

import streamlit as st
import folium
from streamlit_folium import st_folium
from typing import Optional, Dict, Any, List
import logging
from utils.ocr import extract_survey_data, OCRError, OCRValidationError, format_coordinates_summary
from utils.geo import (
    CoordinateManager, 
    CoordinateTransformationError, 
    CoordinateValidationError
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Page configuration
st.set_page_config(
    page_title="Omo-Onile Radar",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize coordinate manager
@st.cache_resource
def get_coordinate_manager() -> CoordinateManager:
    """Initialize and cache the coordinate manager."""
    return CoordinateManager()


def initialize_session_state():
    """Initialize session state variables."""
    if 'api_key' not in st.session_state:
        st.session_state.api_key = ""
    if 'region' not in st.session_state:
        st.session_state.region = CoordinateManager.ZONE_31N
    if 'uploaded_file' not in st.session_state:
        st.session_state.uploaded_file = None
    if 'extraction_results' not in st.session_state:
        st.session_state.extraction_results = None
    if 'converted_coordinates' not in st.session_state:
        st.session_state.converted_coordinates = None
    if 'file_processed' not in st.session_state:
        st.session_state.file_processed = False


def mask_api_key(api_key: str) -> str:
    """
    Mask API key for display purposes.
    
    Args:
        api_key: The API key to mask
    
    Returns:
        Masked version of the API key
    """
    if not api_key or len(api_key) < 8:
        return "****"
    return api_key[:4] + "*" * (len(api_key) - 8) + api_key[-4:]


def render_sidebar():
    """Render the sidebar with API key input and region selection."""
    st.sidebar.title("⚙️ Configuration")
    
    # API Key Input
    st.sidebar.subheader("OpenAI API Key")
    api_key_input = st.sidebar.text_input(
        "Enter your OpenAI API key",
        type="password",
        value=st.session_state.api_key,
        help="Your API key is required to process survey plans with AI"
    )
    
    if api_key_input != st.session_state.api_key:
        st.session_state.api_key = api_key_input
        st.session_state.file_processed = False
    
    if st.session_state.api_key:
        st.sidebar.success(f"API Key: {mask_api_key(st.session_state.api_key)}")
    else:
        st.sidebar.warning("⚠️ Please enter your OpenAI API key to continue")
    
    st.sidebar.markdown("---")
    
    # Region Selection
    st.sidebar.subheader("Survey Region")
    zone_options = {
        "Lagos West (Zone 31N)": CoordinateManager.ZONE_31N,
        "Lagos East (Zone 32N)": CoordinateManager.ZONE_32N
    }
    
    selected_region = st.sidebar.selectbox(
        "Select the region of your survey",
        options=list(zone_options.keys()),
        index=0 if st.session_state.region == CoordinateManager.ZONE_31N else 1,
        help="Choose the zone based on the location of your property"
    )
    
    new_region = zone_options[selected_region]
    if new_region != st.session_state.region:
        st.session_state.region = new_region
        st.session_state.converted_coordinates = None  # Clear old conversions
    
    st.sidebar.info(
        f"📍 Selected: {selected_region}\n\n"
        f"EPSG Code: {st.session_state.region}"
    )
    
    st.sidebar.markdown("---")
    
    # Information
    st.sidebar.subheader("ℹ️ About")
    st.sidebar.markdown(
        """
        **Omo-Onile Radar** helps you perform due diligence on Nigerian land surveys by:
        
        1. 🔍 Extracting data from survey plans using AI
        2. 📐 Converting Minna Datum coordinates to WGS84
        3. 🗺️ Visualizing property boundaries on a map
        4. ⚠️ Identifying potential red flags
        
        **Supported Formats:** PNG, JPG, JPEG
        """
    )


def render_metadata_card(title: str, content: str, icon: str = "📋", is_warning: bool = False):
    """
    Render a metadata card with styling.
    
    Args:
        title: Card title
        content: Card content
        icon: Icon emoji
        is_warning: Whether to style as a warning
    """
    bg_color = "#fff3cd" if is_warning else "#f8f9fa"
    border_color = "#ffc107" if is_warning else "#dee2e6"
    
    st.markdown(
        f"""
        <div style="
            background-color: {bg_color};
            border: 1px solid {border_color};
            border-radius: 0.5rem;
            padding: 1rem;
            margin-bottom: 1rem;
        ">
            <h4 style="margin: 0 0 0.5rem 0; color: #333;">
                {icon} {title}
            </h4>
            <p style="margin: 0; color: #666; white-space: pre-wrap;">
                {content}
            </p>
        </div>
        """,
        unsafe_allow_html=True
    )


def display_extraction_results(results: Dict[str, Any]):
    """
    Display extracted survey data in a user-friendly format.
    
    Args:
        results: Dictionary containing extracted survey data
    """
    st.subheader("📄 Survey Information")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Survey Number
        survey_number = results.get('survey_number', 'Not found')
        render_metadata_card(
            "Survey Number",
            survey_number if survey_number else "Not found",
            icon="📝"
        )
        
        # Location
        location = results.get('location_text', 'Not found')
        render_metadata_card(
            "Location",
            location if location else "Not found",
            icon="📍"
        )
    
    with col2:
        # Surveyor
        surveyor = results.get('surveyor_name', 'Not found')
        render_metadata_card(
            "Surveyor",
            surveyor if surveyor else "Not found",
            icon="👤"
        )
        
        # Red Flags
        red_flags = results.get('red_flags', [])
        if red_flags:
            red_flags_text = "\n".join([f"• {flag}" for flag in red_flags])
            render_metadata_card(
                "⚠️ Red Flags Detected",
                red_flags_text,
                icon="🚩",
                is_warning=True
            )
        else:
            st.success("✅ No red flags detected")
    
    # Coordinates summary
    coordinates = results.get('coordinates', [])
    if coordinates:
        st.info(f"📐 Found {len(coordinates)} coordinate points")


def create_map_visualization(
    converted_coords: List[Dict[str, float]], 
    survey_info: Dict[str, Any]
) -> folium.Map:
    """
    Create a Folium map with property boundaries and markers.
    
    Args:
        converted_coords: List of converted coordinates with lat/lon
        survey_info: Survey metadata for marker tooltips
    
    Returns:
        Folium map object
    """
    # Default center (Nigeria)
    default_center = [6.5244, 3.3792]  # Lagos, Nigeria
    zoom_start = 6
    
    # If we have coordinates, center on the first point
    if converted_coords and len(converted_coords) > 0:
        first_coord = converted_coords[0]
        default_center = [first_coord['latitude'], first_coord['longitude']]
        zoom_start = 18
    
    # Create map
    m = folium.Map(
        location=default_center,
        zoom_start=zoom_start,
        tiles='OpenStreetMap'
    )
    
    # Add satellite imagery layer option
    folium.TileLayer(
        tiles='https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}',
        attr='Google Satellite',
        name='Satellite View',
        overlay=False,
        control=True
    ).add_to(m)
    
    # Add layer control
    folium.LayerControl().add_to(m)
    
    if not converted_coords:
        return m
    
    # Extract lat/lon pairs for polygon
    polygon_points = [
        [coord['latitude'], coord['longitude']] 
        for coord in converted_coords
    ]
    
    # Close the polygon by adding the first point at the end
    if len(polygon_points) > 2:
        polygon_points.append(polygon_points[0])
    
    # Draw polygon
    folium.Polygon(
        locations=polygon_points,
        color='red',
        fill=True,
        fill_color='red',
        fill_opacity=0.2,
        weight=3,
        popup=f"Survey: {survey_info.get('survey_number', 'Unknown')}"
    ).add_to(m)
    
    # Add markers for each corner
    for idx, coord in enumerate(converted_coords, 1):
        # Create popup content
        popup_html = f"""
        <div style="font-family: Arial, sans-serif; min-width: 200px;">
            <h4 style="margin: 0 0 10px 0;">Point {idx}</h4>
            <table style="width: 100%;">
                <tr>
                    <td><b>Latitude:</b></td>
                    <td>{coord['latitude']:.6f}</td>
                </tr>
                <tr>
                    <td><b>Longitude:</b></td>
                    <td>{coord['longitude']:.6f}</td>
                </tr>
                <tr>
                    <td colspan="2" style="padding-top: 10px; border-top: 1px solid #ccc;">
                        <i>Original Minna Datum:</i>
                    </td>
                </tr>
                <tr>
                    <td><b>Easting:</b></td>
                    <td>{coord['easting']:.2f}</td>
                </tr>
                <tr>
                    <td><b>Northing:</b></td>
                    <td>{coord['northing']:.2f}</td>
                </tr>
            </table>
        </div>
        """
        
        folium.Marker(
            location=[coord['latitude'], coord['longitude']],
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=f"Point {idx}",
            icon=folium.Icon(color='red', icon='info-sign')
        ).add_to(m)
    
    return m


def process_survey_image(image_bytes: bytes, api_key: str) -> Optional[Dict[str, Any]]:
    """
    Process the uploaded survey image and extract data.
    
    Args:
        image_bytes: Raw image bytes
        api_key: OpenAI API key
    
    Returns:
        Extracted survey data or None if processing fails
    """
    try:
        with st.spinner("🔍 Analyzing document with AI..."):
            results = extract_survey_data(image_bytes, api_key)
            
            if 'error' in results:
                st.error(f"❌ Error processing image: {results['error']}")
                return None
            
            logger.info("Survey data extraction successful")
            return results
            
    except OCRError as e:
        st.error(f"❌ OCR Error: {str(e)}")
        logger.error(f"OCR error: {str(e)}")
        return None
        
    except OCRValidationError as e:
        st.error(f"❌ Validation Error: {str(e)}")
        logger.error(f"Validation error: {str(e)}")
        return None
        
    except Exception as e:
        st.error(f"❌ Unexpected error: {str(e)}")
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return None


def convert_coordinates(
    coordinates: List[Dict[str, float]], 
    zone: int,
    coord_manager: CoordinateManager
) -> Optional[List[Dict[str, float]]]:
    """
    Convert coordinates from Minna Datum to WGS84.
    
    Args:
        coordinates: List of coordinate dictionaries
        zone: Zone EPSG code
        coord_manager: CoordinateManager instance
    
    Returns:
        List of converted coordinates or None if conversion fails
    """
    try:
        with st.spinner("📐 Converting coordinates..."):
            converted = coord_manager.batch_convert(coordinates, zone)
            logger.info(f"Successfully converted {len(converted)} coordinates")
            return converted
            
    except CoordinateValidationError as e:
        st.error(f"❌ Coordinate Validation Error: {str(e)}")
        logger.error(f"Validation error: {str(e)}")
        return None
        
    except CoordinateTransformationError as e:
        st.error(f"❌ Coordinate Transformation Error: {str(e)}")
        logger.error(f"Transformation error: {str(e)}")
        return None
        
    except Exception as e:
        st.error(f"❌ Unexpected error during coordinate conversion: {str(e)}")
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return None


def main():
    """Main application entry point."""
    # Initialize session state
    initialize_session_state()
    
    # Render sidebar
    render_sidebar()
    
    # Main content area
    st.title("🗺️ Omo-Onile Radar")
    st.markdown(
        "### Real Estate Due Diligence Tool for Nigerian Market\n"
        "Upload a survey plan to extract data, convert coordinates, and visualize property boundaries."
    )
    
    st.markdown("---")
    
    # Check if API key is provided
    if not st.session_state.api_key:
        st.warning("⚠️ Please enter your OpenAI API key in the sidebar to continue.")
        st.info(
            "👉 Don't have an API key? Get one from [OpenAI Platform](https://platform.openai.com/api-keys)"
        )
        return
    
    # File uploader
    st.subheader("📤 Upload Survey Plan")
    uploaded_file = st.file_uploader(
        "Choose a survey plan image",
        type=['png', 'jpg', 'jpeg'],
        help="Upload a clear image of the survey plan document"
    )
    
    # Check if a new file was uploaded
    if uploaded_file is not None:
        # Check if this is a new file
        file_id = f"{uploaded_file.name}_{uploaded_file.size}"
        if st.session_state.uploaded_file != file_id:
            st.session_state.uploaded_file = file_id
            st.session_state.file_processed = False
            st.session_state.extraction_results = None
            st.session_state.converted_coordinates = None
        
        # Display uploaded image
        col1, col2 = st.columns([1, 2])
        with col1:
            st.image(uploaded_file, caption="Uploaded Survey Plan", use_container_width=True)
        
        with col2:
            st.info(
                f"**File Details:**\n\n"
                f"- Name: {uploaded_file.name}\n"
                f"- Size: {uploaded_file.size / 1024:.2f} KB\n"
                f"- Type: {uploaded_file.type}"
            )
        
        st.markdown("---")
        
        # Process button
        if st.button("🚀 Process Survey Plan", type="primary", use_container_width=True):
            st.session_state.file_processed = False
            st.session_state.extraction_results = None
            st.session_state.converted_coordinates = None
        
        # Process the file if not already processed
        if not st.session_state.file_processed:
            # Read image bytes
            image_bytes = uploaded_file.read()
            uploaded_file.seek(0)  # Reset file pointer
            
            # Extract survey data
            extraction_results = process_survey_image(
                image_bytes, 
                st.session_state.api_key
            )
            
            if extraction_results:
                st.session_state.extraction_results = extraction_results
                st.session_state.file_processed = True
        
        # Display results if available
        if st.session_state.extraction_results:
            display_extraction_results(st.session_state.extraction_results)
            
            st.markdown("---")
            
            # Process coordinates
            coordinates = st.session_state.extraction_results.get('coordinates', [])
            
            if not coordinates:
                st.warning(
                    "⚠️ No coordinates were found in the survey plan. "
                    "Please ensure the image is clear and contains coordinate information."
                )
            else:
                # Convert coordinates if not already converted
                if st.session_state.converted_coordinates is None:
                    coord_manager = get_coordinate_manager()
                    converted = convert_coordinates(
                        coordinates,
                        st.session_state.region,
                        coord_manager
                    )
                    
                    if converted:
                        st.session_state.converted_coordinates = converted
                
                # Display map if coordinates are converted
                if st.session_state.converted_coordinates:
                    st.subheader("🗺️ Property Boundary Visualization")
                    
                    # Create and display map
                    property_map = create_map_visualization(
                        st.session_state.converted_coordinates,
                        st.session_state.extraction_results
                    )
                    
                    st_folium(
                        property_map, 
                        width=None, 
                        height=600,
                        returned_objects=[]
                    )
                    
                    # Display coordinate table
                    st.subheader("📊 Coordinate Details")
                    
                    import pandas as pd
                    
                    # Create DataFrame for display
                    coord_data = []
                    for idx, coord in enumerate(st.session_state.converted_coordinates, 1):
                        coord_data.append({
                            'Point': idx,
                            'Easting (m)': f"{coord['easting']:.2f}",
                            'Northing (m)': f"{coord['northing']:.2f}",
                            'Latitude (°)': f"{coord['latitude']:.6f}",
                            'Longitude (°)': f"{coord['longitude']:.6f}"
                        })
                    
                    df = pd.DataFrame(coord_data)
                    st.dataframe(df, use_container_width=True, hide_index=True)
                    
                    # Download option
                    csv = df.to_csv(index=False)
                    st.download_button(
                        label="📥 Download Coordinates as CSV",
                        data=csv,
                        file_name=f"coordinates_{st.session_state.extraction_results.get('survey_number', 'survey')}.csv",
                        mime="text/csv"
                    )
    
    else:
        # No file uploaded yet
        st.info("👆 Upload a survey plan image to get started")
    
    # Footer with disclaimer
    st.markdown("---")
    st.markdown(
        """
        <div style="
            background-color: #fff3cd;
            border: 2px solid #ffc107;
            border-radius: 0.5rem;
            padding: 1.5rem;
            margin-top: 2rem;
        ">
            <h4 style="margin: 0 0 0.5rem 0; color: #856404;">
                ⚠️ Disclaimer
            </h4>
            <p style="margin: 0; color: #856404;">
                <strong>This tool is for informational use only and does not constitute 
                legal confirmation of land ownership or boundaries.</strong> Always consult 
                with qualified surveyors and legal professionals before making any land 
                purchase or development decisions. The coordinate conversions and data 
                extractions are based on automated processing and should be independently 
                verified.
            </p>
        </div>
        """,
        unsafe_allow_html=True
    )
    
    # Footer
    st.markdown(
        """
        <div style="text-align: center; color: #666; padding: 2rem 0 1rem 0;">
            <p>Built with ❤️ for the Nigerian Real Estate Market</p>
        </div>
        """,
        unsafe_allow_html=True
    )


if __name__ == "__main__":
    main()
