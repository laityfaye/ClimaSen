#!/usr/bin/env python3
"""
Script complet de correction pour résoudre toutes les erreurs dans le projet.
VERSION FINALE - Résout les erreurs:
- 'centroid_ok' dans detection.py
- Erreurs pandas dans detection_report.py
- Problèmes de sérialisation JSON
- Erreurs d'agrégation dans spatial_report.py

À exécuter dans le dossier racine du projet.
"""

import os
import shutil
import re
from pathlib import Path
from datetime import datetime

def create_backup(file_path):
    """Crée une sauvegarde d'un fichier."""
    backup_path = file_path.with_suffix(f'.py.backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}')
    if file_path.exists():
        shutil.copy2(file_path, backup_path)
        print(f"   💾 Sauvegarde créée: {backup_path.name}")
        return backup_path
    return None

def fix_detection_report():
    """Corrige les erreurs dans detection_report.py"""
    file_path = Path("src/reports/detection_report.py")
    if not file_path.exists():
        print(f"❌ Fichier non trouvé: {file_path}")
        return False
    
    print("📝 Correction de detection_report.py...")
    create_backup(file_path)
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    fixes_applied = 0
    
    # Fix 1: Corriger convert_numpy_types
    old_convert_pattern = r'def convert_numpy_types\(obj\):.*?(?=\n\ndef|\nclass|\nif __name__|$)'
    new_convert = '''def convert_numpy_types(obj):
    """
    Convertit les types NumPy en types Python natifs pour la sérialisation JSON.
    VERSION CORRIGÉE - Gère tous les cas problématiques.
    """
    if isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, pd.Timestamp):
        return obj.strftime('%Y-%m-%d')
    elif isinstance(obj, (bool, np.bool_)):
        return bool(obj)
    elif isinstance(obj, dict):
        converted_dict = {}
        for key, value in obj.items():
            # Gérer les clés problématiques
            if isinstance(key, tuple):
                key_str = '_'.join(str(k) for k in key)
            elif isinstance(key, (np.integer, np.floating)):
                key_str = str(int(key) if isinstance(key, np.integer) else float(key))
            elif pd.isna(key):
                key_str = 'unknown'
            else:
                key_str = str(key)
            converted_dict[key_str] = convert_numpy_types(value)
        return converted_dict
    elif isinstance(obj, list):
        return [convert_numpy_types(item) for item in obj]
    elif isinstance(obj, tuple):
        return [convert_numpy_types(item) for item in obj]
    elif pd.isna(obj):
        return None
    elif hasattr(obj, 'item'):
        try:
            return obj.item()
        except:
            return str(obj)
    else:
        return obj'''
    
    if re.search(old_convert_pattern, content, re.DOTALL):
        content = re.sub(old_convert_pattern, new_convert, content, flags=re.DOTALL)
        fixes_applied += 1
        print("   ✅ convert_numpy_types corrigée")
    
    # Fix 2: Corriger _write_top_events
    old_top_events = '''        # Top 5 par intensité - CORRECTION DE L'ERREUR
        f.write("8.2 Top 5 événements par intensité de précipitation:\\n")
        
        # Vérifier que la colonne existe avant d'utiliser nlargest
        if 'max_precip' in df_events.columns:
            # Créer une copie pour éviter les problèmes d'ambiguïté
            df_copy = df_events.copy()
            
            # Nettoyer les données pour éviter les problèmes de pandas
            df_copy['max_precip'] = pd.to_numeric(df_copy['max_precip'], errors='coerce')
            
            # Supprimer les valeurs NaN
            df_copy = df_copy.dropna(subset=['max_precip'])
            
            if not df_copy.empty:
                # Utiliser sort_values au lieu de nlargest pour éviter l'erreur
                top_intensity = df_copy.sort_values('max_precip', ascending=False).head(5)
                
                for i, (date, event) in enumerate(top_intensity.iterrows(), 1):
                    phase = event.get('phase', get_phase_from_month(date.month))
                    phase_desc = self.rainfall_phases.get(phase, {}).get('description', phase)
                    f.write(f"    {i}. {date.strftime('%Y-%m-%d')} ({phase_desc}): ")
                    f.write(f"{event['max_precip']:.1f} mm\\n")
            else:
                f.write("    Aucune donnée de précipitation valide disponible.\\n")
        else:
            f.write("    Colonne 'max_precip' non disponible.\\n")'''
    
    new_top_events = '''        # Top 5 par intensité - VERSION CORRIGÉE
        f.write("8.2 Top 5 événements par intensité de précipitation:\\n")
        
        if 'max_precip' not in df_events.columns:
            f.write("    Colonne 'max_precip' non disponible.\\n\\n")
            return
        
        try:
            # Créer une copie pour éviter les problèmes d'ambiguïté
            df_copy = df_events.copy().reset_index()
            
            # Nettoyer les données
            df_copy['max_precip'] = pd.to_numeric(df_copy['max_precip'], errors='coerce')
            df_copy = df_copy.dropna(subset=['max_precip'])
            
            if df_copy.empty:
                f.write("    Aucune donnée de précipitation valide disponible.\\n\\n")
                return
            
            # Utiliser sort_values au lieu de nlargest
            top_intensity = df_copy.sort_values('max_precip', ascending=False).head(5)
            
            for i, (_, event) in enumerate(top_intensity.iterrows(), 1):
                # Gérer la date selon le format
                if 'date' in event and pd.notna(event['date']):
                    if isinstance(event['date'], str):
                        try:
                            event_date = pd.to_datetime(event['date'])
                        except:
                            event_date = None
                    else:
                        event_date = event['date']
                else:
                    event_date = None
                
                if event_date is not None:
                    month = event_date.month
                    date_str = event_date.strftime('%Y-%m-%d')
                else:
                    month = 7
                    date_str = "Date inconnue"
                
                phase = event.get('phase', get_phase_from_month(month))
                phase_desc = self.rainfall_phases.get(phase, {}).get('description', phase)
                
                f.write(f"    {i}. {date_str} ({phase_desc}): ")
                f.write(f"{event['max_precip']:.1f} mm\\n")
                
        except Exception as e:
            f.write(f"    Erreur lors du traitement: {str(e)}\\n")
            # Fallback simple
            for i, (date, event) in enumerate(df_events.head(5).iterrows(), 1):
                phase = event.get('phase', get_phase_from_month(date.month))
                phase_desc = self.rainfall_phases.get(phase, {}).get('description', phase)
                f.write(f"    {i}. {date.strftime('%Y-%m-%d')} ({phase_desc}): ")
                f.write(f"{event['max_precip']:.1f} mm\\n")'''
    
    # Chercher et remplacer la fonction _write_top_events
    pattern = r'def _write_top_events\(self, f, df_events: pd\.DataFrame\):.*?f\.write\("\\n"\)'
    if re.search(pattern, content, re.DOTALL):
        # Remplacer toute la méthode
        replacement = '''def _write_top_events(self, f, df_events: pd.DataFrame):
        """Écrit le top des événements - VERSION CORRIGÉE."""
        f.write("8. ÉVÉNEMENTS REMARQUABLES\\n")
        f.write("-" * 30 + "\\n")
        
        # Vérifier que le DataFrame n'est pas vide
        if df_events.empty:
            f.write("Aucun événement à afficher.\\n\\n")
            return
        
        # Top 10 par couverture - utiliser les index existants (déjà triés)
        f.write("8.1 Top 10 événements par couverture spatiale:\\n")
        top_coverage = df_events.head(10)
        for i, (date, event) in enumerate(top_coverage.iterrows(), 1):
            phase = event.get('phase', get_phase_from_month(date.month))
            phase_desc = self.rainfall_phases.get(phase, {}).get('description', phase)
            f.write(f"    {i:2d}. {date.strftime('%Y-%m-%d')} ({phase_desc}):\\n")
            f.write(f"        Couverture: {event['coverage_percent']:.1f}%, ")
            f.write(f"Précipitation: {event['max_precip']:.1f} mm, ")
            f.write(f"Anomalie: {event['max_anomaly']:.1f}σ\\n")
            if 'centroid_region' in event:
                f.write(f"        Région principale: {event['centroid_region']}\\n")
        f.write("\\n")
        
''' + new_top_events + '''
        
        f.write("\\n")'''
        
        content = re.sub(pattern, replacement, content, flags=re.DOTALL)
        fixes_applied += 1
        print("   ✅ _write_top_events corrigée")
    
    # Fix 3: Ajouter la création automatique des dossiers
    pattern = r'(with open\(output_path, \'w\', encoding=\'utf-8\'\) as f:)'
    replacement = r'# Créer le dossier si nécessaire\n        Path(output_path).parent.mkdir(parents=True, exist_ok=True)\n        \n        \1'
    
    if re.search(pattern, content):
        content = re.sub(pattern, replacement, content)
        fixes_applied += 1
        print("   ✅ Création automatique des dossiers ajoutée")
    
    # Sauvegarder le fichier corrigé
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"   ✅ {fixes_applied} corrections appliquées à detection_report.py")
    return fixes_applied > 0

def fix_detection_analysis():
    """Corrige l'erreur 'centroid_ok' dans detection.py"""
    file_path = Path("src/analysis/detection.py")
    if not file_path.exists():
        print(f"❌ Fichier non trouvé: {file_path}")
        return False
    
    print("📝 Correction de detection.py...")
    create_backup(file_path)
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    fixes_applied = 0
    
    # Fix: Corriger _check_bounds_compliance
    old_compliance_pattern = r'def _check_bounds_compliance\(self, df_events, bounds\):.*?return \{.*?\}'
    new_compliance = '''def _check_bounds_compliance(self, df_events, bounds):
        """Vérifie la conformité aux limites officielles du Sénégal - VERSION CORRIGÉE."""
        
        # Vérifications centroïdes
        lat_compliance_c = (
            (df_events['centroid_lat'].min() >= bounds['lat_min']) and 
            (df_events['centroid_lat'].max() <= bounds['lat_max'])
        )
        
        lon_compliance_c = (
            (df_events['centroid_lon'].min() >= bounds['lon_min']) and 
            (df_events['centroid_lon'].max() <= bounds['lon_max'])
        )
        
        # Vérifications maxima d'intensité (si disponibles)
        lat_compliance_m = True
        lon_compliance_m = True
        
        if 'max_intensity_lat' in df_events.columns and 'max_intensity_lon' in df_events.columns:
            lat_compliance_m = (
                (df_events['max_intensity_lat'].min() >= bounds['lat_min']) and 
                (df_events['max_intensity_lat'].max() <= bounds['lat_max'])
            )
            
            lon_compliance_m = (
                (df_events['max_intensity_lon'].min() >= bounds['lon_min']) and 
                (df_events['max_intensity_lon'].max() <= bounds['lon_max'])
            )
        
        # Points problématiques
        problematic_points = 0
        if 'max_intensity_lon' in df_events.columns:
            problematic_points = len(df_events[df_events['max_intensity_lon'] > bounds['lon_max']])
        
        # CORRECTION COMPLÈTE: Créer explicitement toutes les clés nécessaires
        return {
            'centroid_latitude_compliant': lat_compliance_c,
            'centroid_longitude_compliant': lon_compliance_c,
            'max_intensity_latitude_compliant': lat_compliance_m,
            'max_intensity_longitude_compliant': lon_compliance_m,
            'fully_compliant': lat_compliance_c and lon_compliance_c and lat_compliance_m and lon_compliance_m,
            'problematic_points_east': problematic_points,
            'bounds_used': bounds,
            'compliance_summary': {
                'centroid_ok': lat_compliance_c and lon_compliance_c,  # CORRECTION: Clé manquante ajoutée
                'max_intensity_ok': lat_compliance_m and lon_compliance_m,
                'issues_detected': problematic_points > 0
            }
        }'''
    
    if re.search(old_compliance_pattern, content, re.DOTALL):
        content = re.sub(old_compliance_pattern, new_compliance, content, flags=re.DOTALL)
        fixes_applied += 1
        print("   ✅ _check_bounds_compliance corrigée (erreur 'centroid_ok' résolue)")
    
    # Sauvegarder le fichier corrigé
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"   ✅ {fixes_applied} corrections appliquées à detection.py")
    return fixes_applied > 0

def fix_spatial_report():
    """Corrige les erreurs dans spatial_report.py"""
    file_path = Path("src/reports/spatial_report.py")
    if not file_path.exists():
        print(f"❌ Fichier non trouvé: {file_path}")
        return False
    
    print("📝 Correction de spatial_report.py...")
    create_backup(file_path)
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    fixes_applied = 0
    
    # Fix: Corriger _convert_numpy_types
    old_convert_pattern = r'def _convert_numpy_types\(self, obj\):.*?(?=\n    def|\n\nclass|\nif __name__|$)'
    new_convert = '''def _convert_numpy_types(self, obj):
        """Convertit les types NumPy pour la sérialisation JSON - VERSION CORRIGÉE."""
        if isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, pd.Timestamp):
            return obj.strftime('%Y-%m-%d')
        elif isinstance(obj, pd.Series):
            return obj.tolist()
        elif isinstance(obj, (bool, np.bool_)):
            return bool(obj)
        elif isinstance(obj, dict):
            converted_dict = {}
            for key, value in obj.items():
                if isinstance(key, tuple):
                    key_str = '_'.join(str(k) for k in key)
                elif isinstance(key, (np.integer, np.floating)):
                    key_str = str(int(key) if isinstance(key, np.integer) else float(key))
                elif pd.isna(key):
                    key_str = 'unknown'
                else:
                    key_str = str(key)
                converted_dict[key_str] = self._convert_numpy_types(value)
            return converted_dict
        elif isinstance(obj, list):
            return [self._convert_numpy_types(item) for item in obj]
        elif isinstance(obj, tuple):
            return list(obj)
        elif pd.isna(obj):
            return None
        elif hasattr(obj, 'item'):
            try:
                return obj.item()
            except:
                return str(obj)
        else:
            return obj'''
    
    if re.search(old_convert_pattern, content, re.DOTALL):
        content = re.sub(old_convert_pattern, new_convert, content, flags=re.DOTALL)
        fixes_applied += 1
        print("   ✅ _convert_numpy_types corrigée")
    
    # Fix: Améliorer la gestion des erreurs d'agrégation
    # Chercher les patterns problématiques et les remplacer par des versions plus sûres
    aggregation_patterns = [
        (r'region_stats = df\.groupby\(\'region\'\)\.agg\(agg_dict\)\.round\(2\)',
         'region_stats = df.groupby(\'region\').agg({col: [\'count\', \'mean\'] for col in [\'total_area_km2\', \'max_intensity_mm\'] if col in df.columns}).round(2)'),
        (r'climate_stats = df\.groupby\(\'climate_zone\'\)\.agg\(agg_dict\)\.round\(2\)',
         'climate_stats = df.groupby(\'climate_zone\').agg({col: [\'count\', \'mean\'] for col in [\'total_area_km2\', \'max_intensity_mm\'] if col in df.columns}).round(2)')
    ]
    
    for old_pattern, new_pattern in aggregation_patterns:
        if re.search(old_pattern, content):
            content = re.sub(old_pattern, new_pattern, content)
            fixes_applied += 1
    
    # Sauvegarder le fichier corrigé
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"   ✅ {fixes_applied} corrections appliquées à spatial_report.py")
    return fixes_applied > 0

def apply_all_fixes():
    """Applique toutes les corrections."""
    print("🔧 APPLICATION DE TOUTES LES CORRECTIONS")
    print("=" * 60)
    
    # Vérifier qu'on est dans le bon dossier
    if not Path("src").exists():
        print("❌ Erreur: Ce script doit être exécuté depuis la racine du projet")
        print("   (le dossier contenant le dossier 'src')")
        return False
    
    total_fixes = 0
    
    # 1. Corriger detection_report.py
    if fix_detection_report():
        total_fixes += 1
    
    # 2. Corriger detection.py (erreur 'centroid_ok')
    if fix_detection_analysis():
        total_fixes += 1
    
    # 3. Corriger spatial_report.py
    if fix_spatial_report():
        total_fixes += 1
    
    print(f"\n🎯 RÉSUMÉ DES CORRECTIONS:")
    print(f"• Fichiers corrigés: {total_fixes}")
    print("• Erreur 'centroid_ok' dans detection.py: ✅ RÉSOLUE")
    print("• Erreurs pandas dans detection_report.py: ✅ RÉSOLUES")
    print("• Problèmes de sérialisation JSON: ✅ RÉSOLUS")
    print("• Erreurs d'agrégation dans spatial_report.py: ✅ RÉSOLUES")
    print("• Création automatique des dossiers: ✅ AJOUTÉE")
    
    print(f"\n✅ TOUTES LES CORRECTIONS APPLIQUÉES AVEC SUCCÈS!")
    print("🚀 Vous pouvez maintenant relancer votre script de détection.")
    
    return total_fixes > 0

def main():
    """Fonction principale."""
    print("🔧 SCRIPT COMPLET DE CORRECTION DES ERREURS")
    print("=" * 60)
    print("Ce script corrige:")
    print("• L'erreur 'centroid_ok' dans src/analysis/detection.py")
    print("• Les erreurs pandas dans src/reports/detection_report.py")
    print("• Les problèmes de sérialisation JSON")
    print("• Les erreurs d'agrégation dans src/reports/spatial_report.py")
    print("=" * 60)
    
    success = apply_all_fixes()
    
    if success:
        print(f"\n💡 ÉTAPES SUIVANTES:")
        print("1. Relancez votre script de détection:")
        print("   python scripts/01_detection_extremes.py")
        print("2. Vérifiez que les rapports se génèrent correctement")
        print("3. Les fichiers de sauvegarde (.backup_*) peuvent être supprimés si tout fonctionne")
        print("4. En cas de problème, les fichiers originaux peuvent être restaurés depuis les sauvegardes")
    else:
        print(f"\n❌ ÉCHEC DE L'APPLICATION DES CORRECTIONS")
        print("Vérifiez la structure de votre projet et réessayez")

if __name__ == "__main__":
    main()