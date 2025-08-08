# src/utils/geographic_references.py
"""
Module centralisé pour les références géographiques complètes du Sénégal.
Inclut toutes les régions, départements et principales villes avec coordonnées réelles.
"""

from typing import Dict, Any, List, Tuple
import math

class SenegalGeography:
    """Classe centralisée pour toutes les références géographiques du Sénégal."""
    
    # Régions administratives du Sénégal avec leurs départements
    REGIONS = {
        'Dakar': {
            'lat': 14.6928, 'lon': -17.4467,
            'superficie': 547,  # km²
            'population': 3732284,
            'bounds': {'lat_min': 14.53, 'lat_max': 14.85, 'lon_min': -17.54, 'lon_max': -17.10},
            'departements': {
                'Dakar': {'lat': 14.6928, 'lon': -17.4467, 'chef_lieu': 'Dakar'},
                'Guédiawaye': {'lat': 14.7692, 'lon': -17.4103, 'chef_lieu': 'Guédiawaye'},
                'Pikine': {'lat': 14.7547, 'lon': -17.3906, 'chef_lieu': 'Pikine'},
                'Rufisque': {'lat': 14.7167, 'lon': -17.2667, 'chef_lieu': 'Rufisque'},
                'Keur Massar': {'lat': 14.7833, 'lon': -17.3167, 'chef_lieu': 'Keur Massar'}
            }
        },
        
        'Thiès': {
            'lat': 14.7886, 'lon': -16.9260,
            'superficie': 6601,
            'population': 2016563,
            'bounds': {'lat_min': 14.40, 'lat_max': 15.15, 'lon_min': -17.20, 'lon_max': -16.50},
            'departements': {
                'Thiès': {'lat': 14.7886, 'lon': -16.9260, 'chef_lieu': 'Thiès'},
                'Mbour': {'lat': 14.4069, 'lon': -16.9644, 'chef_lieu': 'Mbour'},
                'Tivaouane': {'lat': 14.9500, 'lon': -16.8167, 'chef_lieu': 'Tivaouane'}
            }
        },
        
        'Diourbel': {
            'lat': 14.6594, 'lon': -16.2311,
            'superficie': 4948,
            'population': 1739447,
            'bounds': {'lat_min': 14.30, 'lat_max': 15.00, 'lon_min': -16.50, 'lon_max': -15.80},
            'departements': {
                'Diourbel': {'lat': 14.6594, 'lon': -16.2311, 'chef_lieu': 'Diourbel'},
                'Mbacké': {'lat': 14.7964, 'lon': -15.9131, 'chef_lieu': 'Mbacké'},
                'Bambey': {'lat': 14.7019, 'lon': -16.4553, 'chef_lieu': 'Bambey'}
            }
        },
        
        'Fatick': {
            'lat': 14.3333, 'lon': -16.4167,
            'superficie': 7935,
            'population': 827828,
            'bounds': {'lat_min': 13.75, 'lat_max': 14.75, 'lon_min': -16.80, 'lon_max': -15.90},
            'departements': {
                'Fatick': {'lat': 14.3333, 'lon': -16.4167, 'chef_lieu': 'Fatick'},
                'Foundiougne': {'lat': 14.1333, 'lon': -16.4667, 'chef_lieu': 'Foundiougne'},
                'Gossas': {'lat': 14.4833, 'lon': -16.0667, 'chef_lieu': 'Gossas'}
            }
        },
        
        'Kaolack': {
            'lat': 14.1500, 'lon': -16.0667,
            'superficie': 5357,
            'population': 985306,
            'bounds': {'lat_min': 13.75, 'lat_max': 14.50, 'lon_min': -16.40, 'lon_max': -15.40},
            'departements': {
                'Kaolack': {'lat': 14.1500, 'lon': -16.0667, 'chef_lieu': 'Kaolack'},
                'Guinguinéo': {'lat': 14.2667, 'lon': -15.9500, 'chef_lieu': 'Guinguinéo'},
                'Nioro du Rip': {'lat': 13.7500, 'lon': -15.7833, 'chef_lieu': 'Nioro du Rip'}
            }
        },
        
        'Kaffrine': {
            'lat': 14.1058, 'lon': -15.5472,
            'superficie': 11262,
            'population': 566992,
            'bounds': {'lat_min': 13.60, 'lat_max': 14.60, 'lon_min': -16.00, 'lon_max': -15.00},
            'departements': {
                'Kaffrine': {'lat': 14.1058, 'lon': -15.5472, 'chef_lieu': 'Kaffrine'},
                'Birkelane': {'lat': 14.1667, 'lon': -15.6500, 'chef_lieu': 'Birkelane'},
                'Koungheul': {'lat': 14.8000, 'lon': -14.8000, 'chef_lieu': 'Koungheul'},
                'Malem-Hodar': {'lat': 13.8333, 'lon': -15.3167, 'chef_lieu': 'Malem-Hodar'}
            }
        },
        
        'Tambacounda': {
            'lat': 13.7667, 'lon': -13.6667,
            'superficie': 42364,
            'population': 699829,
            'bounds': {'lat_min': 13.00, 'lat_max': 14.80, 'lon_min': -14.50, 'lon_max': -11.50},
            'departements': {
                'Tambacounda': {'lat': 13.7667, 'lon': -13.6667, 'chef_lieu': 'Tambacounda'},
                'Bakel': {'lat': 14.9000, 'lon': -12.4500, 'chef_lieu': 'Bakel'},
                'Goudiry': {'lat': 14.1833, 'lon': -12.7167, 'chef_lieu': 'Goudiry'},
                'Koumpentoum': {'lat': 14.5500, 'lon': -14.5500, 'chef_lieu': 'Koumpentoum'}
            }
        },
        
        'Kédougou': {
            'lat': 12.5597, 'lon': -12.1750,
            'superficie': 16896,
            'population': 151715,
            'bounds': {'lat_min': 12.10, 'lat_max': 13.00, 'lon_min': -13.00, 'lon_max': -11.50},
            'departements': {
                'Kédougou': {'lat': 12.5597, 'lon': -12.1750, 'chef_lieu': 'Kédougou'},
                'Saraya': {'lat': 12.8000, 'lon': -11.7500, 'chef_lieu': 'Saraya'},
                'Salémata': {'lat': 12.8333, 'lon': -12.3167, 'chef_lieu': 'Salémata'}
            }
        },
        
        'Kolda': {
            'lat': 12.8833, 'lon': -14.9500,
            'superficie': 13771,
            'population': 718444,
            'bounds': {'lat_min': 12.40, 'lat_max': 13.40, 'lon_min': -15.50, 'lon_max': -14.00},
            'departements': {
                'Kolda': {'lat': 12.8833, 'lon': -14.9500, 'chef_lieu': 'Kolda'},
                'Médina Yoro Foulah': {'lat': 12.8167, 'lon': -14.5833, 'chef_lieu': 'Médina Yoro Foulah'},
                'Vélingara': {'lat': 13.1500, 'lon': -14.1167, 'chef_lieu': 'Vélingara'}
            }
        },
        
        'Sédhiou': {
            'lat': 12.7089, 'lon': -15.5647,
            'superficie': 7341,
            'population': 459788,
            'bounds': {'lat_min': 12.30, 'lat_max': 13.20, 'lon_min': -16.20, 'lon_max': -15.00},
            'departements': {
                'Sédhiou': {'lat': 12.7089, 'lon': -15.5647, 'chef_lieu': 'Sédhiou'},
                'Bounkiling': {'lat': 12.6333, 'lon': -15.3667, 'chef_lieu': 'Bounkiling'},
                'Goudomp': {'lat': 12.5667, 'lon': -15.8667, 'chef_lieu': 'Goudomp'}
            }
        },
        
        'Ziguinchor': {
            'lat': 12.5833, 'lon': -16.2667,
            'superficie': 7339,
            'population': 549151,
            'bounds': {'lat_min': 12.25, 'lat_max': 13.00, 'lon_min': -16.75, 'lon_max': -15.80},
            'departements': {
                'Ziguinchor': {'lat': 12.5833, 'lon': -16.2667, 'chef_lieu': 'Ziguinchor'},
                'Bignona': {'lat': 12.8167, 'lon': -16.2333, 'chef_lieu': 'Bignona'},
                'Oussouye': {'lat': 12.4833, 'lon': -16.5500, 'chef_lieu': 'Oussouye'}
            }
        },
        
        'Saint-Louis': {
            'lat': 16.0333, 'lon': -16.5167,
            'superficie': 19034,
            'population': 975115,
            'bounds': {'lat_min': 15.50, 'lat_max': 16.70, 'lon_min': -17.00, 'lon_max': -15.50},
            'departements': {
                'Saint-Louis': {'lat': 16.0333, 'lon': -16.5167, 'chef_lieu': 'Saint-Louis'},
                'Dagana': {'lat': 16.5167, 'lon': -15.5000, 'chef_lieu': 'Dagana'},
                'Podor': {'lat': 16.6500, 'lon': -14.9667, 'chef_lieu': 'Podor'}
            }
        },
        
        'Louga': {
            'lat': 15.6181, 'lon': -16.2314,
            'superficie': 24847,
            'population': 978347,
            'bounds': {'lat_min': 15.00, 'lat_max': 16.30, 'lon_min': -16.80, 'lon_max': -15.20},
            'departements': {
                'Louga': {'lat': 15.6181, 'lon': -16.2314, 'chef_lieu': 'Louga'},
                'Linguère': {'lat': 15.3833, 'lon': -15.1167, 'chef_lieu': 'Linguère'},
                'Kébémer': {'lat': 15.4000, 'lon': -16.4500, 'chef_lieu': 'Kébémer'}
            }
        },
        
        'Matam': {
            'lat': 15.6558, 'lon': -13.2553,
            'superficie': 29445,
            'population': 619404,
            'bounds': {'lat_min': 15.20, 'lat_max': 16.70, 'lon_min': -14.00, 'lon_max': -12.00},
            'departements': {
                'Matam': {'lat': 15.6558, 'lon': -13.2553, 'chef_lieu': 'Matam'},
                'Kanel': {'lat': 15.5167, 'lon': -13.1833, 'chef_lieu': 'Kanel'},
                'Ranérou': {'lat': 15.3000, 'lon': -13.9500, 'chef_lieu': 'Ranérou'}
            }
        }
    }
    
    # Principales villes du Sénégal avec informations détaillées
    CITIES = {
        # Capitales régionales
        'Dakar': {'lat': 14.6928, 'lon': -17.4467, 'type': 'capitale', 'size': 15, 'population': 1182315},
        'Thiès': {'lat': 14.7886, 'lon': -16.9260, 'type': 'capitale_region', 'size': 10, 'population': 365964},
        'Kaolack': {'lat': 14.1500, 'lon': -16.0667, 'type': 'capitale_region', 'size': 10, 'population': 233708},
        'Saint-Louis': {'lat': 16.0333, 'lon': -16.5167, 'type': 'capitale_region', 'size': 10, 'population': 254171},
        'Ziguinchor': {'lat': 12.5833, 'lon': -16.2667, 'type': 'capitale_region', 'size': 10, 'population': 230758},
        'Diourbel': {'lat': 14.6594, 'lon': -16.2311, 'type': 'capitale_region', 'size': 10, 'population': 177891},
        'Tambacounda': {'lat': 13.7667, 'lon': -13.6667, 'type': 'capitale_region', 'size': 10, 'population': 116628},
        'Kolda': {'lat': 12.8833, 'lon': -14.9500, 'type': 'capitale_region', 'size': 8, 'population': 66468},
        'Fatick': {'lat': 14.3333, 'lon': -16.4167, 'type': 'capitale_region', 'size': 8, 'population': 30963},
        'Louga': {'lat': 15.6181, 'lon': -16.2314, 'type': 'capitale_region', 'size': 8, 'population': 102041},
        'Matam': {'lat': 15.6558, 'lon': -13.2553, 'type': 'capitale_region', 'size': 8, 'population': 35881},
        'Kédougou': {'lat': 12.5597, 'lon': -12.1750, 'type': 'capitale_region', 'size': 8, 'population': 23345},
        'Sédhiou': {'lat': 12.7089, 'lon': -15.5647, 'type': 'capitale_region', 'size': 8, 'population': 34302},
        'Kaffrine': {'lat': 14.1058, 'lon': -15.5472, 'type': 'capitale_region', 'size': 8, 'population': 47213},
        
        # Chefs-lieux de départements importants
        'Mbour': {'lat': 14.4069, 'lon': -16.9644, 'type': 'chef_lieu_dept', 'size': 8, 'population': 232777},
        'Rufisque': {'lat': 14.7167, 'lon': -17.2667, 'type': 'chef_lieu_dept', 'size': 8, 'population': 221066},
        'Pikine': {'lat': 14.7547, 'lon': -17.3906, 'type': 'chef_lieu_dept', 'size': 8, 'population': 874062},
        'Guédiawaye': {'lat': 14.7692, 'lon': -17.4103, 'type': 'chef_lieu_dept', 'size': 8, 'population': 337545},
        'Touba': {'lat': 14.8667, 'lon': -15.8833, 'type': 'ville_religieuse', 'size': 12, 'population': 1200000},
        'Mbacké': {'lat': 14.7964, 'lon': -15.9131, 'type': 'chef_lieu_dept', 'size': 8, 'population': 204454},
        'Tivaouane': {'lat': 14.9500, 'lon': -16.8167, 'type': 'chef_lieu_dept', 'size': 8, 'population': 45569},
        'Linguère': {'lat': 15.3833, 'lon': -15.1167, 'type': 'chef_lieu_dept', 'size': 6, 'population': 35332},
        'Podor': {'lat': 16.6500, 'lon': -14.9667, 'type': 'chef_lieu_dept', 'size': 6, 'population': 15229},
        'Dagana': {'lat': 16.5167, 'lon': -15.5000, 'type': 'chef_lieu_dept', 'size': 6, 'population': 20228},
        'Bakel': {'lat': 14.9000, 'lon': -12.4500, 'type': 'chef_lieu_dept', 'size': 6, 'population': 18939},
        'Vélingara': {'lat': 13.1500, 'lon': -14.1167, 'type': 'chef_lieu_dept', 'size': 6, 'population': 23734},
        'Bignona': {'lat': 12.8167, 'lon': -16.2333, 'type': 'chef_lieu_dept', 'size': 6, 'population': 27751}
    }
    
    # Limites du Sénégal
    SENEGAL_BOUNDS = {
        'lat_min': 12.3,
        'lat_max': 16.7,
        'lon_min': -17.55,
        'lon_max': -11.35
    }
    
    # Zones climatiques du Sénégal
    CLIMATE_ZONES = {
        'Zone sahélienne': {
            'regions': ['Saint-Louis', 'Louga', 'Matam'],
            'caracteristiques': 'Climat sahélien sec, précipitations < 400mm/an',
            'bounds': {'lat_min': 15.5, 'lat_max': 17.0}
        },
        'Zone soudano-sahélienne': {
            'regions': ['Thiès', 'Diourbel', 'Fatick', 'Kaolack', 'Kaffrine', 'Tambacounda'],
            'caracteristiques': 'Climat semi-aride, précipitations 400-800mm/an',
            'bounds': {'lat_min': 13.5, 'lat_max': 15.5}
        },
        'Zone soudanienne': {
            'regions': ['Kédougou', 'Kolda', 'Sédhiou', 'Ziguinchor'],
            'caracteristiques': 'Climat tropical humide, précipitations > 800mm/an',
            'bounds': {'lat_min': 12.0, 'lat_max': 13.5}
        },
        'Zone côtière': {
            'regions': ['Dakar'],
            'caracteristiques': 'Climat océanique tempéré par l\'influence maritime',
            'bounds': {'lon_min': -17.6, 'lon_max': -17.0}
        }
    }
    
    @classmethod
    def get_all_departments(cls) -> Dict[str, Dict[str, Any]]:
        """Retourne tous les départements du Sénégal avec leurs informations."""
        all_departments = {}
        
        for region_name, region_data in cls.REGIONS.items():
            for dept_name, dept_data in region_data['departements'].items():
                all_departments[dept_name] = {
                    'lat': dept_data['lat'],
                    'lon': dept_data['lon'],
                    'chef_lieu': dept_data['chef_lieu'],
                    'region': region_name
                }
        
        return all_departments
    
    @classmethod
    def identify_region(cls, lat: float, lon: float) -> str:
        """Identifie la région d'un point géographique."""
        for region_name, region_info in cls.REGIONS.items():
            bounds = region_info['bounds']
            if (bounds['lat_min'] <= lat <= bounds['lat_max'] and 
                bounds['lon_min'] <= lon <= bounds['lon_max']):
                return region_name
        
        # Si pas dans les limites exactes, chercher la région la plus proche
        return cls.identify_closest_region(lat, lon)
    
    @classmethod
    def identify_closest_region(cls, lat: float, lon: float) -> str:
        """Identifie la région la plus proche d'un point."""
        min_distance = float('inf')
        closest_region = "Zone indéterminée"
        
        for region_name, region_info in cls.REGIONS.items():
            distance = cls._calculate_distance(lat, lon, region_info['lat'], region_info['lon'])
            if distance < min_distance:
                min_distance = distance
                closest_region = region_name
        
        return closest_region
    
    @classmethod
    def identify_department(cls, lat: float, lon: float) -> Tuple[str, str]:
        """Identifie le département et la région d'un point géographique."""
        region = cls.identify_region(lat, lon)
        
        if region == "Zone indéterminée":
            return "Département indéterminé", region
        
        # Chercher le département le plus proche dans la région
        min_distance = float('inf')
        closest_dept = "Département indéterminé"
        
        for dept_name, dept_info in cls.REGIONS[region]['departements'].items():
            distance = cls._calculate_distance(lat, lon, dept_info['lat'], dept_info['lon'])
            if distance < min_distance:
                min_distance = distance
                closest_dept = dept_name
        
        return closest_dept, region
    
    @classmethod
    def identify_climate_zone(cls, lat: float, lon: float) -> str:
        """Identifie la zone climatique d'un point."""
        for zone_name, zone_info in cls.CLIMATE_ZONES.items():
            bounds = zone_info.get('bounds', {})
            
            if 'lat_min' in bounds and 'lat_max' in bounds:
                if bounds['lat_min'] <= lat <= bounds['lat_max']:
                    return zone_name
            elif 'lon_min' in bounds and 'lon_max' in bounds:
                if bounds['lon_min'] <= lon <= bounds['lon_max']:
                    return zone_name
        
        return "Zone climatique indéterminée"
    
    @classmethod
    def get_region_info(cls, region_name: str) -> Dict[str, Any]:
        """Retourne les informations complètes d'une région."""
        return cls.REGIONS.get(region_name, {})
    
    @classmethod
    def get_department_info(cls, dept_name: str) -> Dict[str, Any]:
        """Retourne les informations d'un département."""
        for region_name, region_data in cls.REGIONS.items():
            if dept_name in region_data['departements']:
                dept_info = region_data['departements'][dept_name].copy()
                dept_info['region'] = region_name
                return dept_info
        
        return {}
    
    @classmethod
    def identify_nearby_cities(cls, lat: float, lon: float, max_distance: float = 1.0) -> List[Dict[str, Any]]:
        """Identifie les villes proches d'un point."""
        nearby_cities = []
        
        for city_name, city_info in cls.CITIES.items():
            distance = cls._calculate_distance(lat, lon, city_info['lat'], city_info['lon'])
            if distance <= max_distance:
                nearby_cities.append({
                    'name': city_name,
                    'distance_km': distance,
                    'direction': cls._get_direction(lat, lon, city_info['lat'], city_info['lon']),
                    'type': city_info['type'],
                    'population': city_info.get('population', 0)
                })
        
        return sorted(nearby_cities, key=lambda x: x['distance_km'])
    
    @classmethod
    def get_regional_statistics(cls) -> Dict[str, Any]:
        """Retourne les statistiques générales par région."""
        stats = {}
        
        for region_name, region_data in cls.REGIONS.items():
            stats[region_name] = {
                'superficie': region_data['superficie'],
                'population': region_data['population'],
                'densite': region_data['population'] / region_data['superficie'],
                'nb_departements': len(region_data['departements']),
                'departements': list(region_data['departements'].keys())
            }
        
        return stats
    
    @staticmethod
    def _calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calcule la distance entre deux points en km (formule de Haversine)."""
        R = 6371  # Rayon de la Terre en km
        
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)
        
        a = (math.sin(delta_lat / 2) ** 2 + 
             math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        
        return R * c
    
    @staticmethod
    def _get_direction(lat1: float, lon1: float, lat2: float, lon2: float) -> str:
        """Détermine la direction relative entre deux points."""
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        
        if abs(dlat) > abs(dlon):
            return "Nord" if dlat > 0 else "Sud"
        else:
            return "Est" if dlon > 0 else "Ouest"
    
    @classmethod
    def is_point_in_senegal(cls, lat: float, lon: float) -> bool:
        """Vérifie si un point est dans les limites du Sénégal."""
        bounds = cls.SENEGAL_BOUNDS
        return (bounds['lat_min'] <= lat <= bounds['lat_max'] and 
                bounds['lon_min'] <= lon <= bounds['lon_max'])
    
    @classmethod
    def get_border_regions(cls) -> List[str]:
        """Retourne les régions frontalières."""
        return ['Saint-Louis', 'Matam', 'Tambacounda', 'Kédougou', 'Kolda', 'Sédhiou', 'Ziguinchor']
    
    @classmethod
    def get_coastal_regions(cls) -> List[str]:
        """Retourne les régions côtières."""
        return ['Dakar', 'Thiès', 'Fatick', 'Ziguinchor', 'Saint-Louis']


# Fonctions utilitaires pour l'analyse géographique
def analyze_geographic_distribution(coordinates: List[Tuple[float, float]]) -> Dict[str, Any]:
    """
    Analyse la distribution géographique d'une liste de coordonnées.
    
    Args:
        coordinates: Liste de tuples (latitude, longitude)
        
    Returns:
        Dict avec statistiques de distribution
    """
    if not coordinates:
        return {}
    
    # Compter par région
    region_counts = {}
    dept_counts = {}
    climate_counts = {}
    
    for lat, lon in coordinates:
        if SenegalGeography.is_point_in_senegal(lat, lon):
            region = SenegalGeography.identify_region(lat, lon)
            dept, _ = SenegalGeography.identify_department(lat, lon)
            climate = SenegalGeography.identify_climate_zone(lat, lon)
            
            region_counts[region] = region_counts.get(region, 0) + 1
            dept_counts[dept] = dept_counts.get(dept, 0) + 1
            climate_counts[climate] = climate_counts.get(climate, 0) + 1
    
    return {
        'regions': region_counts,
        'departements': dept_counts,
        'zones_climatiques': climate_counts,
        'total_points': len(coordinates),
        'points_au_senegal': sum(region_counts.values())
    }


if __name__ == "__main__":
    print("🇸🇳 Références géographiques du Sénégal")
    print("=" * 50)
    
    # Afficher les statistiques générales
    print(f"📊 STATISTIQUES GÉNÉRALES:")
    print(f"   • Nombre de régions: {len(SenegalGeography.REGIONS)}")
    print(f"   • Nombre total de départements: {sum(len(r['departements']) for r in SenegalGeography.REGIONS.values())}")
    print(f"   • Nombre de villes principales: {len(SenegalGeography.CITIES)}")
    print(f"   • Zones climatiques: {len(SenegalGeography.CLIMATE_ZONES)}")
    
    # Afficher les régions avec leurs départements
    print(f"\n🏛️  RÉGIONS ET DÉPARTEMENTS:")
    for region, data in SenegalGeography.REGIONS.items():
        print(f"\n   📍 {region}")
        print(f"      Population: {data['population']:,} habitants")
        print(f"      Superficie: {data['superficie']:,} km²")
        print(f"      Densité: {data['population']/data['superficie']:.1f} hab/km²")
        print(f"      Départements ({len(data['departements'])}):")
        for dept, dept_info in data['departements'].items():
            print(f"         • {dept} (chef-lieu: {dept_info['chef_lieu']})")
    
    # Afficher les zones climatiques
    print(f"\n🌡️  ZONES CLIMATIQUES:")
    for zone, zone_info in SenegalGeography.CLIMATE_ZONES.items():
        print(f"\n   🌿 {zone}")
        print(f"      Caractéristiques: {zone_info['caracteristiques']}")
        print(f"      Régions concernées: {', '.join(zone_info['regions'])}")
    
    # Test de fonctionnalités
    print(f"\n🧪 TESTS DE FONCTIONNALITÉS:")
    
    # Test coordonnées Dakar
    test_lat, test_lon = 14.6928, -17.4467
    print(f"\n   📍 Test avec Dakar ({test_lat}, {test_lon}):")
    print(f"      Région: {SenegalGeography.identify_region(test_lat, test_lon)}")
    dept, region = SenegalGeography.identify_department(test_lat, test_lon)
    print(f"      Département: {dept}")
    print(f"      Zone climatique: {SenegalGeography.identify_climate_zone(test_lat, test_lon)}")
    
    # Test coordonnées Tambacounda
    test_lat, test_lon = 13.7667, -13.6667
    print(f"\n   📍 Test avec Tambacounda ({test_lat}, {test_lon}):")
    print(f"      Région: {SenegalGeography.identify_region(test_lat, test_lon)}")
    dept, region = SenegalGeography.identify_department(test_lat, test_lon)
    print(f"      Département: {dept}")
    print(f"      Zone climatique: {SenegalGeography.identify_climate_zone(test_lat, test_lon)}")
    
    # Test villes proches
    nearby = SenegalGeography.identify_nearby_cities(14.6928, -17.4467, 0.5)
    print(f"\n   🏘️  Villes proches de Dakar (rayon 0.5°):")
    for city in nearby[:5]:  # Limiter à 5 villes
        print(f"      • {city['name']}: {city['distance_km']:.1f} km au {city['direction']}")
    
    # Statistiques régionales
    print(f"\n📈 STATISTIQUES RÉGIONALES:")
    stats = SenegalGeography.get_regional_statistics()
    
    # Région la plus peuplée
    most_populated = max(stats.items(), key=lambda x: x[1]['population'])
    print(f"   • Région la plus peuplée: {most_populated[0]} ({most_populated[1]['population']:,} hab)")
    
    # Région la plus grande
    largest = max(stats.items(), key=lambda x: x[1]['superficie'])
    print(f"   • Région la plus grande: {largest[0]} ({largest[1]['superficie']:,} km²)")
    
    # Région la plus dense
    densest = max(stats.items(), key=lambda x: x[1]['densite'])
    print(f"   • Région la plus dense: {densest[0]} ({densest[1]['densite']:.1f} hab/km²)")
    
    # Informations sur les frontières et côtes
    print(f"\n🌊 GÉOGRAPHIE PHYSIQUE:")
    print(f"   • Régions frontalières: {', '.join(SenegalGeography.get_border_regions())}")
    print(f"   • Régions côtières: {', '.join(SenegalGeography.get_coastal_regions())}")
    
    print(f"\n✅ Module prêt à l'utilisation!")
    print(f"📋 Fonctionnalités disponibles:")
    print(f"   • identify_region(lat, lon) - Identifier une région")
    print(f"   • identify_department(lat, lon) - Identifier un département")
    print(f"   • identify_climate_zone(lat, lon) - Identifier une zone climatique")
    print(f"   • identify_nearby_cities(lat, lon, distance) - Villes proches")
    print(f"   • get_region_info(region) - Infos détaillées d'une région")
    print(f"   • get_department_info(dept) - Infos détaillées d'un département")
    print(f"   • analyze_geographic_distribution(coordinates) - Analyser distribution")
    print(f"   • is_point_in_senegal(lat, lon) - Vérifier si point au Sénégal")