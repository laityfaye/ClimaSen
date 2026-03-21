#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# scripts/03b_split_events_by_phase.py
"""
Script pour diviser les événements extrêmes en trois fichiers selon la phase de saison.

Ce script lit le fichier extreme_events_comprehensive.csv et crée trois fichiers séparés :
- extreme_events_phase_1_debut.csv : Événements du début de saison (Mai-Juin)
- extreme_events_phase_2_pleine.csv : Événements de la pleine saison (Juillet-Août)
- extreme_events_phase_3_fin.csv : Événements de la fin de saison (Septembre-Octobre)

Usage:
    python scripts/03b_split_events_by_phase.py
    python scripts/03b_split_events_by_phase.py --input-file path/to/events.csv
"""

import sys
import os
import io

# Configurer l'encodage UTF-8 pour Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import argparse
from pathlib import Path
import pandas as pd

# Ajouter le répertoire racine au path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

try:
    from src.config.settings import EXPORT_DIR, create_output_directories
    print("[OK] Configuration importee")
except ImportError:
    print("[WARNING] Configuration basique utilisee")
    EXPORT_DIR = project_root / "outputs" / "exports"
    def create_output_directories():
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)

def split_events_by_phase(input_file: Path, output_dir: Path):
    """
    Divise les événements extrêmes en trois fichiers selon la phase de saison.
    
    Args:
        input_file: Chemin vers le fichier CSV d'entrée
        output_dir: Répertoire de sortie pour les fichiers divisés
    """
    print(f"\n{'='*70}")
    print("DIVISION DES EVENEMENTS EXTRÊMES PAR PHASE DE SAISON")
    print(f"{'='*70}\n")
    
    # Vérifier que le fichier d'entrée existe
    if not input_file.exists():
        print(f"[ERREUR] Fichier d'entree non trouve: {input_file}")
        return False
    
    print(f"Lecture du fichier: {input_file}")
    
    # Lire le fichier CSV
    try:
        df = pd.read_csv(input_file)
        print(f"[OK] {len(df)} evenements charges")
    except Exception as e:
        print(f"[ERREUR] Erreur lors de la lecture du fichier: {e}")
        return False
    
    # Vérifier que la colonne 'phase' existe
    if 'phase' not in df.columns:
        print("[ERREUR] Colonne 'phase' introuvable dans le fichier CSV")
        print(f"   Colonnes disponibles: {', '.join(df.columns)}")
        return False
    
    # Créer le répertoire de sortie si nécessaire
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Définir les phases et leurs fichiers de sortie
    phases_config = {
        'Phase_1_debut': {
            'filename': 'extreme_events_phase_1_debut.csv',
            'description': 'Début de saison (Mai-Juin)',
            'months': [5, 6]
        },
        'Phase_2_pleine': {
            'filename': 'extreme_events_phase_2_pleine.csv',
            'description': 'Pleine saison (Juillet-Août)',
            'months': [7, 8]
        },
        'Phase_3_fin': {
            'filename': 'extreme_events_phase_3_fin.csv',
            'description': 'Fin de saison (Septembre-Octobre)',
            'months': [9, 10]
        }
    }
    
    # Statistiques globales
    total_events = len(df)
    phase_counts = df['phase'].value_counts()
    
    print(f"\nStatistiques des phases:")
    print(f"   Total d'evenements: {total_events}")
    for phase, count in phase_counts.items():
        pct = (count / total_events) * 100 if total_events > 0 else 0
        print(f"   {phase}: {count} evenements ({pct:.1f}%)")
    
    # Diviser et sauvegarder pour chaque phase
    results = {}
    print(f"\n{'-'*70}")
    print("Division des evenements par phase:")
    print(f"{'-'*70}\n")
    
    for phase_key, phase_info in phases_config.items():
        # Filtrer les événements de cette phase
        phase_df = df[df['phase'] == phase_key].copy()
        
        if len(phase_df) == 0:
            print(f"[WARNING] {phase_key} ({phase_info['description']}): 0 evenements")
            continue
        
        # Chemin du fichier de sortie
        output_file = output_dir / phase_info['filename']
        
        # Sauvegarder le fichier
        try:
            phase_df.to_csv(output_file, index=False)
            results[phase_key] = {
                'count': len(phase_df),
                'file': output_file,
                'success': True
            }
            print(f"[OK] {phase_key} ({phase_info['description']}):")
            print(f"   -> {len(phase_df)} evenements sauvegardes")
            print(f"   -> Fichier: {output_file}")
            
            # Afficher quelques statistiques
            if 'year' in phase_df.columns:
                years = phase_df['year'].unique()
                print(f"   -> Periode: {years.min()} - {years.max()} ({len(years)} annees)")
            
        except Exception as e:
            print(f"[ERREUR] Erreur lors de la sauvegarde de {phase_key}: {e}")
            results[phase_key] = {
                'count': len(phase_df),
                'file': output_file,
                'success': False,
                'error': str(e)
            }
    
    # Résumé final
    print(f"\n{'='*70}")
    print("RESUME")
    print(f"{'='*70}\n")
    
    successful_phases = [k for k, v in results.items() if v.get('success', False)]
    total_saved = sum(v['count'] for k, v in results.items() if v.get('success', False))
    
    if successful_phases:
        print(f"[OK] {len(successful_phases)} fichier(s) cree(s) avec succes")
        print(f"   Total d'evenements sauvegardes: {total_saved}")
        print(f"\nFichiers crees dans: {output_dir}")
        for phase_key in successful_phases:
            phase_info = phases_config[phase_key]
            result = results[phase_key]
            print(f"   - {phase_info['filename']} ({result['count']} evenements)")
    else:
        print("[ERREUR] Aucun fichier n'a ete cree")
        return False
    
    # Vérifier s'il y a des événements hors saison
    other_phases = df[~df['phase'].isin(phases_config.keys())]
    if len(other_phases) > 0:
        print(f"\n[WARNING] {len(other_phases)} evenement(s) hors saison detecte(s)")
        print(f"   Phases: {', '.join(other_phases['phase'].unique())}")
    
    print(f"\n{'='*70}\n")
    return True

def main():
    """Fonction principale."""
    parser = argparse.ArgumentParser(
        description="Diviser les événements extrêmes par phase de saison",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples:
  python scripts/03b_split_events_by_phase.py
  python scripts/03b_split_events_by_phase.py --input-file outputs/exports/events.csv
        """
    )
    
    parser.add_argument(
        '--input-file',
        type=str,
        default=None,
        help='Chemin vers le fichier CSV des événements extrêmes (défaut: outputs/exports/extreme_events_comprehensive.csv)'
    )
    
    parser.add_argument(
        '--output-dir',
        type=str,
        default=None,
        help='Répertoire de sortie (défaut: outputs/exports)'
    )
    
    args = parser.parse_args()
    
    # Déterminer le fichier d'entrée
    if args.input_file:
        input_file = Path(args.input_file)
    else:
        input_file = EXPORT_DIR / "extreme_events_comprehensive.csv"
    
    # Déterminer le répertoire de sortie
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_dir = EXPORT_DIR
    
    # Créer les répertoires nécessaires
    create_output_directories()
    
    # Exécuter la division
    success = split_events_by_phase(input_file, output_dir)
    
    if success:
        print("[OK] Script termine avec succes!")
        return 0
    else:
        print("[ERREUR] Script termine avec des erreurs")
        return 1

if __name__ == "__main__":
    sys.exit(main())
