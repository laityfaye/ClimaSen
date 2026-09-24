"""Figures produites par Jarvis (Phase 8): magasin et rendu.

Le magasin garde la SPECIFICATION d'une figure (type + donnees deja
calculees), pas une image. Le PNG est dessine a la premiere demande, dans le
theme du widget qui la demande (clair ou sombre), puis mis en cache. Une meme
figure s'affiche ainsi correctement quand l'utilisateur bascule de theme, et
la specification sert aussi a produire la vue tableau (CSV).

Trois garanties:
  - une figure n'est lisible QUE par la session qui l'a produite: son
    identifiant seul ne suffit pas;
  - le magasin est borne (par session, au total) et oublie les figures au
    bout du TTL des conversations;
  - le rendu n'utilise pas pyplot (etat global, non sur entre threads) mais
    l'API objet de matplotlib, sous un verrou pour les reglages de police.

Choix graphiques (voir la palette validee dans le README): une seule echelle
par figure, palette categorielle en ordre fixe, divergente bleu/rouge avec un
milieu gris pour les correlations, grille recessive, etiquettes directes en
bout de courbe. Le titre n'est PAS dessine dans l'image: le widget l'affiche
en HTML, plus lisible dans une bulle etroite.
"""
import csv
import io
import secrets
import threading
import time
from collections import OrderedDict

THEMES = ("clair", "sombre", "hud")

# Palette validee (scripts/validate_palette.js du guide dataviz) sur les fonds
# exacts des bulles du widget: #FFFFFF et #1E293B. En clair, les series 3 et 4
# sont sous 3:1 de contraste: d'ou les etiquettes directes et la vue CSV.
PALETTES = {
    "clair": {
        "fond": "#FFFFFF", "encre": "#0B0B0B", "encre2": "#52514E",
        "grille": "#E8E7E4", "zero": "#9A9893",
        "series": ["#2A78D6", "#EB6834", "#1BAF7A", "#EDA100"],
        "divergente": ["#184F95", "#6DA7EC", "#F0EFEC", "#EC8A89", "#B83232"],
    },
    "sombre": {
        "fond": "#1E293B", "encre": "#FFFFFF", "encre2": "#C3C2B7",
        "grille": "#334155", "zero": "#64748B",
        "series": ["#3987E5", "#D95926", "#199E70", "#C98500"],
        "divergente": ["#6DA7EC", "#2A5C9E", "#383835", "#A33A3A", "#E66767"],
    },
    # Interface J.A.R.V.I.S: fond des bulles du widget (#07121A), encre
    # cyan pale. Series validees sur ce fond (validate_palette.js, mode dark).
    "hud": {
        "fond": "#07121A", "encre": "#E0F7FF", "encre2": "#7FB8C8",
        "grille": "#12303A", "zero": "#2B5563",
        "series": ["#3987E5", "#D95926", "#199E70", "#C98500"],
        "divergente": ["#6DA7EC", "#2A5C9E", "#1F3640", "#A33A3A", "#E66767"],
    },
}

MAX_SERIES = 4
LARGEUR_POUCES = 3.4     # affichee ~330 px dans la bulle: texte ~11 px
DPI = 280

_verrou_rendu = threading.Lock()

# Cache des PNG rendus, GLOBAL et borne. Phase 12: un cache attache a chaque
# figure laissait un visiteur, meme bride en debit, accumuler 1000 figures x 2
# themes x ~100 Ko, soit ~200 Mo de memoire. Au-dela de ce plafond, on
# redessine a la demande (quelques dixiemes de seconde).
MAX_RENDUS_EN_CACHE = 60
_rendus = OrderedDict()
_verrou_cache = threading.Lock()


# =============================================================================
# Magasin
# =============================================================================
class Figure:
    def __init__(self, session_id: str, spec: dict):
        self.id = secrets.token_hex(12)
        self.session_id = session_id
        self.spec = spec
        self.cree_le = time.time()

    def vue_publique(self) -> dict:
        return {"id": self.id, "titre": self.spec.get("titre", ""),
                "sous_titre": self.spec.get("sous_titre", "")}


class FigureStore:
    def __init__(self, ttl_seconds: int = 3600, max_par_session: int = 40,
                 maximum: int = 1000):
        self.ttl = ttl_seconds
        self.max_par_session = max_par_session
        self.maximum = maximum
        self._figures = OrderedDict()
        self._lock = threading.Lock()

    def deposer(self, session_id: str, spec: dict) -> Figure:
        figure = Figure(session_id, spec)
        with self._lock:
            self._purger_verrouille()
            miennes = [f for f in self._figures.values()
                       if f.session_id == session_id]
            if len(miennes) >= self.max_par_session:
                del self._figures[miennes[0].id]
            while len(self._figures) >= self.maximum:
                self._figures.popitem(last=False)
            self._figures[figure.id] = figure
        return figure

    def obtenir(self, session_id: str, figure_id: str):
        """La figure, ou None si inconnue, expiree ou d'une autre session.

        Les trois cas se confondent volontairement: un tiers ne doit pas
        pouvoir tester l'existence d'un identifiant.
        """
        with self._lock:
            figure = self._figures.get(figure_id)
            if figure is None or figure.session_id != session_id:
                return None
            if time.time() - figure.cree_le > self.ttl:
                del self._figures[figure_id]
                return None
            return figure

    def _purger_verrouille(self) -> None:
        limite = time.time() - self.ttl
        for fid in [f.id for f in self._figures.values() if f.cree_le < limite]:
            del self._figures[fid]

    def purger(self) -> int:
        with self._lock:
            avant = len(self._figures)
            self._purger_verrouille()
            return avant - len(self._figures)

    def taille(self) -> int:
        with self._lock:
            return len(self._figures)


# =============================================================================
# Vue tableau
# =============================================================================
def en_csv(spec: dict) -> str:
    """Les donnees de la figure en CSV: l'alternative accessible a l'image."""
    d = spec["donnees"]
    sortie = io.StringIO()
    ecrivain = csv.writer(sortie, lineterminator="\n")
    genre = spec["genre"]
    if genre == "carte_chaleur":
        ecrivain.writerow([d.get("titre_lignes", "")] + [str(c) for c in d["colonnes"]])
        for nom, valeurs in zip(d["lignes"], d["valeurs"]):
            ecrivain.writerow([nom] + ["" if v is None else v for v in valeurs])
    elif genre == "courbes":
        ecrivain.writerow([d.get("x_label", "x")] + [s["nom"] for s in d["series"]])
        for i, x in enumerate(d["x"]):
            ecrivain.writerow([x] + ["" if s["y"][i] is None else s["y"][i]
                                     for s in d["series"]])
    elif genre == "barres":
        entete = [d.get("x_label", ""), d.get("y_label", "")]
        tendance = d.get("tendance")
        if tendance:
            entete.append(tendance["nom"])
        ecrivain.writerow(entete)
        for i, (cat, val) in enumerate(zip(d["categories"], d["valeurs"])):
            ligne = [cat, val]
            if tendance:
                ligne.append(tendance["y"][i])
            ecrivain.writerow(ligne)
    return sortie.getvalue()


# =============================================================================
# Rendu
# =============================================================================
def _preparer_axes(ax, p):
    ax.set_facecolor(p["fond"])
    for cote in ("top", "right"):
        ax.spines[cote].set_visible(False)
    for cote in ("left", "bottom"):
        ax.spines[cote].set_color(p["grille"])
    ax.tick_params(colors=p["encre2"], length=0, pad=3)
    ax.yaxis.label.set_color(p["encre2"])
    ax.xaxis.label.set_color(p["encre2"])
    ax.grid(True, axis="y", color=p["grille"], linewidth=0.6)
    ax.set_axisbelow(True)


def _courbes(fig, spec, p):
    d = spec["donnees"]
    ax = fig.add_subplot(111)
    _preparer_axes(ax, p)
    x = list(range(len(d["x"]))) if d.get("x_categoriel") else d["x"]
    if d.get("ligne_zero", True):
        ax.axhline(0, color=p["zero"], linewidth=0.8, zorder=1)
    traces, fins = [], []
    for rang, serie in enumerate(d["series"][:MAX_SERIES]):
        couleur = p["series"][rang]
        xs = [xi for xi, yi in zip(x, serie["y"]) if yi is not None]
        ys = [yi for yi in serie["y"] if yi is not None]
        trace, = ax.plot(xs, ys, color=couleur, linewidth=1.6, zorder=3,
                         solid_capstyle="round")
        traces.append(trace)
        pleins = serie.get("marqueurs_pleins")
        if pleins is not None:
            # Marqueur plein = significatif, creux = non significatif: la
            # significativite ne repose pas sur la couleur seule.
            for xi, yi, plein in zip(x, serie["y"], pleins):
                if yi is None:
                    continue
                ax.plot([xi], [yi], marker="o", markersize=4.5, zorder=4,
                        markerfacecolor=couleur if plein else p["fond"],
                        markeredgecolor=couleur, markeredgewidth=1.2)
        if ys:
            fins.append((serie["nom"], xs[-1], ys[-1]))
    if d.get("x_categoriel"):
        ax.set_xticks(x)
        ax.set_xticklabels([str(v) for v in d["x"]])
    if len(fins) > 1:
        _etiquettes_directes(ax, fins, p)
        ax.margins(x=0.12)
        # Poignees explicites: sans elles, matplotlib numerote TOUS les
        # traces, ligne du zero comprise, et decale les noms (constate).
        legende = ax.legend(traces, [s["nom"] for s in d["series"][:MAX_SERIES]],
                            loc="upper center", bbox_to_anchor=(0.5, -0.2),
                            ncol=min(4, len(d["series"])), frameon=False,
                            fontsize=7, handlelength=1.2, columnspacing=1.0)
        for texte in legende.get_texts():
            texte.set_color(p["encre2"])
    ax.set_xlabel(d.get("x_label", ""))
    ax.set_ylabel(d.get("y_label", ""))


def _etiquettes_directes(ax, fins, p):
    """Noms en bout de courbe, seulement s'ils tiennent a leur place.

    Des etiquettes ecartees pour ne pas se chevaucher ne sont plus en face de
    leur courbe: le lecteur les attribue a la mauvaise ligne (constate sur
    AMO / Nino12 / AMM, qui finissent a quelques centiemes). Dans ce cas on
    n'en pose aucune et la legende, toujours presente, fait le travail.
    """
    bas, haut = ax.get_ylim()
    ecart = 0.07 * (haut - bas)
    ordonnees = sorted(y for _, _, y in fins)
    if any(b - a < ecart for a, b in zip(ordonnees, ordonnees[1:])):
        return False
    for nom, x, y in fins:
        ax.annotate(nom, (x, y), xytext=(5, 0), textcoords="offset points",
                    va="center", fontsize=7, color=p["encre"],
                    annotation_clip=False)
    return True


def _barres(fig, spec, p):
    d = spec["donnees"]
    ax = fig.add_subplot(111)
    _preparer_axes(ax, p)
    positions = list(range(len(d["categories"])))
    couleur = p["series"][0]
    if d.get("horizontal"):
        ax.grid(False)
        ax.grid(True, axis="x", color=p["grille"], linewidth=0.6)
        ax.barh(positions, d["valeurs"], color=couleur, height=0.72,
                edgecolor=p["fond"], linewidth=1.0, zorder=3)
        ax.set_yticks(positions)
        ax.set_yticklabels(d["categories"])
        ax.invert_yaxis()
        ax.set_xlabel(d.get("y_label", ""))
        for pos, val in zip(positions, d["valeurs"]):
            ax.annotate(_nombre(val), (val, pos), xytext=(3, 0),
                        textcoords="offset points", va="center",
                        fontsize=6.5, color=p["encre2"])
        ax.margins(x=0.12)
    else:
        ax.bar(positions, d["valeurs"], color=couleur, width=0.78,
               edgecolor=p["fond"], linewidth=1.0, zorder=3)
        tendance = d.get("tendance")
        if tendance:
            ax.plot(positions, tendance["y"], color=p["encre"], linewidth=1.2,
                    linestyle=(0, (4, 2)), zorder=4, label=tendance["nom"])
            legende = ax.legend(loc="upper left", frameon=False, fontsize=7)
            for texte in legende.get_texts():
                texte.set_color(p["encre2"])
        pas = max(1, len(positions) // 8)
        ax.set_xticks(positions[::pas])
        ax.set_xticklabels([str(c) for c in d["categories"]][::pas])
        ax.set_xlabel(d.get("x_label", ""))
        ax.set_ylabel(d.get("y_label", ""))


def _nombre(v):
    if v is None:
        return ""
    return ("%d" % v) if float(v).is_integer() else ("%.1f" % v)


def _carte_chaleur(fig, spec, p):
    import numpy as np
    from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm

    d = spec["donnees"]
    ax = fig.add_subplot(111)
    ax.set_facecolor(p["fond"])
    for cote in ax.spines.values():
        cote.set_visible(False)
    ax.tick_params(colors=p["encre2"], length=0, pad=2)

    valeurs = np.array([[np.nan if v is None else v for v in ligne]
                        for ligne in d["valeurs"]], dtype=float)
    vmax = d.get("vmax", 0.6)
    carte = LinearSegmentedColormap.from_list("divergente", p["divergente"])
    image = ax.imshow(valeurs, cmap=carte, aspect="auto",
                      norm=TwoSlopeNorm(vmin=-vmax, vcenter=0, vmax=vmax))
    # Separation de 1 px couleur du fond entre les cellules.
    # Separations interieures seulement: celles du bord laissaient un
    # liseré de couleur sur le cote droit (constate).
    ax.set_xticks(np.arange(0.5, valeurs.shape[1] - 1, 1), minor=True)
    ax.set_yticks(np.arange(0.5, valeurs.shape[0] - 1, 1), minor=True)
    ax.grid(which="minor", color=p["fond"], linewidth=1.2)
    ax.tick_params(which="minor", length=0)

    ax.set_xticks(range(len(d["colonnes"])))
    ax.set_xticklabels([str(c) for c in d["colonnes"]], fontsize=7)
    ax.set_yticks(range(len(d["lignes"])))
    ax.set_yticklabels(d["lignes"], fontsize=7)
    ax.set_xlabel(d.get("titre_colonnes", ""), color=p["encre2"])

    etoiles = d.get("etoiles") or []
    for i, ligne in enumerate(etoiles):
        for j, marque in enumerate(ligne):
            if not marque:
                continue
            fond = carte(image.norm(valeurs[i, j]))
            luminance = 0.2126 * fond[0] + 0.7152 * fond[1] + 0.0722 * fond[2]
            ax.text(j, i, marque, ha="center", va="center", fontsize=6.5,
                    color="#0B0B0B" if luminance > 0.5 else "#FFFFFF")

    barre = fig.colorbar(image, ax=ax, fraction=0.05, pad=0.03)
    barre.outline.set_visible(False)
    barre.ax.tick_params(colors=p["encre2"], length=0, labelsize=6.5)
    barre.set_label(d.get("legende_couleur", "r"), color=p["encre2"], fontsize=7)


_DESSINS = {"courbes": _courbes, "barres": _barres, "carte_chaleur": _carte_chaleur}


def rendre(spec: dict, theme: str = "clair") -> bytes:
    """Dessine la figure en PNG. Pur: ne depend que de la specification."""
    import matplotlib
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure as FigureMpl

    if theme not in PALETTES:
        theme = "clair"
    p = PALETTES[theme]
    hauteur = spec.get("hauteur_pouces", 2.5)
    reglages = {"font.size": 7.5, "axes.labelsize": 7.5, "xtick.labelsize": 7,
                "ytick.labelsize": 7, "font.family": "DejaVu Sans"}
    with _verrou_rendu, matplotlib.rc_context(reglages):
        fig = FigureMpl(figsize=(LARGEUR_POUCES, hauteur), dpi=DPI,
                        facecolor=p["fond"])
        FigureCanvasAgg(fig)
        _DESSINS[spec["genre"]](fig, spec, p)
        fig.tight_layout(pad=0.4)
        tampon = io.BytesIO()
        fig.savefig(tampon, format="png", facecolor=p["fond"])
    return tampon.getvalue()


def rendu_en_cache(figure: Figure, theme: str) -> bytes:
    theme = theme if theme in PALETTES else "clair"
    cle = (figure.id, theme)
    with _verrou_cache:
        if cle in _rendus:
            _rendus.move_to_end(cle)
            return _rendus[cle]
    png = rendre(figure.spec, theme)
    with _verrou_cache:
        _rendus[cle] = png
        while len(_rendus) > MAX_RENDUS_EN_CACHE:
            _rendus.popitem(last=False)
    return png
