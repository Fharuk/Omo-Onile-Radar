"""
Omo-Onile Radar - Real Estate Due Diligence Tool for Nigerian Market

A Streamlit application that uses AI-powered OCR to extract survey plan data,
transform coordinates from Nigerian Minna Datum to WGS84, visualize property
boundaries on an interactive map, and perform intelligent risk detection.
"""

import streamlit as st
import folium
from streamlit_folium import st_folium
from typing import Optional, Dict, Any, List
import logging
import pandas as pd
from datetime import datetime
from utils.ocr import extract_survey_data, OCRError, OCRValidationError, format_coordinates_summary
from utils.geo import (
    CoordinateManager, 
    CoordinateTransformationError, 
    CoordinateValidationError
)
from utils.risk_engine import RiskRadar, RiskAnalysisError, CoordinateValidationError as RiskCoordinateValidationError
from utils import db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize database
try:
    db.init_db()
except Exception as e:
    st.error(f"Critical Error: Failed to initialize database. {str(e)}")
    logger.critical("Database initialization failed: %s", e)

# Page configuration
st.set_page_config(
    page_title="Omo-Onile Radar",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize coordinate manager and risk radar
@st.cache_resource
def get_coordinate_manager() -> CoordinateManager:
    """Initialize and cache the coordinate manager."""
    return CoordinateManager()

@st.cache_resource
def get_risk_radar() -> RiskRadar:
    """Initialize and cache the risk radar."""
    return RiskRadar()


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
    if 'demo_mode' not in st.session_state:
        st.session_state.demo_mode = False
    if 'risk_assessment' not in st.session_state:
        st.session_state.risk_assessment = None
    if 'is_admin' not in st.session_state:
        st.session_state.is_admin = False
    if 'show_form' not in st.session_state:
        st.session_state.show_form = False
    if 'form_submitted' not in st.session_state:
        st.session_state.form_submitted = False
    if 'request_id' not in st.session_state:
        st.session_state.request_id = None


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
    st.sidebar.divider()
    st.sidebar.markdown("🔐 **Admin Access**")
    admin_password = st.sidebar.text_input(
        "Admin Password", 
        type="password", 
        key="admin_pwd",
        help="Enter admin password to access lead dashboard"
    )
    
    if admin_password == db.ADMIN_PASSWORD:
        st.session_state.is_admin = True
        st.sidebar.success("✅ Admin Authenticated")
        if st.sidebar.button("Logout"):
            # Clear password to logout
            st.session_state.is_admin = False
            # We can't easily clear the text_input from here without rerunning or using a different key
            # but setting is_admin to False is enough if we check it.
            # Actually, to logout we might need to reset the text_input value if possible, 
            # but Streamlit doesn't allow easy programmatic reset of widgets except by changing key.
            # A simple way is just to tell user to clear the password field.
            st.info("Please clear the password field to logout.")
        return # Hide other sidebar content

    st.session_state.is_admin = False
    
    st.sidebar.title("⚙️ Configuration")
    
    # Demo Mode Toggle
    st.sidebar.subheader("🧪 Demo Mode")
    demo_mode = st.sidebar.checkbox(
        "Use Demo Data (No API Key Required)",
        value=st.session_state.demo_mode,
        help="Demo mode uses test coordinates that trigger risk alerts"
    )
    
    if demo_mode != st.session_state.demo_mode:
        st.session_state.demo_mode = demo_mode
        st.session_state.file_processed = False
        st.session_state.risk_assessment = None
    
    if st.session_state.demo_mode:
        st.sidebar.info("🧪 Using demo coordinates that overlap with restricted zones")
    
    st.sidebar.markdown("---")
    
    # API Key Input (disabled in demo mode)
    st.sidebar.subheader("OpenAI API Key")
    api_key_disabled = st.session_state.demo_mode
    api_key_help = (
        "Demo mode active - API key not required" if api_key_disabled
        else "Your API key is required to process survey plans with AI"
    )
    
    api_key_input = st.sidebar.text_input(
        "Enter your OpenAI API key",
        type="password",
        value=st.session_state.api_key,
        disabled=api_key_disabled,
        help=api_key_help
    )
    
    if not api_key_disabled and api_key_input != st.session_state.api_key:
        st.session_state.api_key = api_key_input
        st.session_state.file_processed = False
    
    if st.session_state.demo_mode:
        st.sidebar.success("🧪 Demo Mode Active")
    elif st.session_state.api_key:
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
        st.session_state.risk_assessment = None
    
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
        4. 🚨 **NEW: Intelligent risk detection for government zones**
        
        **Features:**
        - ⚠️ Government acquisition zone detection
        - 🛡️ Military reserve identification
        - 🌊 Waterfront restriction alerts
        - 🧪 Demo mode for testing without API
        
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


def render_risk_alert(risk_result: Dict[str, Any]):
    """
    Display risk assessment alerts based on the result.
    
    Args:
        risk_result: Risk assessment result from RiskRadar
    """
    status = risk_result.get('status', 'SAFE')
    message = risk_result.get('message', '')
    intersections = risk_result.get('intersections', [])
    recommendations = risk_result.get('recommendations', [])
    
    if status == 'DANGER':
        st.error(
            f"🚨 **CRITICAL RISK ALERT** 🚨\n\n"
            f"{message}\n\n"
            f"**Immediate Actions Required:**\n"
            + "\n".join([f"• {rec}" for rec in recommendations[:3]])
        )
        
        # Show intersection details if available
        if intersections:
            st.markdown("**⚠️ Intersecting Zones:**")
            for intersection in intersections:
                st.markdown(
                    f"- **{intersection['zone_name']}**\n"
                    f"  - Type: {intersection['zone_type']}\n"
                    f"  - Overlap: {intersection['overlap_percentage']}%\n"
                    f"  - Severity: {intersection['severity']}"
                )
                
    elif status == 'CAUTION':
        st.warning(
            f"⚠️ **CAUTION: Potential Risk Detected** ⚠️\n\n"
            f"{message}\n\n"
            f"**Recommendations:**\n"
            + "\n".join([f"• {rec}" for rec in recommendations[:2]])
        )
        
    else:  # SAFE
        st.success(
            f"✅ **Preliminary Risk Assessment: SAFE**\n\n"
            f"{message}\n\n"
            f"**Note:** Government records are manually maintained. "
            f"Request official verification for final confirmation."
        )


def display_extraction_results(results: Dict[str, Any]):
    """
    Display extracted survey data in a user-friendly format.
    
    Args:
        results: Dictionary containing extracted survey data
    """
    st.subheader("📄 Survey Information")
    
    # Check if demo mode
    if results.get('demo_mode', False):
        st.info("🧪 **Demo Mode - Test Data**")
    
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


def create_enhanced_map_visualization(
    converted_coords: List[Dict[str, float]], 
    survey_info: Dict[str, Any],
    risk_result: Optional[Dict[str, Any]] = None
) -> folium.Map:
    """
    Create a Folium map with property boundaries, government zones, and risk visualization.
    
    Args:
        converted_coords: List of converted coordinates with lat/lon
        survey_info: Survey metadata for marker tooltips
        risk_result: Risk assessment result for zone visualization
    
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
        zoom_start = 12
    
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
    
    # Add government zones layer
    risk_radar = get_risk_radar()
    all_zones = risk_radar.get_all_zones()
    
    zone_group = folium.FeatureGroup(name="🚨 Government Restricted Zones")
    
    for zone_id, zone_data in all_zones.items():
        coordinates = zone_data['coordinates']
        polygon_coords = [[coord[1], coord[0]] for coord in coordinates]  # Convert (lon, lat) to (lat, lon)
        polygon_coords.append(polygon_coords[0])  # Close polygon
        
        # Color based on severity
        if zone_data['severity_level'] == 'HIGH':
            color = 'red'
            fill_color = 'red'
        else:
            color = 'orange'
            fill_color = 'orange'
        
        # Create popup content
        popup_html = f"""
        <div style="font-family: Arial, sans-serif; min-width: 250px;">
            <h4 style="margin: 0 0 10px 0; color: #d32f2f;">{zone_data['zone_name']}</h4>
            <table style="width: 100%;">
                <tr><td><b>Type:</b></td><td>{zone_data['zone_type']}</td></tr>
                <tr><td><b>Severity:</b></td><td>{zone_data['severity_level']}</td></tr>
                <tr><td><b>Acquired:</b></td><td>{zone_data['acquisition_date']}</td></tr>
                <tr><td colspan="2" style="padding-top: 10px; border-top: 1px solid #ccc;">
                    <i>{zone_data['description']}</i>
                </td></tr>
            </table>
        </div>
        """
        
        folium.Polygon(
            locations=polygon_coords,
            color=color,
            fill=True,
            fill_color=fill_color,
            fill_opacity=0.2,
            weight=3,
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=f"{zone_data['zone_name']} ({zone_data['zone_type']})"
        ).add_to(zone_group)
    
    zone_group.add_to(m)
    
    if not converted_coords:
        folium.LayerControl().add_to(m)
        return m
    
    # Extract lat/lon pairs for polygon
    polygon_points = [
        [coord['latitude'], coord['longitude']] 
        for coord in converted_coords
    ]
    
    # Close the polygon by adding the first point at the end
    if len(polygon_points) > 2:
        polygon_points.append(polygon_points[0])
    
    # Draw user land polygon
    user_land_group = folium.FeatureGroup(name="🏠 Your Property")
    
    folium.Polygon(
        locations=polygon_points,
        color='blue',
        fill=True,
        fill_color='cyan',
        fill_opacity=0.5,
        weight=2,
        popup=f"Survey: {survey_info.get('survey_number', 'Unknown')}"
    ).add_to(user_land_group)
    
    # Add markers for each corner
    for idx, coord in enumerate(converted_coords, 1):
        # Create popup content
        popup_html = f"""
        <div style="font-family: Arial, sans-serif; min-width: 200px;">
            <h4 style="margin: 0 0 10px 0;">Property Corner {idx}</h4>
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
            tooltip=f"Corner {idx}",
            icon=folium.Icon(color='blue', icon='home')
        ).add_to(user_land_group)
    
    user_land_group.add_to(m)
    
    # Add intersection highlighting if risk detected
    if risk_result and risk_result.get('intersections'):
        intersection_group = folium.FeatureGroup(name="⚠️ Intersection Areas")
        
        for intersection in risk_result['intersections']:
            # This would require calculating the actual intersection geometry
            # For now, we'll add a marker at the centroid of the user property
            if polygon_points:
                centroid_lat = sum(point[0] for point in polygon_points[:-1]) / len(polygon_points[:-1])
                centroid_lon = sum(point[1] for point in polygon_points[:-1]) / len(polygon_points[:-1])
                
                folium.Marker(
                    location=[centroid_lat, centroid_lon],
                    popup=f"Intersection with {intersection['zone_name']}",
                    tooltip=f"Overlap: {intersection['overlap_percentage']}%",
                    icon=folium.Icon(color='red', icon='warning-sign')
                ).add_to(intersection_group)
        
        intersection_group.add_to(m)
    
    # Add layer control
    folium.LayerControl().add_to(m)
    
    return m


def process_survey_image(image_bytes: bytes, api_key: str, use_demo: bool = False) -> Optional[Dict[str, Any]]:
    """
    Process the uploaded survey image and extract data.
    
    Args:
        image_bytes: Raw image bytes
        api_key: OpenAI API key
        use_demo: Whether to use demo mode
    
    Returns:
        Extracted survey data or None if processing fails
    """
    try:
        with st.spinner("🔍 Analyzing document with AI..." if not use_demo else "🧪 Processing demo data..."):
            results = extract_survey_data(image_bytes, api_key, use_demo_data=use_demo)
            
            if 'error' in results:
                st.error(f"❌ Error processing: {results['error']}")
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


def perform_risk_assessment(
    converted_coords: List[Dict[str, float]], 
    risk_radar: RiskRadar
) -> Optional[Dict[str, Any]]:
    """
    Perform risk assessment on converted coordinates.
    
    Args:
        converted_coords: List of converted coordinates with lat/lon
        risk_radar: RiskRadar instance
    
    Returns:
        Risk assessment result or None if assessment fails
    """
    try:
        with st.spinner("🚨 Analyzing risk factors..."):
            # Extract coordinate pairs for risk analysis
            land_coordinates = [
                (coord['latitude'], coord['longitude']) 
                for coord in converted_coords
            ]
            
            risk_result = risk_radar.check_intersection(land_coordinates)
            logger.info(f"Risk assessment complete: {risk_result['status']}")
            return risk_result
            
    except RiskCoordinateValidationError as e:
        st.error(f"❌ Risk Assessment Validation Error: {str(e)}")
        logger.error(f"Risk validation error: {str(e)}")
        return None
        
    except RiskAnalysisError as e:
        st.error(f"❌ Risk Assessment Error: {str(e)}")
        logger.error(f"Risk analysis error: {str(e)}")
        return None
        
    except Exception as e:
        st.error(f"❌ Unexpected error during risk assessment: {str(e)}")
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return None


def render_admin_dashboard():
    """Render the admin dashboard for managing leads."""
    st.header("👨‍💼 Admin Dashboard")
    
    try:
        requests = db.get_all_requests()
    except Exception as e:
        st.error(f"Error fetching requests: {e}")
        return

    # Metric cards
    total_leads = len(requests)
    pending_leads = len([r for r in requests if r['status'] == 'PENDING'])
    contacted_leads = len([r for r in requests if r['status'] == 'CONTACTED'])
    completed_leads = len([r for r in requests if r['status'] == 'COMPLETED'])
    
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Leads", total_leads)
    m2.metric("Pending Leads", pending_leads)
    m3.metric("Contacted", contacted_leads)
    m4.metric("Completed", completed_leads)
    
    if not requests:
        st.info("No lead requests found yet.")
        return

    # Create DataFrame for display
    df = pd.DataFrame(requests)
    
    # Format risk status for display
    def format_risk(status):
        if status == 'DANGER': return "🔴 DANGER"
        if status == 'CAUTION': return "🟡 CAUTION"
        if status == 'SAFE': return "🟢 SAFE"
        return status

    display_df = df.copy()
    display_df['risk_status'] = display_df['risk_status'].apply(format_risk)
    
    # Reorder and rename columns for nice display
    column_mapping = {
        'id': 'ID',
        'name': 'Name',
        'phone': 'Phone',
        'email': 'Email',
        'survey_plan_number': 'Survey #',
        'risk_status': 'Risk Status',
        'location_text': 'Location',
        'status': 'Status',
        'timestamp': 'Timestamp',
        'notes': 'Notes'
    }
    # Only include columns that exist in the mapping
    available_cols = [col for col in column_mapping.keys() if col in display_df.columns]
    display_df = display_df[available_cols].rename(columns={col: column_mapping[col] for col in available_cols})
    
    st.subheader("All Lead Requests")
    st.dataframe(display_df, use_container_width=True, hide_index=True)
    
    st.divider()
    st.subheader("Update Lead Status")
    
    # Update Status Section
    with st.expander("📝 Edit Lead Status", expanded=True):
        col1, col2, col3 = st.columns([1, 2, 3])
        with col1:
            lead_id = st.number_input("Lead ID", min_value=1, step=1)
        with col2:
            new_status = st.selectbox(
                "New Status", 
                options=["PENDING", "CONTACTED", "COMPLETED", "REJECTED"]
            )
        with col3:
            admin_notes = st.text_input("Admin Notes")
            
        if st.button("Save Changes"):
            update_res = db.update_request_status(lead_id, new_status, admin_notes)
            if update_res['success']:
                st.success(f"Lead #{lead_id} updated successfully!")
                st.rerun()
            else:
                st.error(update_res['message'])


def render_lead_form(extraction_results: Dict[str, Any], risk_assessment: Dict[str, Any]):
    """
    Render the lead capture form for surveyor verification.
    """
    st.divider()
    st.subheader("⚡ Need 100% Certainty?")
    st.write("Our AI assessment is helpful but not legally binding. Get peace of mind with professional verification from our partner surveyors.")
    
    if not st.session_state.show_form and not st.session_state.form_submitted:
        if st.button("📋 Request Official Surveyor Charting (₦15,000)", type="primary"):
            st.session_state.show_form = True
            st.rerun()
    
    if st.session_state.show_form and not st.session_state.form_submitted:
        with st.form("surveyor_request_form"):
            st.markdown("### Verification Request Form")
            name = st.text_input("Full Name", placeholder="John Doe", key="req_name_input")
            phone = st.text_input("Phone Number", placeholder="+234 901 234 5678", key="req_phone_input")
            email = st.text_input("Email Address", placeholder="john@example.com", key="req_email_input")
            
            # Hidden data collected from results
            survey_plan_number = extraction_results.get('survey_number') if extraction_results else None
            risk_status = risk_assessment.get('status') if risk_assessment else 'PENDING'
            location_text = extraction_results.get('location_text') if extraction_results else None
            
            submit_button = st.form_submit_button("Submit Request")
            
            if submit_button:
                # Basic empty check for name, phone, email
                if not name or not phone or not email:
                    st.error("Please fill in all required fields.")
                else:
                    result = db.save_request(
                        name=name,
                        phone=phone,
                        email=email,
                        survey_plan_number=survey_plan_number,
                        risk_status=risk_status,
                        location_text=location_text
                    )
                    
                    if result['success']:
                        st.session_state.form_submitted = True
                        st.session_state.request_id = result['id']
                        st.session_state.show_form = False
                        st.rerun()
                    else:
                        st.error(f"Failed to submit request: {result['message']}")
                    
    elif st.session_state.form_submitted:
        st.success(f"""
        ✅ **Request Received!**
        
        Thank you for choosing Omo-Onile Radar. A partner surveyor will contact you 
        on WhatsApp within 24 hours at your provided phone number.
        
        Reference ID: **{st.session_state.request_id}**
        """)
        if st.button("Submit Another Request"):
            st.session_state.form_submitted = False
            st.session_state.show_form = False
            st.session_state.request_id = None
            st.rerun()


def main():
    """Main application entry point."""
    # Initialize session state
    initialize_session_state()
    
    # Render sidebar
    render_sidebar()
    
    # Check if admin is logged in
    if st.session_state.get('is_admin', False):
        render_admin_dashboard()
        return

    # Main content area
    st.title("🗺️ Omo-Onile Radar")
    st.markdown(
        "### Intelligent Real Estate Due Diligence Tool for Nigerian Market\n"
        "Upload a survey plan to extract data, convert coordinates, visualize boundaries, and **detect government zone intersections**."
    )
    
    st.markdown("---")
    
    # Check if we can proceed (API key or demo mode)
    if not st.session_state.api_key and not st.session_state.demo_mode:
        st.warning("⚠️ Please enter your OpenAI API key in the sidebar or enable demo mode to continue.")
        st.info(
            "👉 Don't have an API key? Get one from [OpenAI Platform](https://platform.openai.com/api-keys)"
        )
        return
    
    # File uploader or demo mode indicator
    if st.session_state.demo_mode:
        st.info("🧪 **Demo Mode Active** - Using test data to demonstrate risk detection capabilities")
        st.markdown(
            """
            **Demo coordinates will:**
            - Show land that overlaps with Lekki Government Acquisition Zone
            - Trigger a DANGER risk alert
            - Demonstrate the full risk assessment workflow
            """
        )
    else:
        st.subheader("📤 Upload Survey Plan")
        uploaded_file = st.file_uploader(
            "Choose a survey plan image",
            type=['png', 'jpg', 'jpeg'],
            help="Upload a clear image of the survey plan document"
        )
    
    # Process based on mode
    if st.session_state.demo_mode:
        # Demo mode processing
        if not st.session_state.file_processed:
            if st.button("🚀 Analyze Demo Data", type="primary", use_container_width=True):
                st.session_state.file_processed = False
                st.session_state.extraction_results = None
                st.session_state.converted_coordinates = None
                st.session_state.risk_assessment = None
                
                # Process demo data
                extraction_results = process_survey_image(b'', '', use_demo=True)
                
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
                st.warning("⚠️ No coordinates were found in the demo data.")
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
                
                # Perform risk assessment
                if st.session_state.converted_coordinates and not st.session_state.risk_assessment:
                    risk_radar = get_risk_radar()
                    risk_result = perform_risk_assessment(
                        st.session_state.converted_coordinates,
                        risk_radar
                    )
                    
                    if risk_result:
                        st.session_state.risk_assessment = risk_result
                
                # Display risk assessment
                if st.session_state.risk_assessment:
                    st.subheader("🚨 Risk Assessment")
                    render_risk_alert(st.session_state.risk_assessment)
                    st.markdown("---")
                
                # Display map if coordinates are converted
                if st.session_state.converted_coordinates:
                    st.subheader("🗺️ Property & Risk Visualization")
                    
                    # Create and display map
                    property_map = create_enhanced_map_visualization(
                        st.session_state.converted_coordinates,
                        st.session_state.extraction_results,
                        st.session_state.risk_assessment
                    )
                    
                    st_folium(
                        property_map, 
                        width=None, 
                        height=600,
                        returned_objects=[]
                    )
                    
                    # Display coordinate table
                    st.subheader("📊 Coordinate Details")
                    
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
                        file_name=f"coordinates_{st.session_state.extraction_results.get('survey_number', 'demo')}.csv",
                        mime="text/csv"
                    )

                    # Lead capture form
                    render_lead_form(st.session_state.extraction_results, st.session_state.risk_assessment)
    else:
        # Regular file upload mode
        uploaded_file = st.session_state.uploaded_file
        
        if uploaded_file:
            # Check if this is a new file
            file_id = f"{uploaded_file.name}_{uploaded_file.size}"
            if st.session_state.uploaded_file != file_id:
                st.session_state.uploaded_file = file_id
                st.session_state.file_processed = False
                st.session_state.extraction_results = None
                st.session_state.converted_coordinates = None
                st.session_state.risk_assessment = None
            
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
                st.session_state.risk_assessment = None
            
            # Process the file if not already processed
            if not st.session_state.file_processed:
                # Read image bytes
                image_bytes = uploaded_file.read()
                uploaded_file.seek(0)  # Reset file pointer
                
                # Extract survey data
                extraction_results = process_survey_image(
                    image_bytes, 
                    st.session_state.api_key,
                    use_demo=False
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
                    
                    # Perform risk assessment
                    if st.session_state.converted_coordinates and not st.session_state.risk_assessment:
                        risk_radar = get_risk_radar()
                        risk_result = perform_risk_assessment(
                            st.session_state.converted_coordinates,
                            risk_radar
                        )
                        
                        if risk_result:
                            st.session_state.risk_assessment = risk_result
                    
                    # Display risk assessment
                    if st.session_state.risk_assessment:
                        st.subheader("🚨 Risk Assessment")
                        render_risk_alert(st.session_state.risk_assessment)
                        st.markdown("---")
                    
                    # Display map if coordinates are converted
                    if st.session_state.converted_coordinates:
                        st.subheader("🗺️ Property & Risk Visualization")
                        
                        # Create and display map
                        property_map = create_enhanced_map_visualization(
                            st.session_state.converted_coordinates,
                            st.session_state.extraction_results,
                            st.session_state.risk_assessment
                        )
                        
                        st_folium(
                            property_map, 
                            width=None, 
                            height=600,
                            returned_objects=[]
                        )
                        
                        # Display coordinate table
                        st.subheader("📊 Coordinate Details")
                        
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
                        
                        # Lead capture form
                        render_lead_form(st.session_state.extraction_results, st.session_state.risk_assessment)
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
                verified. Risk assessment powered by geometric analysis. 
                Verify with official sources before decisions.
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
            <p><em>Now with Intelligent Risk Detection</em></p>
            <p><small><strong>Lead Capture Note:</strong> Your information is securely stored and used only for surveyor coordination. We respect your privacy.</small></p>
        </div>
        """,
        unsafe_allow_html=True
    )


if __name__ == "__main__":
    main()