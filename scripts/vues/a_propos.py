"""Page A propos : projet, donnees, equipe (les emails ne sont plus repetes
dans la barre laterale de chaque page - revue 27/09/2026, point 19)."""
import html

import streamlit as st

EQUIPE = (
    ("LF", "Laity FAYE", "Ingénieur en Génie Logiciel", "laity.faye@univ-thies.sn",
     "Université Iba Der Thiam de Thiès", "#6366F1,#0EA5E9"),
    ("TD", "Thierno DIEDHIOU", "Ingénieur en Génie Logiciel", "thierno.diedhiou@univ-thies.sn",
     "Université Iba Der Thiam de Thiès", "#8B5CF6,#EC4899"),
    ("FK", "François KALY", "Professeur encadreur", "francois.kaly@univ-thies.sn",
     "Université Iba Der Thiam de Thiès", "#10B981,#0EA5E9"),
    ("MD", "Moussa DIAKHATE", "Professeur encadreur", "moussa.diakhate@uam.edu.sn",
     "Université Amadou Mahtar Mbow", "#F59E0B,#F43F5E"),
)


def run(BG, CARD, TEXT, MUTED, BORDER, **kw):
    st.markdown("""
    <div class="pg-hdr"><div>
      <h1 class="pg-ttl">À propos de ClimatSen</h1>
      <p class="pg-sub">Précipitations extrêmes au Sénégal et téléconnexions océaniques</p>
    </div></div>
    """, unsafe_allow_html=True)

    st.markdown(
        f'<div style="background:{CARD};border:1px solid {BORDER};border-radius:14px;'
        f'padding:18px 22px;color:{TEXT};font-size:0.86rem;line-height:1.65;">'
        '<p style="margin:0 0 8px 0;"><b>ClimatSen</b> est la plateforme issue d&#39;un mémoire '
        'de master sur les événements de précipitation extrême au Sénégal et leurs liens avec '
        'les températures de surface de la mer (téléconnexions).</p>'
        '<p style="margin:0 0 8px 0;"><b>Données.</b> Pluie : CHIRPS v2.0 journalier 0,25°, '
        '1981-2023. Température de surface de la mer : NOAA OISST v2 journalier 0,25°, '
        '1983-2023. Prévision saisonnière : Copernicus C3S (ECMWF SEAS5).</p>'
        '<p style="margin:0;"><b>Limites.</b> Les résultats sont statistiques et descriptifs. '
        'La veille pré-saison n&#39;a pas de compétence démontrée en prévision réelle et ne '
        'remplace pas les bulletins officiels de l&#39;ANACIM.</p></div>',
        unsafe_allow_html=True)

    st.markdown('<p class="pnl-ttl" style="margin:22px 0 10px 0;">Équipe</p>',
                unsafe_allow_html=True)
    cols = st.columns(2, gap="small")
    for i, (ini, nom, role, mail, univ, grad) in enumerate(EQUIPE):
        cols[i % 2].markdown(
            f'<div style="background:{CARD};border:1px solid {BORDER};border-radius:14px;'
            f'padding:16px 18px;display:flex;gap:12px;align-items:center;margin-bottom:10px;">'
            f'<div style="width:42px;height:42px;border-radius:50%;flex-shrink:0;'
            f'background:linear-gradient(135deg,{grad});display:flex;align-items:center;'
            f'justify-content:center;font-size:0.85rem;font-weight:800;color:#FFFFFF;">{ini}</div>'
            f'<div style="min-width:0;">'
            f'<p style="margin:0;font-size:0.88rem;font-weight:700;color:{TEXT};">{html.escape(nom)}</p>'
            f'<p style="margin:2px 0 0 0;font-size:0.76rem;font-weight:600;color:{TEXT};">{html.escape(role)}</p>'
            f'<p style="margin:2px 0 0 0;font-size:0.74rem;color:{MUTED};">{html.escape(univ)}</p>'
            f'<p style="margin:2px 0 0 0;font-size:0.74rem;">'
            f'<a href="mailto:{mail}" style="color:{MUTED};">{html.escape(mail)}</a></p>'
            f'</div></div>', unsafe_allow_html=True)
