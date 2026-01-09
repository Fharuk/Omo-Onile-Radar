"""
Risk Detection Engine for Omo-Onile Radar.

This module provides intelligent geospatial risk analysis capabilities, including
government zone intersection detection and land acquisition risk assessment.
"""

import logging
from typing import Dict, List, Tuple, Optional, Any
from shapely.geometry import Polygon
from shapely.errors import GEOSException

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RiskAnalysisError(Exception):
    """Custom exception for risk analysis errors."""
    pass


class CoordinateValidationError(Exception):
    """Custom exception for coordinate validation errors."""
    pass


# Constants for risk thresholds
DANGER_THRESHOLD = 20  # Percentage overlap for DANGER status
CAUTION_THRESHOLD = 5   # Percentage overlap for CAUTION status


class RiskRadar:
    """
    Intelligent risk detection engine for land acquisition analysis.
    
    This class provides methods to detect intersections between land properties
    and known government restricted zones, military areas, and other risk zones.
    """
    
    # Mock Government Acquisition Database
    # These coordinates represent realistic restricted zones in Lagos, Nigeria
    GOVERNMENT_ZONES = {
        'lekki_gov_acquisition': {
            'zone_id': 'gov_001',
            'zone_name': 'Lekki Government Acquisition Zone',
            'zone_type': 'Government Acquisition',
            'acquisition_date': '2006-01-01',
            'severity_level': 'HIGH',
            'coordinates': [
                (3.503, 6.447),  # Southwest
                (3.558, 6.447),  # Southeast  
                (3.558, 6.401),  # Northeast
                (3.503, 6.401)   # Northwest
            ],
            'description': 'Federal government acquisition zone covering Lekki Peninsula'
        },
        'vi_waterfront': {
            'zone_id': 'gov_002', 
            'zone_name': 'Victoria Island Waterfront Restriction',
            'zone_type': 'Waterfront Restriction',
            'acquisition_date': '2010-05-15',
            'severity_level': 'MEDIUM',
            'coordinates': [
                (3.390, 6.445),
                (3.410, 6.445),
                (3.410, 6.465),
                (3.390, 6.465)
            ],
            'description': 'Coastal protection and waterfront development restrictions'
        },
        'ikeja_military': {
            'zone_id': 'gov_003',
            'zone_name': 'Ikeja Military Reserve',
            'zone_type': 'Military Reserve',
            'acquisition_date': '1995-03-20',
            'severity_level': 'HIGH',
            'coordinates': [
                (3.320, 6.580),
                (3.340, 6.580),
                (3.340, 6.600),
                (3.320, 6.600)
            ],
            'description': 'Nigerian Air Force military installation and buffer zone'
        },
        'badagry_creek': {
            'zone_id': 'gov_004',
            'zone_name': 'Badagry Creek Environmental Protection',
            'zone_type': 'Environmental Protection',
            'acquisition_date': '2015-08-10',
            'severity_level': 'MEDIUM',
            'coordinates': [
                (2.900, 6.400),
                (2.950, 6.400),
                (2.950, 6.450),
                (2.900, 6.450)
            ],
            'description': 'Environmental protection zone for Badagry Creek ecosystem'
        }
    }
    
    def __init__(self):
        """Initialize the RiskRadar with cached zone polygons."""
        self._zone_polygons: Dict[str, Polygon] = {}
        self._initialize_zone_polygons()
    
    def _initialize_zone_polygons(self) -> None:
        """Initialize Shapely Polygon objects for all government zones."""
        for zone_id, zone_data in self.GOVERNMENT_ZONES.items():
            try:
                coordinates = zone_data['coordinates']
                # Convert from (lon, lat) to (lat, lon) for Shapely if needed
                polygon_coords = [(coord[1], coord[0]) for coord in coordinates]
                polygon = Polygon(polygon_coords)
                
                if polygon.is_valid:
                    self._zone_polygons[zone_id] = polygon
                    logger.info(f"Initialized polygon for zone: {zone_data['zone_name']}")
                else:
                    logger.warning(f"Invalid polygon for zone: {zone_data['zone_name']}")
                    
            except Exception as e:
                logger.error(f"Failed to create polygon for zone {zone_id}: {str(e)}")
    
    def _validate_wgs84_coordinates(self, coordinates: List[Tuple[float, float]]) -> Tuple[bool, Optional[str]]:
        """
        Validate that coordinates are within valid WGS84 ranges for Nigeria.
        
        Args:
            coordinates: List of (lat, lon) tuples
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not coordinates:
            return False, "No coordinates provided"
        
        if len(coordinates) < 3:
            return False, "At least 3 coordinates required to form a polygon"
        
        for idx, (lat, lon) in enumerate(coordinates):
            # Validate coordinate ranges for Nigeria
            if not (3.0 <= lat <= 15.0):
                return False, f"Latitude {lat} at index {idx} is outside Nigeria's bounds (3.0-15.0)"
            
            if not (2.5 <= lon <= 16.0):
                return False, f"Longitude {lon} at index {idx} is outside Nigeria's bounds (2.5-16.0)"
            
            # Check for NaN or infinity
            if not (float('-inf') < lat < float('inf')):
                return False, f"Invalid latitude {lat} at index {idx}"
            
            if not (float('-inf') < lon < float('inf')):
                return False, f"Invalid longitude {lon} at index {idx}"
        
        return True, None
    
    def _calculate_overlap_percentage(self, land_polygon: Polygon, zone_polygon: Polygon) -> float:
        """
        Calculate the percentage overlap between two polygons.
        
        Args:
            land_polygon: The land property polygon
            zone_polygon: The government zone polygon
            
        Returns:
            Percentage overlap (0.0 to 100.0)
        """
        try:
            if not land_polygon.is_valid or not zone_polygon.is_valid:
                return 0.0
            
            intersection = land_polygon.intersection(zone_polygon)
            
            if intersection.is_empty:
                return 0.0
            
            land_area = land_polygon.area
            intersection_area = intersection.area
            
            if land_area <= 0:
                return 0.0
            
            return (intersection_area / land_area) * 100
            
        except GEOSException:
            logger.warning("GEOS exception during overlap calculation")
            return 0.0
        except Exception as e:
            logger.error(f"Error calculating overlap percentage: {str(e)}")
            return 0.0
    
    def check_intersection(
        self, 
        land_coordinates: List[Tuple[float, float]], 
        zone_filter: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Check for intersections between land coordinates and government restricted zones.
        
        Args:
            land_coordinates: List of (lat, lon) tuples representing land vertices in WGS84
            zone_filter: Specific zone ID to check, or None to check all zones
            
        Returns:
            Dictionary containing:
                - status: 'DANGER', 'CAUTION', or 'SAFE'
                - message: Risk assessment message
                - intersections: List of intersection details
                - recommendations: List of recommendations
                
        Raises:
            CoordinateValidationError: If coordinates are invalid
            RiskAnalysisError: If risk analysis fails
        """
        try:
            # Validate input coordinates
            is_valid, error_msg = self._validate_wgs84_coordinates(land_coordinates)
            if not is_valid:
                raise CoordinateValidationError(error_msg)
            
            # Create Shapely Polygon from land coordinates
            try:
                land_polygon = Polygon(land_coordinates)
                if not land_polygon.is_valid:
                    raise CoordinateValidationError("Land coordinates form an invalid polygon")
            except GEOSException as e:
                raise CoordinateValidationError(f"Invalid polygon geometry: {str(e)}")
            
            # Determine which zones to check
            zones_to_check = (
                {zone_filter: self.GOVERNMENT_ZONES[zone_filter]} 
                if zone_filter and zone_filter in self.GOVERNMENT_ZONES 
                else self.GOVERNMENT_ZONES
            )
            
            intersections = []
            max_severity = 0
            
            # Check intersection with each zone
            for zone_id, zone_data in zones_to_check.items():
                if zone_id not in self._zone_polygons:
                    logger.warning(f"Zone polygon not available for {zone_id}")
                    continue
                
                zone_polygon = self._zone_polygons[zone_id]
                
                try:
                    # Check if polygons intersect
                    if land_polygon.intersects(zone_polygon):
                        overlap_percentage = self._calculate_overlap_percentage(land_polygon, zone_polygon)
                        
                        # Determine severity based on zone type and overlap
                        severity_score = self._calculate_severity_score(zone_data, overlap_percentage)
                        max_severity = max(max_severity, severity_score)
                        
                        intersection_info = {
                            'zone_id': zone_data['zone_id'],
                            'zone_name': zone_data['zone_name'],
                            'zone_type': zone_data['zone_type'],
                            'severity': zone_data['severity_level'],
                            'overlap_percentage': round(overlap_percentage, 2),
                            'intersection_area': round(land_polygon.intersection(zone_polygon).area, 6),
                            'acquisition_date': zone_data['acquisition_date'],
                            'description': zone_data['description']
                        }
                        intersections.append(intersection_info)
                        
                        logger.info(
                            f"Intersection detected with {zone_data['zone_name']}: "
                            f"{overlap_percentage:.2f}% overlap"
                        )
                        
                except GEOSException:
                    logger.warning(f"GEOS error checking intersection with zone {zone_id}")
                    continue
                except Exception as e:
                    logger.error(f"Error checking intersection with zone {zone_id}: {str(e)}")
                    continue
            
            # Determine overall risk status
            status, message, recommendations = self._determine_risk_status(intersections, max_severity)
            
            result = {
                'status': status,
                'message': message,
                'intersections': intersections,
                'recommendations': recommendations
            }
            
            logger.info(f"Risk analysis complete: {status} with {len(intersections)} intersections")
            return result
            
        except CoordinateValidationError:
            # Re-raise validation errors
            raise
        except Exception as e:
            error_msg = f"Risk analysis failed: {str(e)}"
            logger.error(error_msg)
            raise RiskAnalysisError(error_msg)
    
    def _calculate_severity_score(self, zone_data: Dict, overlap_percentage: float) -> int:
        """
        Calculate a severity score based on zone type and overlap percentage.
        
        Args:
            zone_data: Zone information dictionary
            overlap_percentage: Percentage of overlap
            
        Returns:
            Severity score (1-5, where 5 is highest)
        """
        base_severity = {
            'Government Acquisition': 5,
            'Military Reserve': 5,
            'Waterfront Restriction': 3,
            'Environmental Protection': 2
        }.get(zone_data['zone_type'], 3)
        
        # Increase severity based on overlap percentage
        if overlap_percentage > DANGER_THRESHOLD:
            overlap_multiplier = 1.5
        elif overlap_percentage > CAUTION_THRESHOLD:
            overlap_multiplier = 1.2
        else:
            overlap_multiplier = 1.0
        
        return min(5, int(base_severity * overlap_multiplier))
    
    def _determine_risk_status(
        self, 
        intersections: List[Dict], 
        max_severity: int
    ) -> Tuple[str, str, List[str]]:
        """
        Determine overall risk status based on intersections found.
        
        Args:
            intersections: List of intersection details
            max_severity: Maximum severity score from all intersections
            
        Returns:
            Tuple of (status, message, recommendations)
        """
        if not intersections:
            return 'SAFE', "No intersections with known restricted zones detected.", [
                "Preliminary risk assessment appears favorable",
                "Recommend verifying with Lagos State Land Bureau for official confirmation",
                "Ensure all necessary permits and approvals are obtained"
            ]
        
        # Check for high-severity intersections
        high_severity_zones = [
            intersection for intersection in intersections 
            if intersection['zone_type'] in ['Government Acquisition', 'Military Reserve']
        ]
        
        if high_severity_zones:
            zone_name = high_severity_zones[0]['zone_name']
            return 'DANGER', f"CRITICAL: Land overlaps with {zone_name}.", [
                "URGENT: Contact Lagos State Land Bureau immediately",
                "Verify official land status with Federal Ministry of Works",
                "Engage qualified legal counsel specializing in land acquisition",
                "Consider alternative properties outside restricted zones"
            ]
        
        # Check for significant overlap with any zone
        significant_overlaps = [
            intersection for intersection in intersections
            if intersection['overlap_percentage'] > DANGER_THRESHOLD
        ]
        
        if significant_overlaps:
            return 'DANGER', f"High overlap percentage ({significant_overlaps[0]['overlap_percentage']:.1f}%) with restricted zone.", [
                "Consult with Lagos State Land Bureau",
                "Engage professional land surveyor for verification",
                "Review property title documentation thoroughly",
                "Consider renegotiating purchase terms"
            ]
        
        # Otherwise, it's a caution
        total_overlap = sum(intersection['overlap_percentage'] for intersection in intersections)
        return 'CAUTION', f"Potential risk detected. {len(intersections)} zone(s) nearby with {total_overlap:.1f}% total overlap.", [
            "Verify exact boundaries with official sources",
            "Consult local land registry office",
            "Request additional documentation from seller",
            "Consider professional land survey before purchase"
        ]
    
    @staticmethod
    def get_zone_info(zone_id: str) -> Optional[Dict]:
        """
        Get information about a specific government zone.
        
        Args:
            zone_id: The zone identifier
            
        Returns:
            Zone information dictionary or None if not found
        """
        return RiskRadar.GOVERNMENT_ZONES.get(zone_id)
    
    @staticmethod
    def get_all_zones() -> Dict[str, Dict]:
        """
        Get all government zones in the database.
        
        Returns:
            Dictionary of all zone information
        """
        return RiskRadar.GOVERNMENT_ZONES.copy()
    
    def get_zones_by_type(self, zone_type: str) -> List[Dict]:
        """
        Get all zones of a specific type.
        
        Args:
            zone_type: The type of zones to retrieve
            
        Returns:
            List of zone information dictionaries
        """
        return [
            zone_data for zone_data in self.GOVERNMENT_ZONES.values()
            if zone_data['zone_type'] == zone_type
        ]