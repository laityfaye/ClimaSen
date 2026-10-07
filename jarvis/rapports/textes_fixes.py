"""Textes que le modele ne redige pas et ne peut pas modifier.

Mentions officielles, avertissements et limites sont inseres par le code,
apres la redaction: une consigne au modele pourrait etre oubliee ou
reformulee jusqu'a perdre son sens; un texte fixe, non.
"""

SOURCES = {
    "CHIRPS": "CHIRPS v2 (Climate Hazards Center, UCSB), pluie journalière, grille 0,25°, 1981-2023",
    "OISST": "NOAA OISST v2, anomalies journalières de température de surface de la mer, "
             "grille 0,25°, 1983-2023",
    "RGPH5": "ANSD, 5e Recensement général de la population et de l'habitat (RGPH-5), 2023",
    "RGPH2013": "ANSD, RGPH 2013",
    "EHCVM": "ANSD, Enquête harmonisée sur les conditions de vie des ménages (EHCVM) 2021-2022",
    "OCHA": "OCHA COD-AB Sénégal v02 (2024), limites administratives",
    "C3S": "Copernicus C3S, prévision saisonnière ECMWF SEAS5, calibrée sur CHIRPS",
    "INONDATIONS": "Inondations documentées 2005-2020 (PDNA 2009, UNOSAT, FICR, OCHA)",
}

# Libelles courts, pour les pieds de figure.
SOURCE_CHIRPS = "CHIRPS v2"
SOURCE_OISST = "NOAA OISST v2"
SOURCE_RGPH5 = "ANSD RGPH-5"
SOURCE_EHCVM = "ANSD EHCVM 2021-2022"
SOURCE_INDICE = "CHIRPS v2 ; ANSD RGPH-5 ; ANSD EHCVM 2021-2022 ; OCHA COD-AB"

MENTION_ANACIM = (
    "Ce document complète les alertes et prévisions officielles de l'Agence nationale de "
    "l'aviation civile et de la météorologie (ANACIM) ; il ne les remplace pas. En cas "
    "d'alerte, seules les consignes de l'ANACIM et des autorités de protection civile font foi."
)

AVERTISSEMENT_CORRELATION = (
    "Une corrélation statistique décrit un lien observé sur 1983-2023 ; elle ne constitue "
    "pas une prévision et n'établit pas, à elle seule, une relation de cause à effet."
)

AVERTISSEMENT_PROJECTION = (
    "Les probabilités et niveaux de risque annoncés pour une saison à venir sont des "
    "projections. Leur fiabilité mesurée est indiquée à côté de chaque valeur ; une "
    "projection n'est jamais une certitude."
)

AVERTISSEMENT_INDICE = (
    "L'indice de risque classe les zones entre elles (rangs centiles de 0 à 1). Ce n'est "
    "ni une probabilité d'inondation, ni un nombre de sinistrés, ni une prévision de la "
    "saison à venir."
)

LEGENDE_STATUTS = (
    "Chaque énoncé chiffré porte un statut : « Observé » (mesuré dans les données), "
    "« Corrélé » (lien statistique, pas une prévision), « Projeté » (indication pour une "
    "saison à venir, avec sa fiabilité) ou « Méthode » (paramètre de calcul)."
)

# Limites, assemblees selon les drapeaux leves par les collecteurs.
LIMITES = {
    "couverture_chirps": "Les données de pluie couvrent 1981-2023 : les saisons 2024 à 2026 "
                         "ne sont pas encore intégrées au catalogue d'événements.",
    "couverture_oisst": "Les indices océaniques (OISST) commencent en 1983 : les "
                        "corrélations portent sur 41 saisons (1983-2023).",
    "resolution": "Résolution de 0,25° (environ 27 km) pour la pluie (CHIRPS) comme pour "
                  "l'océan (OISST) : un pixel couvre plusieurs communes, et les petites zones "
                  "urbaines prennent la valeur du pixel le plus proche.",
    "evenements_nationaux": "Un événement extrême est une journée où une partie du territoire "
                            "dépasse 2 écarts-types de la climatologie du jour ; il est rattaché "
                            "ici à la zone où son intensité a été maximale.",
    "multiplicite_tests": "Beaucoup de corrélations sont testées (66 par phase et par "
                          "métrique, 330 par phase) sans correction pour tests multiples : au "
                          "seuil de 5 %, environ 3 corrélations sur 66 sortent significatives "
                          "par hasard. Seuls les signaux cohérents sur des décalages voisins "
                          "sont mis en avant.",
    "metrique_intensite": "Les corrélations portent sur l'intensité des pluies extrêmes, pas "
                          "sur le cumul saisonnier : leurs signes peuvent différer de ceux "
                          "publiés pour la pluie totale.",
    "clusters_descriptifs": "Les configurations océaniques (K-Means) sont une typologie "
                            "descriptive : faible séparation (silhouette), et elles regroupent "
                            "surtout les événements d'une même saison. Les 4 états saisonniers "
                            "(El Niño, La Niña, neutre, transition) sont, eux, robustes.",
    "vulnerabilite_provisoire": "La composante vulnérabilité est provisoire : elle repose sur "
                                "la pauvreté connue à l'échelle régionale (EHCVM 2021-2022) et sur "
                                "la croissance démographique 2013-2023, en attendant les données "
                                "d'habitat du RGPH-5.",
    "biais_dakar": "Les zones de la région de Dakar sortent bas dans l'indice malgré des "
                   "inondations récurrentes : la pauvreté régionale y est la plus faible du pays "
                   "et la croissance récente modérée. Ce classement ne doit pas être lu comme "
                   "une absence de risque d'inondation urbaine.",
    "validation_indice": "Face aux inondations documentées 2005-2020, l'indice ne retrouve pas "
                         "mieux que le hasard les départements touchés (surtout urbains) ; "
                         "l'exposition seule les distingue mieux. L'indice n'est pas une carte "
                         "des inondations.",
    "echelle_arrondissement": "L'indice n'est pas calculé à l'échelle de la commune : la "
                              "commune demandée est décrite par l'indice de son arrondissement, "
                              "et seule sa population vient de la commune elle-même.",
    "donnees_absentes": "Données que la plateforme n'a pas : pauvreté par département, "
                        "habitat RGPH-5 par département (logement, assainissement, évacuation "
                        "des eaux), valeurs départementales de l'Atlas RGPH-5.",
    "competence_veille": "La compétence de la veille pré-saison n'est pas démontrée en "
                         "prévision réelle : les scores mesurés sont indiqués dans le rapport.",
    "modules_en_developpement": "Les modules Vulnérabilité et Veille pré-saison sont en cours "
                                "de développement : leurs méthodes peuvent encore évoluer.",
    "tendance": "Une tendance sur 43 ans est sensible aux années extrêmes et à la période "
                "choisie ; une tendance non significative n'exclut pas un changement réel.",
    "periode_reduite": "La période demandée est plus courte que la période complète : "
                       "moins d'années, donc moins de puissance statistique.",
}

ORDRE_LIMITES = tuple(LIMITES)

METHODOLOGIES = {
    "historique": (
        "Les événements de pluie extrême sont détectés dans CHIRPS (pluie journalière, "
        "0,25°, 1981-2023) : une journée est retenue lorsque l'anomalie standardisée dépasse "
        "2 écarts-types de la climatologie du jour sur une partie du territoire. Chaque "
        "événement est décrit par sa date, sa phase de saison (début : mai-juin ; cœur : "
        "juillet-août ; fin : septembre-octobre), son intensité maximale (mm/jour), sa "
        "couverture spatiale et la zone où l'intensité a été maximale. Les tendances sont "
        "estimées par la pente de Sen et testées par le test de Mann-Kendall."
    ),
    "teleconnexions": (
        "Pour chaque phase de saison, les métriques annuelles des événements extrêmes "
        "(intensité maximale, intensité moyenne, anomalie maximale, couverture, nombre "
        "d'événements) sont corrélées aux 11 indices de température de surface de la mer "
        "(NOAA OISST v2) moyennés sur les mois précédant la phase (décalages de 0 à 5 mois), "
        "sur 1983-2023, après retrait de la tendance linéaire. Les p-values sont corrigées de "
        "l'autocorrélation (taille d'échantillon effective, Chelton 1983). Les intervalles de "
        "confiance à 95 % sont calculés par la transformation de Fisher sur la taille "
        "effective. Une corrélation est dite robuste si elle est significative après "
        "correction, confirmée par le rang de Spearman et cohérente sur un décalage voisin. "
        "Les configurations océaniques types proviennent d'un K-Means sur les champs de SST "
        "du jour de chaque événement."
    ),
    "vulnerabilite": (
        "L'indice de risque combine trois composantes, chacune convertie en rang centile "
        "de 0 (plus faible) à 1 (plus fort) : l'aléa (jours par an d'anomalie supérieure à "
        "2 écarts-types et jours à plus de 50 mm, CHIRPS 1981-2023, mai-octobre), "
        "l'exposition (population et densité 2023, ANSD RGPH-5) et la vulnérabilité "
        "(pauvreté régionale EHCVM 2021-2022 et croissance 2013-2023). Indice = (aléa × "
        "exposition × vulnérabilité)^(1/3), calculé pour 46 départements et 125 "
        "arrondissements (limites OCHA COD-AB). La population des communes vient du RGPH-5."
    ),
    "veille": (
        "Le bulletin de veille pré-saison estime le risque qu'une saison soit une « année "
        "extrême » (empreinte saisonnière des événements extrêmes dans le tiers supérieur "
        "des années 1981-2023). Le niveau de risque n'est annoncé qu'à partir de la "
        "prévision saisonnière Copernicus C3S calibrée sur CHIRPS ; la projection de l'état "
        "océanique de novembre à avril sur les configurations du mémoire reste une indication "
        "expérimentale. Les zones prioritaires sont celles de l'indice de risque "
        "(module Vulnérabilité)."
    ),
}

PUBLICS = {
    "decideur": "décideurs (protection civile, collectivités)",
    "technique": "experts et chercheurs (ANSD, ANACIM, universités)",
}
