#!/usr/bin/env python3
# setup.py
"""
Script de configuration et d'installation du projet 

Ce script:
1. Crée la structure de dossiers
2. Installe les dépendances
3. Vérifie la configuration
4. Lance un test de fonctionnement

Utilisation:
    python setup.py
"""

import os
import sys
import subprocess
from pathlib import Path

def create_directory_structure():
    """Crée la structure de dossiers du projet."""
    print("Création de la structure de dossiers...")
    
    directories = [
        "src/config", "src/data", "src/analysis", "src/utils", 
        "src/visualization", "src/reports",
        "scripts", "tests", 
        "data/raw", "data/processed",
        "outputs/data", "outputs/visualizations/detection", 
        "outputs/visualizations/spatial", "outputs/visualizations/temporal",
        "outputs/reports"
    ]
    
    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
    
    print("Structure de dossiers créée avec succès")

def create_init_files():
    """Crée tous les fichiers __init__.py nécessaires."""
    print("Création des fichiers __init__.py...")
    
    init_files = [
        "src/__init__.py",
        "src/config/__init__.py", 
        "src/data/__init__.py",
        "src/analysis/__init__.py",
        "src/utils/__init__.py",
        "src/visualization/__init__.py",
        "src/reports/__init__.py"
    ]
    
    for init_file in init_files:
        Path(init_file).touch()
    
    print("Fichiers __init__.py créés avec succès")

def create_requirements_file():
    """Crée le fichier requirements.txt."""
    print("Création du fichier requirements.txt...")
    
    requirements = """numpy>=1.21.0
pandas>=1.3.0
matplotlib>=3.4.0
seaborn>=0.11.0
scipy>=1.7.0
h5py>=3.3.0
tqdm>=4.61.0
pathlib>=1.0.1
"""
    
    with open("requirements.txt", "w", encoding='utf-8') as f:
        f.write(requirements)
    
    print("Fichier requirements.txt créé avec succès")

def install_dependencies():
    """Installe les dépendances Python."""
    print("Installation des dépendances...")
    
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], 
                      check=True, capture_output=True)
        print("Dépendances installées avec succès")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Erreur lors de l'installation: {e}")
        print("Installez manuellement avec: pip install -r requirements.txt")
        return False

def check_chirps_file():
    """Vérifie la présence du fichier CHIRPS."""
    print("Vérification du fichier CHIRPS...")
    
    chirps_path = Path("data/raw/chirps_WA_1981_2023_dayly.mat")
    
    if chirps_path.exists():
        print(f"Fichier CHIRPS trouvé: {chirps_path}")
        return True
    else:
        print(f"Fichier CHIRPS non trouvé: {chirps_path}")
        print("Veuillez placer votre fichier CHIRPS dans data/raw/")
        return False

def create_example_config():
    """Crée un fichier de configuration d'exemple."""
    print("Création de la configuration d'exemple...")
    
    config_content = '''# Exemple de configuration personnalisée
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
'''
    
    with open("config_example.py", "w", encoding='utf-8') as f:
        f.write(config_content)
    
    print("Configuration d'exemple créée: config_example.py")

def run_validation_test():
    """Lance un test de validation de l'installation."""
    print("Test de validation de l'installation...")
    
    # Test script sans emojis pour éviter les problèmes d'encodage
    test_script = '''
import sys
from pathlib import Path

# Test des imports
try:
    sys.path.insert(0, str(Path("src")))
    
    # Test imports individuels
    try:
        from config.settings import PROJECT_INFO, DETECTION_CRITERIA
        print("OK: Configuration importée")
    except ImportError as e:
        print(f"ERREUR: Configuration - {e}")
        return False
    
    try:
        from data.loader import ChirpsDataLoader
        print("OK: Data loader importé")
    except ImportError as e:
        print(f"ERREUR: Data loader - {e}")
        return False
    
    try:
        from analysis.climatology import calculate_climatology_and_anomalies
        print("OK: Climatologie importée")
    except ImportError as e:
        print(f"ERREUR: Climatologie - {e}")
        return False
    
    try:
        from analysis.detection import ExtremeEventDetector
        print("OK: Détection importée")
    except ImportError as e:
        print(f"ERREUR: Détection - {e}")
        return False
    
    try:
        from utils.season_classifier import SeasonClassifier
        print("OK: Classification saisonnière importée")
    except ImportError as e:
        print(f"ERREUR: Classification - {e}")
        return False
    
    try:
        from visualization.detection_plots import DetectionVisualizer
        print("OK: Visualisation importée")
    except ImportError as e:
        print(f"ERREUR: Visualisation - {e}")
        return False
    
    try:
        from reports.detection_report import DetectionReportGenerator
        print("OK: Rapports importés")
    except ImportError as e:
        print(f"ERREUR: Rapports - {e}")
        return False
    
    print("SUCCÈS: Tous les modules importés correctement")
    print(f"Projet: {PROJECT_INFO.get('title', 'Non défini')}")
    print(f"Critères de détection: {DETECTION_CRITERIA}")
    
    return True
    
except Exception as e:
    print(f"ERREUR INATTENDUE: {e}")
    return False
'''
    
    # Écrire et exécuter le test avec encodage UTF-8
    try:
        with open("validation_test.py", "w", encoding='utf-8') as f:
            f.write(test_script)
        
        result = subprocess.run([sys.executable, "validation_test.py"], 
                              capture_output=True, text=True, encoding='utf-8')
        
        if result.returncode == 0:
            print("Test de validation réussi:")
            print(result.stdout)
            return True
        else:
            print("Test de validation échoué:")
            print("STDOUT:", result.stdout)
            print("STDERR:", result.stderr)
            return False
    except Exception as e:
        print(f"Erreur lors du test: {e}")
        return False
    finally:
        # Nettoyer le fichier de test
        Path("validation_test.py").unlink(missing_ok=True)

def print_next_steps(has_chirps: bool, test_passed: bool):
    """Affiche les prochaines étapes."""
    print("\n" + "="*80)
    print("INSTALLATION TERMINÉE")
    print("="*80)
    
    if test_passed:
        print("SUCCÈS: Tous les modules fonctionnent correctement")
    else:
        print("ATTENTION: Certains modules ont des problèmes - vérifiez les erreurs ci-dessus")
    
    print("\nPROCHAINES ÉTAPES:")
    
    if not has_chirps:
        print("1. OBLIGATOIRE: Placer votre fichier CHIRPS dans data/raw/")
        print("   Nom attendu: chirps_WA_1981_2023_dayly.mat")
        print()
    
    print("2. Lancer l'analyse:")
    print("   python main.py")
    print("   ou")
    print("   python scripts/01_detection_extremes.py")
    print()
    
    print("3. Personnaliser la configuration (optionnel):")
    print("   - Modifier src/config/settings.py")
    print("   - Ajuster les critères de détection")
    print("   - Changer les limites géographiques")
    print()
    
    print("4. Consulter les résultats:")
    print("   - outputs/data/ : Datasets générés")
    print("   - outputs/visualizations/ : Graphiques")
    print("   - outputs/reports/ : Rapports détaillés")
    print()
    
    print("5. Étapes suivantes du mémoire:")
    print("   - Analyse des indices climatiques (SST, ENSO)")
    print("   - Application du machine learning")
    print("   - Développement de modèles prédictifs")

def check_python_version():
    """Vérifie la version de Python."""
    print(f"Version Python: {sys.version}")
    
    if sys.version_info < (3, 8):
        print("ATTENTION: Python 3.8+ recommandé")
        return False
    else:
        print("Version Python compatible")
        return True

def create_missing_modules():
    """Crée les modules manquants avec un contenu minimal."""
    print("Vérification et création des modules manquants...")
    
    modules_to_check = [
        ("src/config/settings.py", "Configuration"),
        ("src/data/loader.py", "Data loader"),
        ("src/analysis/climatology.py", "Climatologie"),
        ("src/analysis/detection.py", "Détection"),
        ("src/utils/season_classifier.py", "Classification"),
        ("src/visualization/detection_plots.py", "Visualisation"),
        ("src/reports/detection_report.py", "Rapports"),
        ("scripts/01_detection_extremes.py", "Script principal"),
        ("main.py", "Point d'entrée")
    ]
    
    missing_modules = []
    
    for module_path, module_name in modules_to_check:
        if not Path(module_path).exists():
            missing_modules.append((module_path, module_name))
    
    if missing_modules:
        print("MODULES MANQUANTS DÉTECTÉS:")
        for module_path, module_name in missing_modules:
            print(f"  - {module_name}: {module_path}")
        
        print("\nCréation de modules stub...")
        
        for module_path, module_name in missing_modules:
            stub_content = f'''# {module_path}
"""
Module stub pour {module_name}.
Ce fichier a été créé automatiquement par le script de setup.
Remplacez ce contenu par le vrai code du module.
"""

print("ATTENTION: Module stub {module_name} - remplacez par le vrai code")

# Stub minimal pour éviter les erreurs d'import
if __name__ == "__main__":
    print("Module {module_name} - Version stub")
'''
            
            try:
                Path(module_path).parent.mkdir(parents=True, exist_ok=True)
                with open(module_path, "w", encoding='utf-8') as f:
                    f.write(stub_content)
                print(f"  Créé: {module_path}")
            except Exception as e:
                print(f"  Erreur création {module_path}: {e}")
        
        print("\nATTENTION: Vous devez remplacer ces modules stub par le vrai code")
        return False
    else:
        print("Tous les modules requis sont présents")
        return True

def main():
    """Fonction principale du script de setup."""
    print("SETUP - Projet d'Analyse des Précipitations Extrêmes au Sénégal")
    print("="*80)
    print("Ce script va configurer votre environnement de travail")
    print()
    
    # Vérifications préliminaires
    python_ok = check_python_version()
    
    # Étapes de configuration
    create_directory_structure()
    create_init_files()
    create_requirements_file()
    
    deps_ok = install_dependencies()
    if not deps_ok:
        print("\nATTENTION: Installation des dépendances échouée")
        print("Continuez manuellement avec: pip install -r requirements.txt")
    
    has_chirps = check_chirps_file()
    create_example_config()
    
    # Vérifier les modules
    modules_ok = create_missing_modules()
    
    test_passed = False
    if deps_ok and modules_ok:
        test_passed = run_validation_test()
    elif not modules_ok:
        print("\nTest de validation ignoré - modules manquants détectés")
        print("Créez d'abord tous les modules nécessaires")
    
    print_next_steps(has_chirps, test_passed)
    
    # Résumé final
    print("\nRÉSUMÉ:")
    print(f"  Python: {'OK' if python_ok else 'ATTENTION'}")
    print(f"  Dépendances: {'OK' if deps_ok else 'ÉCHEC'}")
    print(f"  Fichier CHIRPS: {'OK' if has_chirps else 'MANQUANT'}")
    print(f"  Modules: {'OK' if modules_ok else 'MANQUANTS'}")
    print(f"  Tests: {'OK' if test_passed else 'ÉCHEC/IGNORÉ'}")
    
    return 0 if (deps_ok and (test_passed or not modules_ok)) else 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)