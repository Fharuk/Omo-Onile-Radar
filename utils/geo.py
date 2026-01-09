"""
Coordinate transformation module for Nigerian Minna Datum to WGS84 conversion.

This module handles the conversion of coordinates from the Nigerian Minna Datum
(EPSG:26331 for Zone 31N/West and EPSG:26332 for Zone 32N/East) to WGS84 (EPSG:4326).

The Minna Datum is the official geodetic reference system used in Nigeria for surveying
and mapping. Lagos falls across two zones:
- Zone 31N (West Lagos): EPSG:26331
- Zone 32N (East Lagos): EPSG:26332
"""

from typing import List, Dict, Tuple, Optional
import logging
from pyproj import Transformer, CRS
from pyproj.exceptions import ProjError

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CoordinateTransformationError(Exception):
    """Custom exception for coordinate transformation errors."""
    pass


class CoordinateValidationError(Exception):
    """Custom exception for coordinate validation errors."""
    pass


class CoordinateManager:
    """
    Manages coordinate transformations between Nigerian Minna Datum and WGS84.
    
    The Minna Datum uses a Transverse Mercator projection with two zones covering Nigeria:
    - Zone 31N: Covers western Nigeria including western Lagos (EPSG:26331)
    - Zone 32N: Covers eastern Nigeria including eastern Lagos (EPSG:26332)
    
    Attributes:
        ZONE_31N (int): EPSG code for Minna Datum Zone 31N (West)
        ZONE_32N (int): EPSG code for Minna Datum Zone 32N (East)
        WGS84 (int): EPSG code for WGS84 coordinate system
    """
    
    ZONE_31N = 26331  # Minna / Nigeria West Belt
    ZONE_32N = 26332  # Minna / Nigeria Mid Belt (covers East Lagos)
    WGS84 = 4326      # World Geodetic System 1984
    
    # Valid coordinate ranges for Nigerian Minna Datum
    # Easting typically ranges from ~200,000 to ~800,000 meters
    # Northing typically ranges from ~600,000 to ~1,500,000 meters
    MIN_EASTING = 100000
    MAX_EASTING = 900000
    MIN_NORTHING = 500000
    MAX_NORTHING = 1600000
    
    def __init__(self):
        """Initialize the CoordinateManager with transformers for both zones."""
        self._transformers: Dict[int, Transformer] = {}
        self._initialize_transformers()
    
    def _initialize_transformers(self) -> None:
        """
        Initialize pyproj Transformers for both zones.
        
        Transformers are cached for performance since they're reused frequently.
        """
        try:
            # Create transformer for Zone 31N (West Lagos)
            self._transformers[self.ZONE_31N] = Transformer.from_crs(
                CRS.from_epsg(self.ZONE_31N),
                CRS.from_epsg(self.WGS84),
                always_xy=True
            )
            logger.info(f"Initialized transformer for Zone 31N (EPSG:{self.ZONE_31N})")
            
            # Create transformer for Zone 32N (East Lagos)
            self._transformers[self.ZONE_32N] = Transformer.from_crs(
                CRS.from_epsg(self.ZONE_32N),
                CRS.from_epsg(self.WGS84),
                always_xy=True
            )
            logger.info(f"Initialized transformer for Zone 32N (EPSG:{self.ZONE_32N})")
            
        except ProjError as e:
            error_msg = f"Failed to initialize coordinate transformers: {str(e)}"
            logger.error(error_msg)
            raise CoordinateTransformationError(error_msg)
    
    def validate_coordinates(self, easting: float, northing: float) -> Tuple[bool, Optional[str]]:
        """
        Validate that coordinates are numeric and within reasonable ranges for Nigeria.
        
        Args:
            easting: Easting coordinate in meters (X coordinate)
            northing: Northing coordinate in meters (Y coordinate)
        
        Returns:
            Tuple of (is_valid, error_message). error_message is None if valid.
        
        Examples:
            >>> manager = CoordinateManager()
            >>> manager.validate_coordinates(500000, 700000)
            (True, None)
            >>> manager.validate_coordinates(50000, 700000)
            (False, 'Easting coordinate 50000.00 is outside valid range...')
        """
        try:
            # Check if values are numeric
            easting_float = float(easting)
            northing_float = float(northing)
            
            # Check for NaN or infinity
            if not (float('-inf') < easting_float < float('inf')):
                return False, f"Easting coordinate {easting} is not a valid number"
            
            if not (float('-inf') < northing_float < float('inf')):
                return False, f"Northing coordinate {northing} is not a valid number"
            
            # Check if values are within valid ranges for Nigerian Minna Datum
            if not (self.MIN_EASTING <= easting_float <= self.MAX_EASTING):
                return False, (
                    f"Easting coordinate {easting_float:.2f} is outside valid range "
                    f"({self.MIN_EASTING} - {self.MAX_EASTING} meters). "
                    f"Please verify the coordinate value."
                )
            
            if not (self.MIN_NORTHING <= northing_float <= self.MAX_NORTHING):
                return False, (
                    f"Northing coordinate {northing_float:.2f} is outside valid range "
                    f"({self.MIN_NORTHING} - {self.MAX_NORTHING} meters). "
                    f"Please verify the coordinate value."
                )
            
            return True, None
            
        except (TypeError, ValueError) as e:
            return False, f"Invalid coordinate values: {str(e)}"
    
    def convert_minna_to_wgs84(
        self, 
        easting: float, 
        northing: float, 
        zone: int
    ) -> Tuple[float, float]:
        """
        Convert a single coordinate pair from Minna Datum to WGS84.
        
        Args:
            easting: Easting coordinate in meters (X coordinate in Minna Datum)
            northing: Northing coordinate in meters (Y coordinate in Minna Datum)
            zone: Zone number (26331 for Zone 31N/West, 26332 for Zone 32N/East)
        
        Returns:
            Tuple of (longitude, latitude) in WGS84 (EPSG:4326)
        
        Raises:
            CoordinateValidationError: If coordinates are invalid
            CoordinateTransformationError: If transformation fails
        
        Examples:
            >>> manager = CoordinateManager()
            >>> lon, lat = manager.convert_minna_to_wgs84(500000, 700000, 26331)
            >>> print(f"Longitude: {lon:.6f}, Latitude: {lat:.6f}")
        """
        # Validate coordinates first
        is_valid, error_msg = self.validate_coordinates(easting, northing)
        if not is_valid:
            logger.error(f"Coordinate validation failed: {error_msg}")
            raise CoordinateValidationError(error_msg)
        
        # Validate zone
        if zone not in self._transformers:
            valid_zones = list(self._transformers.keys())
            error_msg = (
                f"Invalid zone {zone}. Valid zones are {valid_zones}. "
                f"Use {self.ZONE_31N} for West Lagos or {self.ZONE_32N} for East Lagos."
            )
            logger.error(error_msg)
            raise CoordinateTransformationError(error_msg)
        
        try:
            # Perform transformation
            # Note: always_xy=True means the order is (easting/x, northing/y) -> (lon, lat)
            transformer = self._transformers[zone]
            longitude, latitude = transformer.transform(easting, northing)
            
            logger.debug(
                f"Converted ({easting}, {northing}) in Zone {zone} "
                f"to ({longitude:.6f}, {latitude:.6f}) in WGS84"
            )
            
            # Sanity check: Nigeria's bounding box is roughly (2.5°E to 15°E, 4°N to 14°N)
            if not (2.0 <= longitude <= 16.0 and 3.0 <= latitude <= 15.0):
                logger.warning(
                    f"Converted coordinates ({longitude:.6f}, {latitude:.6f}) "
                    f"are outside Nigeria's typical bounds. Please verify input coordinates."
                )
            
            return longitude, latitude
            
        except ProjError as e:
            error_msg = f"Coordinate transformation failed: {str(e)}"
            logger.error(error_msg)
            raise CoordinateTransformationError(error_msg)
    
    def batch_convert(
        self, 
        coordinates: List[Dict[str, float]], 
        zone: int
    ) -> List[Dict[str, float]]:
        """
        Convert multiple coordinate pairs from Minna Datum to WGS84.
        
        This method processes multiple coordinates in batch, providing better
        error handling and reporting for bulk operations.
        
        Args:
            coordinates: List of dictionaries with 'easting' and 'northing' keys
            zone: Zone number (26331 for Zone 31N/West, 26332 for Zone 32N/East)
        
        Returns:
            List of dictionaries with 'longitude', 'latitude', 'easting', and 'northing' keys
        
        Raises:
            CoordinateTransformationError: If any transformation fails
        
        Examples:
            >>> manager = CoordinateManager()
            >>> coords = [
            ...     {'easting': 500000, 'northing': 700000},
            ...     {'easting': 501000, 'northing': 701000}
            ... ]
            >>> result = manager.batch_convert(coords, 26331)
            >>> for coord in result:
            ...     print(f"Lat: {coord['latitude']:.6f}, Lon: {coord['longitude']:.6f}")
        """
        if not coordinates:
            logger.warning("Empty coordinates list provided to batch_convert")
            return []
        
        converted_coords = []
        errors = []
        
        for idx, coord in enumerate(coordinates):
            try:
                # Validate coordinate dictionary structure
                if 'easting' not in coord or 'northing' not in coord:
                    raise CoordinateValidationError(
                        f"Coordinate {idx} missing 'easting' or 'northing' key"
                    )
                
                easting = coord['easting']
                northing = coord['northing']
                
                # Convert to WGS84
                longitude, latitude = self.convert_minna_to_wgs84(easting, northing, zone)
                
                # Store both original and converted coordinates
                converted_coords.append({
                    'easting': easting,
                    'northing': northing,
                    'longitude': longitude,
                    'latitude': latitude
                })
                
            except (CoordinateValidationError, CoordinateTransformationError) as e:
                error_msg = f"Error converting coordinate {idx} ({coord}): {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)
        
        if errors:
            # If any conversions failed, raise an error with all failure details
            raise CoordinateTransformationError(
                f"Failed to convert {len(errors)} out of {len(coordinates)} coordinates:\n" +
                "\n".join(errors)
            )
        
        logger.info(f"Successfully converted {len(converted_coords)} coordinates")
        return converted_coords
    
    @staticmethod
    def get_zone_name(zone: int) -> str:
        """
        Get a human-readable name for a zone.
        
        Args:
            zone: Zone EPSG code
        
        Returns:
            Human-readable zone name
        """
        zone_names = {
            26331: "Lagos West (Zone 31N)",
            26332: "Lagos East (Zone 32N)"
        }
        return zone_names.get(zone, f"Zone {zone}")
