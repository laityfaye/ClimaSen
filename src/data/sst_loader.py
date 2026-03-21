"""
Module pour le chargement et la préparation des données SST (Sea Surface Temperature).
"""

import numpy as np
import pandas as pd
from pathlib import Path
from typing import Tuple, Optional, Dict, List
from datetime import datetime, timedelta
import xarray as xr
from tqdm import tqdm
import os
import ctypes
from ctypes import wintypes
from scipy.ndimage import zoom
from collections import Counter

from src.config.settings import RAW_DATA_DIR


def get_short_path(long_path: str) -> str:
    """
    Convertit un chemin Windows long avec caractères Unicode en chemin court (8.3).
    Cela résout les problèmes avec netCDF4 et les caractères accentués.
    
    Args:
        long_path (str): Chemin long avec caractères Unicode
        
    Returns:
        str: Chemin court (8.3) ou chemin original si la conversion échoue
    """
    try:
        # Utiliser l'API Windows GetShortPathNameW
        kernel32 = ctypes.windll.kernel32
        kernel32.GetShortPathNameW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
        kernel32.GetShortPathNameW.restype = wintypes.DWORD
        
        buffer = ctypes.create_unicode_buffer(260)  # MAX_PATH
        result = kernel32.GetShortPathNameW(long_path, buffer, 260)
        
        if result > 0:
            return buffer.value
        else:
            return long_path
    except:
        # Si la conversion échoue, retourner le chemin original
        return long_path


class SSTDataLoader:
    """
    Classe pour charger et préparer les données SST depuis les fichiers netCDF.
    """
    
    def __init__(self, sst_dir: Path = None,
                 lat_min: float = -60.0, lat_max: float = 60.0):
        """
        Initialise le chargeur de données SST.

        Args:
            sst_dir (Path, optional): Chemin vers le dossier contenant les fichiers SST.
                                    Par défaut: data/raw/SST
            lat_min (float): Latitude minimale à conserver (défaut: -60°, soit 60°S).
            lat_max (float): Latitude maximale à conserver (défaut:  60°, soit 60°N).
                             Au-delà de ±60°, la glace de mer perturbe les anomalies SST.
        """
        if sst_dir is None:
            # Utiliser le chemin absolu pour éviter les problèmes de résolution
            self.sst_dir = Path(RAW_DATA_DIR).resolve() / "SST"
        else:
            self.sst_dir = Path(sst_dir).resolve()

        # Plage de latitude active
        self.lat_min = float(lat_min)
        self.lat_max = float(lat_max)

        # Vérifier que le dossier existe
        if not self.sst_dir.exists():
            raise FileNotFoundError(f"Dossier SST non trouvé: {self.sst_dir}")

        self.sst_files = sorted(list(self.sst_dir.glob("*.nc")))

        if not self.sst_files:
            raise FileNotFoundError(f"Aucun fichier SST trouvé dans {self.sst_dir}")

        print(f"[OK] {len(self.sst_files)} fichiers SST trouves")
        print(f"   Plage de latitude : {self.lat_min}S -> {self.lat_max}N")
        for f in self.sst_files:
            print(f"   - {f.name}")
    
    def get_sst_file_for_date(self, date: datetime) -> Optional[Path]:
        """
        Trouve le fichier SST correspondant à une date donnée.
        
        Args:
            date (datetime): Date recherchée
            
        Returns:
            Optional[Path]: Chemin vers le fichier SST (absolu) ou None si non trouvé
        """
        year = date.year
        
        # Chercher un fichier contenant l'année dans le nom
        for sst_file in self.sst_files:
            if str(year) in sst_file.name:
                # Retourner le chemin absolu résolu
                return Path(sst_file).resolve()
        
        return None
    
    def load_sst_field(self, date: datetime, variable: str = None) -> Optional[np.ndarray]:
        """
        Charge le champ SST pour une date donnée.
        
        Args:
            date (datetime): Date du champ SST à charger
            variable (str, optional): Nom de la variable à charger. 
                                    Si None, charge la première variable de données.
        
        Returns:
            Optional[np.ndarray]: Champ SST 2D (lat, lon) ou None si non trouvé
        """
        sst_file = self.get_sst_file_for_date(date)
        
        if sst_file is None:
            return None
        
        # S'assurer que le chemin est absolu et résolu
        sst_file = Path(sst_file).resolve()
        
        # Vérifier que le fichier existe vraiment
        if not sst_file.exists():
            return None
        
        try:
            # Ouvrir le dataset avec gestionnaire de contexte
            # Convertir le chemin en chemin court (8.3) pour éviter les problèmes avec les caractères Unicode
            file_path_str = os.fspath(sst_file)
            short_path = get_short_path(file_path_str)
            
            # Essayer d'abord avec decode_times=True, puis False si ça échoue
            try:
                ds = xr.open_dataset(short_path, decode_times=True, engine='netcdf4')
            except:
                # Si ça échoue, essayer sans decode_times
                try:
                    ds = xr.open_dataset(short_path, decode_times=False, engine='netcdf4')
                except:
                    # Dernier recours : essayer avec scipy
                    ds = xr.open_dataset(short_path, decode_times=False, engine='scipy')
            
            try:
                # Déterminer la variable à charger
                if variable is None:
                    # Prendre la première variable de données (pas les coordonnées)
                    data_vars = [v for v in ds.data_vars]
                    if not data_vars:
                        return None
                    variable = data_vars[0]
                
                # Vérifier que la variable existe
                if variable not in ds.data_vars:
                    return None

                # --- Filtre de latitude : 60°S – 60°N ---
                # Les données polaires (>|60°|) sont perturbées par la glace de mer ;
                # les indices de téléconnexion sont tous définis dans cette plage.
                da_var = ds[variable]
                for _lat_name in ['lat', 'latitude', 'Lat', 'Latitude',
                                   'LAT', 'LATITUDE', 'y']:
                    if _lat_name in da_var.coords:
                        _lat_vals = da_var[_lat_name].values
                        if len(_lat_vals) > 0:
                            if _lat_vals[0] > _lat_vals[-1]:
                                # Ordre décroissant (90 → -90) : slice(max, min)
                                da_var = da_var.sel(
                                    {_lat_name: slice(self.lat_max, self.lat_min)})
                            else:
                                # Ordre croissant (-90 → 90) : slice(min, max)
                                da_var = da_var.sel(
                                    {_lat_name: slice(self.lat_min, self.lat_max)})
                        break

                # Extraire les coordonnées temporelles
                time_coord = None
                for coord_name in ['time', 'Time', 'TIME', 'date', 'Date', 't']:
                    if coord_name in ds.coords:
                        time_coord = coord_name
                        break

                if time_coord is None:
                    # Pas de coordonnée temporelle, prendre le premier champ
                    sst_data = da_var.values
                    if len(sst_data.shape) == 2:
                        field = sst_data.copy()
                    elif len(sst_data.shape) == 3:
                        field = sst_data[0, :, :].copy()
                    else:
                        return None
                else:
                    # Filtrer par date
                    try:
                        # Convertir la date en format compatible
                        date_pd = pd.Timestamp(date)

                        # Sélectionner la date la plus proche
                        sst_sel = da_var.sel({time_coord: date_pd}, method='nearest')
                        field = sst_sel.values.copy()

                        # Si 3D, prendre la première couche temporelle
                        if len(field.shape) == 3:
                            field = field[0, :, :].copy()

                    except (KeyError, ValueError, IndexError) as e:
                        # Si la date exacte n'est pas trouvée, prendre le premier champ
                        sst_data = da_var.values
                        if len(sst_data.shape) == 2:
                            field = sst_data.copy()
                        elif len(sst_data.shape) == 3:
                            field = sst_data[0, :, :].copy()
                        else:
                            return None

                # Retourner le champ 2D
                return field
            finally:
                ds.close()
            
        except Exception as e:
            # Ne pas afficher d'erreur pour chaque tentative (trop verbeux)
            # L'erreur sera gérée au niveau supérieur
            return None
    
    def get_sst_coordinates(self, sst_file: Path = None) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """
        Récupère les coordonnées (latitudes, longitudes) des données SST.
        
        Args:
            sst_file (Path, optional): Fichier SST à utiliser. 
                                     Si None, utilise le premier fichier disponible.
        
        Returns:
            Tuple[Optional[np.ndarray], Optional[np.ndarray]]: (lats, lons) ou (None, None)
        """
        if sst_file is None:
            sst_file = self.sst_files[0]
        
        try:
            # S'assurer que le chemin est absolu et résolu
            sst_file = Path(sst_file).resolve()
            file_path_str = os.fspath(sst_file)
            short_path = get_short_path(file_path_str)
            
            with xr.open_dataset(short_path, decode_times=True, engine='netcdf4') as ds:
                # Chercher les coordonnées latitude et longitude
                lats = None
                lons = None
                
                for coord_name in ['lat', 'latitude', 'Lat', 'Latitude', 'LAT', 'LATITUDE', 'y']:
                    if coord_name in ds.coords:
                        lats = ds[coord_name].values.copy()
                        break

                for coord_name in ['lon', 'longitude', 'Lon', 'Longitude', 'LON', 'LONGITUDE', 'x']:
                    if coord_name in ds.coords:
                        lons = ds[coord_name].values.copy()
                        break

                # Si pas trouvé dans les coords, chercher dans les dimensions
                if lats is None:
                    for dim_name in ['lat', 'latitude', 'Lat', 'Latitude', 'y']:
                        if dim_name in ds.dims:
                            lats = np.linspace(-90, 90, ds.dims[dim_name])

                if lons is None:
                    for dim_name in ['lon', 'longitude', 'Lon', 'Longitude', 'x']:
                        if dim_name in ds.dims:
                            lons = np.linspace(-180, 180, ds.dims[dim_name])

                # Appliquer le filtre de latitude sur les coordonnées retournées
                if lats is not None:
                    lat_mask = (lats >= self.lat_min) & (lats <= self.lat_max)
                    lats = lats[lat_mask]

                return lats, lons
            
        except Exception as e:
            print(f"[WARN] Erreur lors de la recuperation des coordonnees: {e}")
            return None, None
    
    def load_sst_fields_for_dates(self, dates: List[datetime], 
                                  variable: str = None,
                                  verbose: bool = True) -> Dict[datetime, np.ndarray]:
        """
        Charge les champs SST pour une liste de dates.
        
        Args:
            dates (List[datetime]): Liste des dates pour lesquelles charger les champs SST
            variable (str, optional): Nom de la variable à charger
            verbose (bool): Afficher la progression
        
        Returns:
            Dict[datetime, np.ndarray]: Dictionnaire {date: champ_SST}
        """
        sst_fields = {}
        
        # Filtrer les dates pour ne garder que celles avec des fichiers SST disponibles
        available_years = set()
        for sst_file in self.sst_files:
            # Extraire l'année du nom de fichier
            for year in range(1980, 2030):
                if str(year) in sst_file.name:
                    available_years.add(year)
                    break
        
        # Filtrer les dates
        filtered_dates = [d for d in dates if d.year in available_years]
        
        if verbose:
            print(f"\n[CHARGEMENT] Chargement des champs SST pour {len(filtered_dates)} dates (sur {len(dates)} total)")
            if len(filtered_dates) < len(dates):
                print(f"   [WARN] Fichiers SST disponibles uniquement pour les annees: {sorted(available_years)}")
        
        if not filtered_dates:
            if verbose:
                print("[ERREUR] Aucune date ne correspond aux fichiers SST disponibles")
            return {}
        
        iterator = tqdm(filtered_dates, desc="Chargement SST") if verbose else filtered_dates
        
        # Diagnostic: tester le premier fichier SST pour comprendre la structure
        if verbose and filtered_dates and len(sst_fields) == 0:
            first_date = filtered_dates[0]
            first_file = self.get_sst_file_for_date(first_date)
            if first_file:
                # Utiliser resolve() pour obtenir le chemin absolu correct
                first_file = Path(first_file).resolve()
                print(f"\n   [DIAGNOSTIC] Test du fichier: {first_file.name}")
                print(f"      Chemin: {first_file}")
                print(f"      Existe: {first_file.exists()}")
                
                if first_file.exists():
                    try:
                        # Tester l'ouverture du premier fichier avec chemin absolu
                        # Convertir en chemin court (8.3) pour éviter les problèmes avec les caractères Unicode
                        file_path_str = os.fspath(first_file)
                        short_path = get_short_path(file_path_str)
                        
                        # Vérifier la taille du fichier
                        file_size = first_file.stat().st_size
                        print(f"      Taille du fichier: {file_size / (1024*1024):.2f} MB")
                        print(f"      Chemin court: {short_path}")
                        
                        # Essayer différents moteurs avec le chemin court
                        test_ds = None
                        for engine in ['netcdf4', 'scipy']:
                            try:
                                print(f"      Tentative avec engine='{engine}'...")
                                test_ds = xr.open_dataset(short_path, decode_times=False, engine=engine)
                                print(f"      [OK] Fichier ouvert avec succes (engine='{engine}')!")
                                break
                            except Exception as engine_error:
                                print(f"      [ECHEC] engine='{engine}': {str(engine_error)[:100]}")
                                continue
                        
                        if test_ds is not None:
                            print(f"      Variables: {list(test_ds.data_vars)}")
                            print(f"      Coordonnées: {list(test_ds.coords)}")
                            print(f"      Dimensions: {dict(test_ds.dims)}")
                            if test_ds.data_vars:
                                first_var = list(test_ds.data_vars)[0]
                                print(f"      Shape de '{first_var}': {test_ds[first_var].shape}")
                            test_ds.close()
                        else:
                            print(f"      [ECHEC] Aucun engine n'a pu ouvrir le fichier")
                    except Exception as diag_error:
                        print(f"      [ERREUR] lors de l'ouverture: {diag_error}")
                        import traceback
                        traceback.print_exc()
                else:
                    print(f"      [ERREUR] Le fichier n'existe pas a ce chemin")
        
        for date in iterator:
            field = self.load_sst_field(date, variable=variable)
            if field is not None:
                sst_fields[date] = field
        
        if verbose:
            print(f"[OK] {len(sst_fields)}/{len(filtered_dates)} champs SST charges avec succes")
            if len(sst_fields) < len(filtered_dates):
                print(f"   [WARN] {len(filtered_dates) - len(sst_fields)} dates n'ont pas pu etre chargees")
        
        return sst_fields
    
    def vectorize_sst_field(self, sst_field: np.ndarray, 
                           mask_nan: bool = True) -> np.ndarray:
        """
        Vectorise un champ SST 2D en un vecteur 1D.
        
        Args:
            sst_field (np.ndarray): Champ SST 2D (lat, lon)
            mask_nan (bool): Si True, remplace les NaN par 0. Sinon, les conserve.
        
        Returns:
            np.ndarray: Vecteur 1D du champ SST
        """
        if mask_nan:
            # Remplacer les NaN par 0
            field_clean = np.nan_to_num(sst_field, nan=0.0)
        else:
            field_clean = sst_field.copy()
        
        # Aplatir le champ 2D en vecteur 1D
        vector = field_clean.flatten()
        
        return vector
    
    def normalize_sst_field_sizes(self, sst_fields: Dict[datetime, np.ndarray],
                                   target_shape: Tuple[int, int] = None,
                                   verbose: bool = True) -> Dict[datetime, np.ndarray]:
        """
        Normalise les tailles de tous les champs SST à une taille commune.
        
        Args:
            sst_fields (Dict[datetime, np.ndarray]): Dictionnaire de champs SST
            target_shape (Tuple[int, int], optional): Taille cible (lat, lon). 
                                                     Si None, utilise la taille la plus fréquente.
            verbose (bool): Afficher les informations de normalisation
        
        Returns:
            Dict[datetime, np.ndarray]: Dictionnaire de champs SST normalisés
        """
        if not sst_fields:
            return {}
        
        # Détecter toutes les tailles différentes
        shapes = [field.shape for field in sst_fields.values()]
        shape_counts = Counter(shapes)
        
        if verbose:
            print(f"\n[INFO] Normalisation des tailles de champs SST:")
            print(f"   Tailles détectées: {dict(shape_counts)}")
        
        # Déterminer la taille cible
        if target_shape is None:
            # Utiliser la taille la plus fréquente
            target_shape = shape_counts.most_common(1)[0][0]
            if verbose:
                print(f"   Taille cible choisie (la plus fréquente): {target_shape}")
        else:
            if verbose:
                print(f"   Taille cible spécifiée: {target_shape}")
        
        # Normaliser tous les champs à la taille cible
        normalized_fields = {}
        resized_count = 0
        
        for date, field in sst_fields.items():
            if field.shape == target_shape:
                # Aucun redimensionnement nécessaire
                normalized_fields[date] = field
            else:
                # Redimensionner le champ
                zoom_factors = (target_shape[0] / field.shape[0], 
                               target_shape[1] / field.shape[1])
                resized_field = zoom(field, zoom_factors, order=1, mode='nearest')
                normalized_fields[date] = resized_field
                resized_count += 1
        
        if verbose and resized_count > 0:
            print(f"   [OK] {resized_count} champs redimensionnes vers {target_shape}")
        
        return normalized_fields
    
    def vectorize_sst_fields(self, sst_fields: Dict[datetime, np.ndarray],
                            mask_nan: bool = True,
                            normalize_sizes: bool = True) -> Tuple[np.ndarray, List[datetime]]:
        """
        Vectorise plusieurs champs SST en une matrice (n_samples, n_features).
        
        Args:
            sst_fields (Dict[datetime, np.ndarray]): Dictionnaire de champs SST
            mask_nan (bool): Si True, remplace les NaN par 0
            normalize_sizes (bool): Si True, normalise les tailles avant vectorisation
        
        Returns:
            Tuple[np.ndarray, List[datetime]]: (matrice_vectorisée, liste_dates)
        """
        if not sst_fields:
            return np.array([]), []
        
        # Normaliser les tailles si nécessaire
        if normalize_sizes:
            sst_fields = self.normalize_sst_field_sizes(sst_fields, verbose=True)
        
        # Obtenir la taille d'un vecteur
        first_field = list(sst_fields.values())[0]
        vector_size = first_field.size
        
        # Pré-allouer la matrice avec float32 pour réduire l'utilisation mémoire
        # Utiliser np.empty au lieu de np.zeros (plus rapide, valeurs non initialisées)
        n_samples = len(sst_fields)
        matrix = np.empty((n_samples, vector_size), dtype=np.float32)
        
        dates_list = []
        
        # Remplir la matrice progressivement
        for i, (date, field) in enumerate(sst_fields.items()):
            vector = self.vectorize_sst_field(field, mask_nan=mask_nan)
            # Convertir en float32 et assigner directement
            matrix[i, :] = vector.astype(np.float32)
            dates_list.append(date)
        
        return matrix, dates_list


def load_sst_for_extreme_events(events_df: pd.DataFrame,
                               sst_dir: Path = None,
                               variable: str = None) -> Tuple[np.ndarray, List[datetime], Dict]:
    """
    Fonction utilitaire pour charger et vectoriser les champs SST 
    associés aux jours d'événements extrêmes.
    
    Args:
        events_df (pd.DataFrame): DataFrame des événements extrêmes avec colonne 'date'
        sst_dir (Path, optional): Dossier contenant les fichiers SST
        variable (str, optional): Nom de la variable SST à charger
    
    Returns:
        Tuple[np.ndarray, List[datetime], Dict]:
            - Matrice vectorisée (n_events, n_features)
            - Liste des dates des événements
            - Dictionnaire de métadonnées
    """
    # Initialiser le chargeur
    loader = SSTDataLoader(sst_dir=sst_dir)
    
    # Convertir les dates
    # Vérifier d'abord si l'index est un DatetimeIndex
    if isinstance(events_df.index, pd.DatetimeIndex):
        dates = events_df.index.tolist()
    elif 'date' in events_df.columns:
        dates = pd.to_datetime(events_df['date']).tolist()
    else:
        raise ValueError("Le DataFrame doit contenir une colonne 'date' ou un index DatetimeIndex")
    
    # Charger les champs SST
    sst_fields = loader.load_sst_fields_for_dates(dates, variable=variable, verbose=True)
    
    if not sst_fields:
        raise ValueError("Aucun champ SST n'a pu être chargé")
    
    # Sauvegarder la shape pour les métadonnées avant vectorisation
    sst_shape = list(sst_fields.values())[0].shape if sst_fields else None
    n_events = len(sst_fields)
    
    # Vectoriser les champs
    matrix, dates_loaded = loader.vectorize_sst_fields(sst_fields, mask_nan=True)
    
    # Libérer la mémoire des champs SST individuels après vectorisation
    del sst_fields
    import gc
    gc.collect()
    
    # Récupérer les coordonnées SST
    lats, lons = loader.get_sst_coordinates()
    
    # Métadonnées
    metadata = {
        'n_events': n_events,
        'n_features': matrix.shape[1],
        'sst_shape': sst_shape,
        'lats': lats,
        'lons': lons,
        'variable': variable,
        'dates_range': (min(dates_loaded), max(dates_loaded)) if dates_loaded else None
    }
    
    return matrix, dates_loaded, metadata

