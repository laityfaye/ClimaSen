"""Outils de Jarvis - Phase 2: lecture seule des donnees de la plateforme.

Quatre outils publics, tous adosses aux loaders du dashboard:

    get_sst_index          valeurs des indices SST (load_sst)
    search_extreme_events  catalogue des evenements extremes (load_events)
    get_teleconnection     correlations SST / pluies extremes (load_telecon)
    get_risk_cluster       regimes oceaniques du K-Means (load_clustering)

Aucun outil n ecrit quoi que ce soit: le profil public ne peut que lire.
"""
from .dataset import DataUnavailableError, preload
from .registry import MAX_RESULT_CHARS, TOOLS, execute, label_for, specs_for

__all__ = [
    "DataUnavailableError",
    "MAX_RESULT_CHARS",
    "TOOLS",
    "execute",
    "label_for",
    "preload",
    "specs_for",
]
