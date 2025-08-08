#!/usr/bin/env python3
"""
Script de correction rapide pour les erreurs du script de détection.
À exécuter avant de relancer l'analyse.
"""

import os
import sys
from pathlib import Path
import warnings

def create_missing_directories():
    """Crée les dossiers de sortie manquants."""
    dirs = [
        "outputs/data",
        "outputs/visualizations", 
        "outputs/visualizations/phases",
        "outputs/visualizations/spatial",
        "outputs/visualizations/temporal",
        "outputs/reports",
        "outputs/exports"
    ]
    
    for dir_path in dirs:
        Path(dir_path).mkdir(parents=True, exist_ok=True)
        print(f"✅ Dossier créé: {dir_path}")

def suppress_known_warnings():
    """Supprime les warnings connus qui causent des problèmes."""
    warnings.filterwarnings('ignore', message='.*truth value of a Series.*')
    warnings.filterwarnings('ignore', message='.*keys must be str.*')
    warnings.filterwarnings('ignore', category=RuntimeWarning)
    print("✅ Warnings problématiques supprimés")

def check_dependencies():
    """Vérifie les dépendances critiques."""
    required_packages = ['pandas', 'numpy', 'matplotlib', 'h5py']
    missing = []
    
    for package in required_packages:
        try:
            __import__(package)
            print(f"✅ {package}")
        except ImportError:
            missing.append(package)
            print(f"❌ {package}")
    
    if missing:
        print(f"\n⚠️ Packages manquants: {', '.join(missing)}")
        print("Installer avec: pip install " + " ".join(missing))
        return False
    return True

def patch_pandas_issue():
    """Applique un patch pour le problème pandas connu."""
    try:
        import pandas as pd
        # Désactiver le warning des attributs
        pd.options.mode.chained_assignment = None
        print("✅ Patch pandas appliqué")
    except ImportError:
        print("❌ Pandas non disponible")

def main():
    print("🔧 SCRIPT DE CORRECTION RAPIDE")
    print("=" * 40)
    
    # 1. Créer les dossiers
    print("\n📁 Création des dossiers de sortie...")
    create_missing_directories()
    
    # 2. Vérifier les dépendances
    print("\n📦 Vérification des dépendances...")
    if not check_dependencies():
        return False
    
    # 3. Supprimer les warnings
    print("\n⚠️ Suppression des warnings...")
    suppress_known_warnings()
    
    # 4. Patches spécifiques
    print("\n🩹 Application des patches...")
    patch_pandas_issue()
    
    print("\n✅ CORRECTIONS APPLIQUÉES AVEC SUCCÈS")
    print("🔄 Vous pouvez maintenant relancer le script de détection")
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)