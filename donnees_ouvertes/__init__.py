"""API ouverte de ClimatSen : les statistiques produites par la plateforme,
en lecture seule, en JSON, CSV, GeoJSON et SDMX (CSV 2.0 et JSON 2.0).

Paquet volontairement separe de jarvis/ : il ne depend ni de Claude, ni des
sessions, ni de Streamlit. Le serveur d'IRIS le monte sous /api/v1 :

    app.mount("/api/v1", creer_api(ip_client=...))

Les donnees sont lues dans outputs/ et data/processed/, telles que produites
par les scripts 26 a 34 ; l'API ne recalcule rien.
"""
from .app import creer_api

__all__ = ["creer_api"]
