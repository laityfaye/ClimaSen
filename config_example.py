# Exemple de configuration personnalisée
# Copiez ce fichier vers src/config/custom_settings.py pour personnaliser

# Paramètres de détection personnalisés
CUSTOM_DETECTION_CRITERIA = {
    "threshold_anomaly": 2.5,      # Plus strict que 2.0
    "min_grid_points": 30,         # Moins strict que 40
    "min_precipitation": 10.0      # Plus strict que 5.0
}

# Région d'étude personnalisée (exemple: sous-région du Sénégal)
CUSTOM_REGION_BOUNDS = {
    "lat_min": 13.0,
    "lat_max": 16.0,
    "lon_min": -17.0,
    "lon_max": -13.0
}
