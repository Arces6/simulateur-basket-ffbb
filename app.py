# app.py - Application principale Streamlit
# Installation requise : pip install streamlit reportlab plotly pandas

import streamlit as st
import json
import os
import time
import random
from collections import defaultdict
from datetime import datetime
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.colors import HexColor, white
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                 Table, TableStyle, PageBreak)
from reportlab.lib.enums import TA_CENTER, TA_LEFT
import io

# =============================================================================
# CONFIGURATION DE LA PAGE
# =============================================================================

st.set_page_config(
    page_title="Simulateur Basket FFBB",
    page_icon="🏀",
    layout="wide",
    initial_sidebar_state="expanded",
)

# =============================================================================
# CONSTANTES
# =============================================================================

FICHIER_DONNEES   = "championnats.json"
SEUIL_EXHAUSTIF   = 20
NB_SIMULATIONS_MC = 500_000

# =============================================================================
# GESTION DES DONNÉES
# =============================================================================

def charger_donnees():
    if os.path.exists(FICHIER_DONNEES):
        with open(FICHIER_DONNEES, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"championnats": {}}


def sauvegarder_donnees(donnees):
    with open(FICHIER_DONNEES, "w", encoding="utf-8") as f:
        json.dump(donnees, f, ensure_ascii=False, indent=2)


def nouveau_championnat(nom, nb_equipes, nb_journees,
                         nb_relegations, nb_montees,
                         equipes, calendrier):
    return {
        "nom":            nom,
        "nb_equipes":     nb_equipes,
        "nb_journees":    nb_journees,
        "nb_relegations": nb_relegations,
        "nb_montees":     nb_montees,
        "equipes":        equipes,
        "calendrier":     calendrier,
        "resultats":      {},
        "cree_le":        datetime.now().strftime("%d/%m/%Y %H:%M"),
        "modifie_le":     datetime.now().strftime("%d/%m/%Y %H:%M"),
    }

# =============================================================================
# CALCUL DU CLASSEMENT
# =============================================================================

def calculer_stats_equipe(eq, champ):
    resultats = champ["resultats"]
    pts = v = d = pts_marques = pts_encaisses = matchs_joues = 0

    for j_key, matchs_j in resultats.items():
        for match in matchs_j:
            if match.get("reporte"):
                continue
            dom = match["domicile"]
            ext = match["exterieur"]
            if match.get("penalite"):
                if dom == eq or ext == eq:
                    matchs_joues += 1
                    if match["vainqueur"] == eq:
                        pts += 2; v += 1
                    else:
                        pts += 0; d += 1
            else:
                if dom == eq:
                    matchs_joues  += 1
                    pts_marques   += match["score_dom"]
                    pts_encaisses += match["score_ext"]
                    if match["score_dom"] > match["score_ext"]:
                        pts += 2; v += 1
                    else:
                        pts += 1; d += 1
                elif ext == eq:
                    matchs_joues  += 1
                    pts_marques   += match["score_ext"]
                    pts_encaisses += match["score_dom"]
                    if match["score_ext"] > match["score_dom"]:
                        pts += 2; v += 1
                    else:
                        pts += 1; d += 1

    return {
        "equipe":        eq,
        "pts":           pts,
        "j":             matchs_joues,
        "v":             v,
        "d":             d,
        "pts_marques":   pts_marques,
        "pts_encaisses": pts_encaisses,
        "diff":          pts_marques - pts_encaisses,
    }


def construire_matrice_cd(champ):
    equipes    = champ["equipes"]
    resultats  = champ["resultats"]
    pts_cd     = {a: {b: 0 for b in equipes} for a in equipes}
    diff_cd    = {a: {b: 0 for b in equipes} for a in equipes}
    marques_cd = {a: {b: 0 for b in equipes} for a in equipes}

    for j_key, matchs_j in resultats.items():
        for match in matchs_j:
            if match.get("reporte"):
                continue
            dom = match["domicile"]
            ext = match["exterieur"]
            if match.get("penalite"):
                v = match["vainqueur"]
                p = ext if v == dom else dom
                pts_cd[v][p] += 2
                pts_cd[p][v] += 0
            else:
                s_dom = match["score_dom"]
                s_ext = match["score_ext"]
                if s_dom > s_ext:
                    pts_cd[dom][ext] += 2
                    pts_cd[ext][dom] += 1
                else:
                    pts_cd[dom][ext] += 1
                    pts_cd[ext][dom] += 2
                diff_cd[dom][ext]    += (s_dom - s_ext)
                diff_cd[ext][dom]    += (s_ext - s_dom)
                marques_cd[dom][ext] += s_dom
                marques_cd[ext][dom] += s_ext

    return pts_cd, diff_cd, marques_cd


def departager(groupe, pts_cd, diff_cd, marques_cd, stats_dict):
    if len(groupe) == 1:
        return groupe

    pts_mini     = {eq: sum(pts_cd[eq][adv]
                            for adv in groupe if adv != eq)
                    for eq in groupe}
    diff_mini    = {eq: sum(diff_cd[eq][adv]
                            for adv in groupe if adv != eq)
                    for eq in groupe}
    marques_mini = {eq: sum(marques_cd[eq][adv]
                            for adv in groupe if adv != eq)
                    for eq in groupe}

    groupe_trie = sorted(
        groupe,
        key=lambda e: (
            pts_mini[e],
            diff_mini[e],
            marques_mini[e],
            stats_dict[e]["diff"],
            stats_dict[e]["pts_marques"],
        ),
        reverse=True,
    )

    resultat_final = []
    i = 0
    while i < len(groupe_trie):
        eq_ref      = groupe_trie[i]
        sous_groupe = [eq_ref]
        j = i + 1
        while j < len(groupe_trie):
            eq_j = groupe_trie[j]
            if (pts_mini[eq_j]         == pts_mini[eq_ref]         and
                diff_mini[eq_j]        == diff_mini[eq_ref]        and
                marques_mini[eq_j]     == marques_mini[eq_ref]     and
                stats_dict[eq_j]["diff"] == stats_dict[eq_ref]["diff"] and
                stats_dict[eq_j]["pts_marques"] ==
                    stats_dict[eq_ref]["pts_marques"]):
                sous_groupe.append(eq_j)
                j += 1
            else:
                break
        resultat_final.extend(sorted(sous_groupe))
        i = j

    return resultat_final


def calculer_classement_complet(champ):
    equipes  = champ["equipes"]
    stats    = {eq: calculer_stats_equipe(eq, champ) for eq in equipes}
    pts_cd, diff_cd, marques_cd = construire_matrice_cd(champ)

    eq_triees = sorted(equipes,
                       key=lambda e: stats[e]["pts"],
                       reverse=True)
    classement = []
    i = 0
    while i < len(eq_triees):
        pts_ref = stats[eq_triees[i]]["pts"]
        groupe  = []
        j = i
        while (j < len(eq_triees) and
               stats[eq_triees[j]]["pts"] == pts_ref):
            groupe.append(eq_triees[j])
            j += 1
        if len(groupe) == 1:
            classement.append(groupe[0])
        else:
            classement.extend(
                departager(groupe, pts_cd, diff_cd, marques_cd, stats)
            )
        i = j

    return [{"rang": r + 1, **stats[eq]}
            for r, eq in enumerate(classement)]

# =============================================================================
# SIMULATION
# =============================================================================

def get_matchs_restants(champ):
    resultats  = champ["resultats"]
    calendrier = champ["calendrier"]

    matchs_joues = set()
    for j_key, matchs_j in resultats.items():
        for match in matchs_j:
            if not match.get("reporte"):
                matchs_joues.add(
                    (int(j_key), match["domicile"], match["exterieur"])
                )

    matchs_restants = []
    for j_num, matchs_j in enumerate(calendrier, 1):
        for match in matchs_j:
            dom = match["domicile"]
            ext = match["exterieur"]
            if (j_num, dom, ext) not in matchs_joues:
                matchs_restants.append({
                    "journee":   j_num,
                    "domicile":  dom,
                    "exterieur": ext,
                })

    return matchs_restants


def simuler_un_scenario(bits, matchs_restants, stats_base,
                         pts_cd_base, diff_cd_base, marques_cd_base,
                         equipes, nb_relegations, nb_montees,
                         diff_moyen):
    score_moy_v = 70 + diff_moyen // 2
    score_moy_d = 70 - diff_moyen // 2

    pts      = {eq: stats_base[eq]["pts"]        for eq in equipes}
    diff_gen = {eq: stats_base[eq]["diff"]        for eq in equipes}
    marques  = {eq: stats_base[eq]["pts_marques"] for eq in equipes}

    pts_cd  = {a: dict(pts_cd_base[a])     for a in equipes}
    diff_cd = {a: dict(diff_cd_base[a])    for a in equipes}
    marq_cd = {a: dict(marques_cd_base[a]) for a in equipes}

    for i, match in enumerate(matchs_restants):
        dom = match["domicile"]
        ext = match["exterieur"]
        v   = dom if bits[i] == 0 else ext
        p   = ext if bits[i] == 0 else dom

        pts[v]      += 2
        pts[p]      += 1
        pts_cd[v][p]  += 2
        pts_cd[p][v]  += 1
        diff_cd[v][p]  += diff_moyen
        diff_cd[p][v]  -= diff_moyen
        marq_cd[v][p]  += score_moy_v
        marq_cd[p][v]  += score_moy_d
        diff_gen[v]    += diff_moyen
        diff_gen[p]    -= diff_moyen
        marques[v]     += score_moy_v
        marques[p]     += score_moy_d

    stats_fin = {
        eq: {"pts": pts[eq], "diff": diff_gen[eq],
             "pts_marques": marques[eq]}
        for eq in equipes
    }

    eq_triees = sorted(equipes, key=lambda e: pts[e], reverse=True)
    classement_final = []
    i = 0
    while i < len(eq_triees):
        pts_ref = pts[eq_triees[i]]
        groupe  = []
        j = i
        while j < len(eq_triees) and pts[eq_triees[j]] == pts_ref:
            groupe.append(eq_triees[j])
            j += 1
        if len(groupe) == 1:
            classement_final.append(groupe[0])
        else:
            pts_mini  = {e: sum(pts_cd[e][a]
                                for a in groupe if a != e)
                         for e in groupe}
            diff_mini = {e: sum(diff_cd[e][a]
                                for a in groupe if a != e)
                         for e in groupe}
            marq_mini = {e: sum(marq_cd[e][a]
                                for a in groupe if a != e)
                         for e in groupe}
            groupe_t  = sorted(
                groupe,
                key=lambda e: (
                    pts_mini[e], diff_mini[e], marq_mini[e],
                    stats_fin[e]["diff"],
                    stats_fin[e]["pts_marques"],
                ),
                reverse=True,
            )
            classement_final.extend(groupe_t)
        i = j

    nb_eq       = len(equipes)
    nb_maintien = nb_eq - nb_relegations
    maintenus   = set(classement_final[:nb_maintien])
    montes      = set(classement_final[:nb_montees]) if nb_montees > 0 else set()
    relegues    = set(classement_final[nb_maintien:])

    return maintenus, montes, relegues, classement_final


def lancer_simulation(champ, diff_moyen=10):
    equipes         = champ["equipes"]
    nb_relegations  = champ["nb_relegations"]
    nb_montees      = champ.get("nb_montees", 0)
    matchs_restants = get_matchs_restants(champ)
    nb_matchs       = len(matchs_restants)

    if nb_matchs == 0:
        return None, None, None, "Aucun match restant.", 0

    stats_base = {eq: calculer_stats_equipe(eq, champ)
                  for eq in equipes}
    pts_cd_base, diff_cd_base, marques_cd_base = \
        construire_matrice_cd(champ)

    compteur_maintien = {eq: 0 for eq in equipes}
    compteur_montee   = {eq: 0 for eq in equipes}
    compteur_rang     = {eq: defaultdict(int) for eq in equipes}

    # Stockage complet des scénarios pour analyse personnalisée
    tous_scenarios = []

    mode = ("exhaustive" if nb_matchs <= SEUIL_EXHAUSTIF
            else "monte_carlo")

    if mode == "exhaustive":
        nb_total = 2 ** nb_matchs
        for scenario in range(nb_total):
            bits = [(scenario >> i) & 1 for i in range(nb_matchs)]
            maintenus, montes, relegues, classement_final = \
                simuler_un_scenario(
                    bits, matchs_restants, stats_base,
                    pts_cd_base, diff_cd_base, marques_cd_base,
                    equipes, nb_relegations, nb_montees, diff_moyen,
                )
            for eq in maintenus:
                compteur_maintien[eq] += 1
            for eq in montes:
                compteur_montee[eq] += 1
            for rang, eq in enumerate(classement_final, 1):
                compteur_rang[eq][rang] += 1
            tous_scenarios.append({
                "bits":      bits,
                "maintenus": maintenus,
                "montes":    montes,
                "relegues":  relegues,
            })
    else:
        nb_total = NB_SIMULATIONS_MC
        for _ in range(nb_total):
            bits = [random.randint(0, 1) for _ in range(nb_matchs)]
            maintenus, montes, relegues, classement_final = \
                simuler_un_scenario(
                    bits, matchs_restants, stats_base,
                    pts_cd_base, diff_cd_base, marques_cd_base,
                    equipes, nb_relegations, nb_montees, diff_moyen,
                )
            for eq in maintenus:
                compteur_maintien[eq] += 1
            for eq in montes:
                compteur_montee[eq] += 1
            for rang, eq in enumerate(classement_final, 1):
                compteur_rang[eq][rang] += 1
            tous_scenarios.append({
                "bits":      bits,
                "maintenus": maintenus,
                "montes":    montes,
                "relegues":  relegues,
            })

    resultats_sim = sorted(
        [{
            "equipe":     eq,
            "maintien":   compteur_maintien[eq],
            "relegation": nb_total - compteur_maintien[eq],
            "pct":        round((compteur_maintien[eq]/nb_total)*100, 2),
            "montee":     compteur_montee[eq],
            "pct_montee": round((compteur_montee[eq]/nb_total)*100, 2),
         }
         for eq in equipes],
        key=lambda x: x["pct"],
        reverse=True,
    )

    return resultats_sim, compteur_rang, tous_scenarios, mode, nb_total

# =============================================================================
# ANALYSE SCÉNARIOS PERSONNALISÉS
# =============================================================================

def analyser_scenarios_personnalises(tous_scenarios, conditions,
                                      matchs_restants, nb_total):
    """
    Filtre les scénarios selon les conditions définies par l'utilisateur.
    conditions = {
        "equipe_A": "monte",
        "equipe_B": "maintien",
        "equipe_C": "relegue",
    }
    Retourne :
    - nb_scenarios_ok : nombre de scénarios correspondants
    - pct_ok : pourcentage
    - proba_match : pour chaque match, proba que dom gagne dans ces scénarios
    - matchs_obligatoires : matchs avec résultat identique dans 100% des scénarios
    """
    scenarios_ok = []

    for sc in tous_scenarios:
        valide = True
        for eq, statut in conditions.items():
            if statut == "monte":
                if eq not in sc["montes"]:
                    valide = False; break
            elif statut == "maintien":
                if eq not in sc["maintenus"]:
                    valide = False; break
            elif statut == "relegue":
                if eq not in sc["relegues"]:
                    valide = False; break
        if valide:
            scenarios_ok.append(sc)

    nb_ok = len(scenarios_ok)
    pct_ok = (nb_ok / nb_total * 100) if nb_total > 0 else 0

    if nb_ok == 0:
        return nb_ok, pct_ok, [], []

    # Probabilité par match
    proba_match = []
    for i, match in enumerate(matchs_restants):
        dom_gagne = sum(1 for sc in scenarios_ok if sc["bits"][i] == 0)
        ext_gagne = nb_ok - dom_gagne
        proba_match.append({
            "journee":      match["journee"],
            "domicile":     match["domicile"],
            "exterieur":    match["exterieur"],
            "pct_dom":      round(dom_gagne / nb_ok * 100, 1),
            "pct_ext":      round(ext_gagne / nb_ok * 100, 1),
        })

    # Matchs obligatoires (100% identiques)
    matchs_obligatoires = []
    for i, match in enumerate(matchs_restants):
        dom_gagne = sum(1 for sc in scenarios_ok if sc["bits"][i] == 0)
        if dom_gagne == nb_ok:
            matchs_obligatoires.append({
                "journee":   match["journee"],
                "domicile":  match["domicile"],
                "exterieur": match["exterieur"],
                "vainqueur": match["domicile"],
            })
        elif dom_gagne == 0:
            matchs_obligatoires.append({
                "journee":   match["journee"],
                "domicile":  match["domicile"],
                "exterieur": match["exterieur"],
                "vainqueur": match["exterieur"],
            })

    return nb_ok, pct_ok, proba_match, matchs_obligatoires

# =============================================================================
# STATUTS
# =============================================================================

def statut_maintien(pct):
    if pct == 100.0:   return "GARANTI"
    elif pct >= 90.0:  return "QUASI-CERTAIN"
    elif pct >= 70.0:  return "PROBABLE"
    elif pct >= 50.0:  return "INCERTAIN"
    elif pct > 0.0:    return "EN DANGER"
    else:              return "IMPOSSIBLE"


def statut_montee(pct):
    if pct == 100.0:   return "GARANTIE"
    elif pct >= 90.0:  return "QUASI-CERTAINE"
    elif pct >= 70.0:  return "PROBABLE"
    elif pct >= 50.0:  return "INCERTAINE"
    elif pct > 0.0:    return "PEU PROBABLE"
    else:              return "IMPOSSIBLE"

# =============================================================================
# GRAPHIQUES
# =============================================================================

def graphique_evolution_classement(champ):
    equipes   = champ["equipes"]
    resultats = champ["resultats"]
    nb_j      = champ["nb_journees"]

    historique = []
    champ_temp = {**champ, "resultats": {}}

    for j_num in range(1, nb_j + 1):
        j_key = str(j_num)
        if j_key in resultats:
            champ_temp["resultats"][j_key] = resultats[j_key]
            classement = calculer_classement_complet(champ_temp)
            for item in classement:
                historique.append({
                    "journee": j_num,
                    "equipe":  item["equipe"],
                    "rang":    item["rang"],
                    "pts":     item["pts"],
                })

    if not historique:
        return None

    df       = pd.DataFrame(historique)
    fig      = go.Figure()
    couleurs = px.colors.qualitative.Set3

    for idx, eq in enumerate(equipes):
        df_eq = df[df["equipe"] == eq]
        if df_eq.empty:
            continue
        fig.add_trace(go.Scatter(
            x=df_eq["journee"],
            y=df_eq["rang"],
            mode="lines+markers",
            name=eq,
            line=dict(color=couleurs[idx % len(couleurs)], width=2),
            marker=dict(size=6),
            hovertemplate=(
                f"<b>{eq}</b><br>"
                "Journée %{x}<br>"
                "Rang : %{y}e<br>"
                "<extra></extra>"
            ),
        ))

    nb_maintien = len(equipes) - champ["nb_relegations"]
    nb_montees  = champ.get("nb_montees", 0)

    fig.add_hline(
        y=nb_maintien + 0.5,
        line_dash="dash", line_color="red", line_width=2,
        annotation_text="Zone relégation",
        annotation_position="right",
    )
    if nb_montees > 0:
        fig.add_hline(
            y=nb_montees + 0.5,
            line_dash="dash", line_color="green", line_width=2,
            annotation_text="Zone montée",
            annotation_position="right",
        )

    fig.update_layout(
        title="Évolution du classement au fil des journées",
        xaxis_title="Journée",
        yaxis_title="Rang",
        yaxis=dict(autorange="reversed", tickmode="linear",
                   tick0=1, dtick=1),
        xaxis=dict(tickmode="linear", tick0=1, dtick=1),
        legend=dict(orientation="v", x=1.02, y=1),
        height=600,
        hovermode="x unified",
    )
    return fig


def graphique_probabilites(resultats_sim, champ):
    df       = pd.DataFrame(resultats_sim)
    couleurs = []
    for pct in df["pct"]:
        if pct == 100.0:   couleurs.append("#1e7e34")
        elif pct >= 90.0:  couleurs.append("#28a745")
        elif pct >= 70.0:  couleurs.append("#ffc107")
        elif pct >= 50.0:  couleurs.append("#fd7e14")
        elif pct > 0.0:    couleurs.append("#dc3545")
        else:              couleurs.append("#6c757d")

    fig = go.Figure(go.Bar(
        x=df["pct"],
        y=df["equipe"],
        orientation="h",
        marker_color=couleurs,
        text=[f"{p:.1f}%" for p in df["pct"]],
        textposition="outside",
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Probabilité de maintien : %{x:.2f}%<br>"
            "<extra></extra>"
        ),
    ))
    fig.add_vline(x=50, line_dash="dash",
                  line_color="gray", line_width=1)
    fig.update_layout(
        title="Probabilités de Maintien",
        xaxis_title="% de chances de maintien",
        xaxis=dict(range=[0, 115]),
        yaxis=dict(autorange="reversed"),
        height=500,
        showlegend=False,
    )
    return fig


def graphique_probabilites_montee(resultats_sim):
    df        = pd.DataFrame(resultats_sim)
    df_montee = df[df["pct_montee"] > 0].copy()
    if df_montee.empty:
        return None

    df_montee = df_montee.sort_values("pct_montee", ascending=True)
    couleurs  = []
    for pct in df_montee["pct_montee"]:
        if pct == 100.0:   couleurs.append("#1a5276")
        elif pct >= 90.0:  couleurs.append("#2980b9")
        elif pct >= 70.0:  couleurs.append("#5dade2")
        elif pct >= 50.0:  couleurs.append("#85c1e9")
        else:              couleurs.append("#aed6f1")

    fig = go.Figure(go.Bar(
        x=df_montee["pct_montee"],
        y=df_montee["equipe"],
        orientation="h",
        marker_color=couleurs,
        text=[f"{p:.1f}%" for p in df_montee["pct_montee"]],
        textposition="outside",
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Probabilité de montée : %{x:.2f}%<br>"
            "<extra></extra>"
        ),
    ))
    fig.add_vline(x=50, line_dash="dash",
                  line_color="gray", line_width=1)
    fig.update_layout(
        title="Probabilités de Montée",
        xaxis_title="% de chances de montée",
        xaxis=dict(range=[0, 115]),
        height=400,
        showlegend=False,
    )
    return fig

# =============================================================================
# GÉNÉRATION PDF
# =============================================================================

def generer_pdf_streamlit(champ, classement, resultats_sim,
                           compteur_rang, mode_sim, nb_total):
    BLEU_TITRE   = HexColor("#1a3a6b")
    BLEU_CLAIR   = HexColor("#dce6f1")
    VERT         = HexColor("#1e7e34")
    VERT_CLAIR   = HexColor("#d4edda")
    ORANGE_CLAIR = HexColor("#fdebd0")
    ROUGE        = HexColor("#c0392b")
    ROUGE_CLAIR  = HexColor("#fadbd8")
    GRIS_CLAIR   = HexColor("#f2f2f2")
    GRIS_MOYEN   = HexColor("#bdc3c7")
    JAUNE_CLAIR  = HexColor("#fef9e7")
    BLEU_MONTEE  = HexColor("#d6eaf8")

    def couleur_pct(pct):
        if pct == 100.0:   return VERT_CLAIR
        elif pct >= 90.0:  return HexColor("#d0f0c0")
        elif pct >= 70.0:  return JAUNE_CLAIR
        elif pct >= 50.0:  return ORANGE_CLAIR
        elif pct > 0.0:    return ROUGE_CLAIR
        else:              return HexColor("#f0f0f0")

    styles = getSampleStyleSheet()
    larg_p = A4[0] - 3.6 * cm

    st_titre = ParagraphStyle(
        'Titre', parent=styles['Title'],
        fontSize=18, textColor=white,
        alignment=TA_CENTER, fontName='Helvetica-Bold',
    )
    st_sous = ParagraphStyle(
        'SousTitre', parent=styles['Normal'],
        fontSize=10, textColor=white, alignment=TA_CENTER,
    )
    st_section = ParagraphStyle(
        'Section', parent=styles['Heading1'],
        fontSize=12, textColor=white,
        fontName='Helvetica-Bold', alignment=TA_LEFT,
    )
    st_sous_section = ParagraphStyle(
        'SousSection', parent=styles['Heading2'],
        fontSize=10, textColor=BLEU_TITRE,
        fontName='Helvetica-Bold', spaceAfter=4,
    )
    st_corps = ParagraphStyle(
        'Corps', parent=styles['Normal'],
        fontSize=9, spaceAfter=4, leading=14,
    )
    st_note = ParagraphStyle(
        'Note', parent=styles['Normal'],
        fontSize=8, textColor=HexColor("#7f8c8d"),
        spaceAfter=4, leading=12,
    )

    buffer = io.BytesIO()
    doc    = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=1.8*cm, leftMargin=1.8*cm,
        topMargin=1.5*cm,   bottomMargin=1.5*cm,
    )
    elements = []

    nb_equipes     = len(champ["equipes"])
    nb_relegations = champ["nb_relegations"]
    nb_montees     = champ.get("nb_montees", 0)
    nb_maintien    = nb_equipes - nb_relegations

    def bloc_bleu(texte, style):
        t = Table([[Paragraph(texte, style)]], colWidths=[larg_p])
        t.setStyle(TableStyle([
            ('BACKGROUND',    (0,0), (-1,-1), BLEU_TITRE),
            ('TOPPADDING',    (0,0), (-1,-1), 10),
            ('BOTTOMPADDING', (0,0), (-1,-1), 10),
        ]))
        return t

    def titre_section(texte):
        t = Table([[Paragraph(texte, st_section)]], colWidths=[larg_p])
        t.setStyle(TableStyle([
            ('BACKGROUND',    (0,0), (-1,-1), BLEU_TITRE),
            ('TOPPADDING',    (0,0), (-1,-1), 7),
            ('BOTTOMPADDING', (0,0), (-1,-1), 7),
            ('LEFTPADDING',   (0,0), (-1,-1), 10),
        ]))
        return t

    def style_base():
        return [
            ('BACKGROUND',    (0,0), (-1,0),  BLEU_TITRE),
            ('TEXTCOLOR',     (0,0), (-1,0),  white),
            ('FONTNAME',      (0,0), (-1,0),  'Helvetica-Bold'),
            ('FONTSIZE',      (0,0), (-1,-1), 8),
            ('ALIGN',         (0,0), (-1,-1), 'CENTER'),
            ('GRID',          (0,0), (-1,-1), 0.3, GRIS_MOYEN),
            ('TOPPADDING',    (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('LEFTPADDING',   (0,0), (-1,-1), 4),
            ('ROWBACKGROUND', (0,1), (-1,-1), [white, GRIS_CLAIR]),
        ]

    # Page de garde
    elements.append(bloc_bleu("RAPPORT D'ANALYSE", st_titre))
    elements.append(bloc_bleu(champ["nom"], st_sous))
    elements.append(bloc_bleu(
        f"Genere le {datetime.now().strftime('%d/%m/%Y a %H:%M')}",
        st_sous))
    elements.append(Spacer(1, 0.5*cm))

    infos = [
        ["Championnat",     champ["nom"]],
        ["Equipes",         str(nb_equipes)],
        ["Journees",        str(champ["nb_journees"])],
        ["Relegations",     str(nb_relegations)],
        ["Montees",         str(nb_montees)],
        ["Mode simulation", "Exhaustive"
                            if mode_sim == "exhaustive"
                            else f"Monte Carlo ({nb_total:,})"],
        ["Scenarios",       f"{nb_total:,}"],
    ]
    t_infos = Table(
        [[Paragraph(k, ParagraphStyle('b', parent=st_corps,
                                      fontName='Helvetica-Bold')),
          Paragraph(v, st_corps)]
         for k, v in infos],
        colWidths=[5*cm, larg_p - 5*cm],
    )
    t_infos.setStyle(TableStyle([
        ('BACKGROUND',    (0,0), (0,-1), BLEU_CLAIR),
        ('BACKGROUND',    (1,0), (1,-1), GRIS_CLAIR),
        ('GRID',          (0,0), (-1,-1), 0.5, GRIS_MOYEN),
        ('ROWBACKGROUND', (0,0), (-1,-1), [GRIS_CLAIR, white]),
        ('TOPPADDING',    (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING',   (0,0), (-1,-1), 8),
    ]))
    elements.append(t_infos)

    # Section 1 : Classement actuel
    elements.append(PageBreak())
    elements.append(titre_section("1. Classement Actuel"))
    elements.append(Spacer(1, 0.3*cm))

    rows_cl = [["Rang", "Equipe", "Pts", "J", "V", "D",
                 "Marques", "Encaisses", "Diff", "Zone"]]
    for item in classement:
        rang = item["rang"]
        if rang <= nb_montees:
            zone = "Montee"
        elif rang <= nb_maintien:
            zone = "Maintenu"
        else:
            zone = "Relegue"
        rows_cl.append([
            str(rang), item["equipe"],
            str(item["pts"]), str(item["j"]),
            str(item["v"]),   str(item["d"]),
            str(item["pts_marques"]),
            str(item["pts_encaisses"]),
            f"{item['diff']:+d}", zone,
        ])

    t_cl = Table(rows_cl,
                 colWidths=[0.9*cm, 4.5*cm, 0.9*cm, 0.7*cm,
                            0.7*cm, 0.7*cm, 1.3*cm, 1.4*cm,
                            1*cm,   2.2*cm])
    st_cl = style_base()
    st_cl += [
        ('ALIGN',     (1,0), (1,-1), 'LEFT'),
        ('ALIGN',     (9,0), (9,-1), 'LEFT'),
        ('LINEBELOW', (0, nb_maintien), (-1, nb_maintien), 2, ROUGE),
    ]
    if nb_montees > 0:
        st_cl.append(
            ('LINEBELOW', (0, nb_montees), (-1, nb_montees), 2, VERT)
        )
    for i, item in enumerate(classement, 1):
        if item["rang"] <= nb_montees:
            st_cl.append(('BACKGROUND', (0,i), (-1,i), BLEU_MONTEE))
        elif item["rang"] <= nb_maintien:
            st_cl.append(('BACKGROUND', (9,i), (9,i), VERT_CLAIR))
        else:
            st_cl.append(('BACKGROUND', (9,i), (9,i), ROUGE_CLAIR))
            st_cl.append(('BACKGROUND', (0,i), (-1,i), ROUGE_CLAIR))
    t_cl.setStyle(TableStyle(st_cl))
    elements.append(t_cl)

    # Section 2 : Probabilités
    if resultats_sim:
        elements.append(PageBreak())
        elements.append(titre_section("2. Probabilites de Maintien"))
        elements.append(Spacer(1, 0.3*cm))

        mode_txt = (
            f"Simulation exhaustive ({nb_total:,} scenarios)"
            if mode_sim == "exhaustive"
            else f"Monte Carlo ({nb_total:,} simulations)"
        )
        elements.append(Paragraph(f"Mode : {mode_txt}", st_note))
        elements.append(Spacer(1, 0.2*cm))

        entetes = ["Rang", "Equipe", "% Maintien", "Statut Maintien"]
        if nb_montees > 0:
            entetes += ["% Montee", "Statut Montee"]
        rows_sim = [entetes]

        for rang, item in enumerate(resultats_sim, 1):
            row = [
                str(rang),
                item["equipe"],
                f"{item['pct']:.2f}%",
                statut_maintien(item["pct"]),
            ]
            if nb_montees > 0:
                row += [
                    f"{item['pct_montee']:.2f}%",
                    statut_montee(item["pct_montee"]),
                ]
            rows_sim.append(row)

        col_ws = ([0.9*cm, 5*cm, 2*cm, 3*cm, 2*cm, 2.9*cm]
                  if nb_montees > 0
                  else [0.9*cm, 6*cm, 2.5*cm, 4*cm])

        t_sim = Table(rows_sim, colWidths=col_ws)
        st_sim = style_base()
        st_sim += [
            ('ALIGN',    (1,0), (1,-1), 'LEFT'),
            ('FONTNAME', (2,1), (2,-1), 'Helvetica-Bold'),
        ]
        for i, item in enumerate(resultats_sim, 1):
            st_sim.append(
                ('BACKGROUND', (0,i), (-1,i), couleur_pct(item["pct"]))
            )
        t_sim.setStyle(TableStyle(st_sim))
        elements.append(t_sim)
        elements.append(Spacer(1, 0.3*cm))

        # Section 3 : Distribution
        if compteur_rang:
            elements.append(PageBreak())
            elements.append(
                titre_section("3. Distribution des Classements Finaux"))
            elements.append(Spacer(1, 0.3*cm))
            elements.append(Paragraph(
                "Probabilite (%) d'arriver a chaque place finale. "
                "Les places avec 0% sont exclues.",
                st_note,
            ))
            elements.append(Spacer(1, 0.3*cm))

            for item in resultats_sim:
                eq   = item["equipe"]
                dist = compteur_rang.get(eq, {})
                rangs_ok = sorted(
                    [r for r in range(1, nb_equipes + 1)
                     if dist.get(r, 0) > 0]
                )
                if not rangs_ok:
                    continue

                elements.append(Paragraph(eq, st_sous_section))
                rows_dist = [
                    ["Place"]    + [f"{r}e"   for r in rangs_ok],
                    ["Nb scen"]  + [f"{dist[r]:,}" for r in rangs_ok],
                    ["%"]        + [
                        f"{dist[r]/nb_total*100:.1f}%"
                        for r in rangs_ok
                    ],
                ]
                nb_cols = len(rangs_ok) + 1
                col_w   = larg_p / nb_cols
                t_dist  = Table(rows_dist,
                                colWidths=[col_w] * nb_cols)
                st_dist = [
                    ('BACKGROUND',   (0,0), (-1,0),  BLEU_TITRE),
                    ('TEXTCOLOR',    (0,0), (-1,0),  white),
                    ('FONTNAME',     (0,0), (-1,0),  'Helvetica-Bold'),
                    ('BACKGROUND',   (0,1), (0,-1),  BLEU_CLAIR),
                    ('FONTNAME',     (0,1), (0,-1),  'Helvetica-Bold'),
                    ('FONTSIZE',     (0,0), (-1,-1), 7),
                    ('ALIGN',        (0,0), (-1,-1), 'CENTER'),
                    ('GRID',         (0,0), (-1,-1), 0.3, GRIS_MOYEN),
                    ('TOPPADDING',   (0,0), (-1,-1), 3),
                    ('BOTTOMPADDING',(0,0), (-1,-1), 3),
                    ('ROWBACKGROUND',(0,1), (-1,-1), [white, GRIS_CLAIR]),
                ]
                for j_col, r in enumerate(rangs_ok, 1):
                    if r <= nb_montees:
                        st_dist.append(
                            ('BACKGROUND', (j_col,0), (j_col,0),
                             HexColor("#aed6f1")))
                    elif r <= nb_maintien:
                        st_dist.append(
                            ('BACKGROUND', (j_col,0), (j_col,0),
                             HexColor("#a9dfbf")))
                    else:
                        st_dist.append(
                            ('BACKGROUND', (j_col,0), (j_col,0),
                             HexColor("#f5b7b1")))
                t_dist.setStyle(TableStyle(st_dist))
                elements.append(t_dist)
                elements.append(Spacer(1, 0.2*cm))

    # Pied de page
    elements.append(Spacer(1, 0.5*cm))
    pied = Table(
        [[Paragraph(
            f"Rapport genere le "
            f"{datetime.now().strftime('%d/%m/%Y a %H:%M')} | "
            f"{champ['nom']} | Simulateur Basket FFBB",
            ParagraphStyle('pied', parent=st_note,
                           alignment=TA_CENTER, textColor=white),
        )]],
        colWidths=[larg_p],
    )
    pied.setStyle(TableStyle([
        ('BACKGROUND',    (0,0), (-1,-1), BLEU_TITRE),
        ('TOPPADDING',    (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
    ]))
    elements.append(pied)

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()

# =============================================================================
# SAUVEGARDE / RESTAURATION
# =============================================================================

def page_sauvegarde(donnees):
    st.title("💾 Sauvegarde & Restauration")

    st.subheader("📤 Exporter les données")
    st.write(
        "Téléchargez une copie de toutes vos données "
        "(championnats, équipes, résultats)."
    )
    json_bytes = json.dumps(
        donnees, ensure_ascii=False, indent=2
    ).encode("utf-8")
    nom_export = (
        f"sauvegarde_basket_"
        f"{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    )
    st.download_button(
        label="⬇️ Télécharger la sauvegarde (.json)",
        data=json_bytes,
        file_name=nom_export,
        mime="application/json",
        type="primary",
    )

    st.divider()

    st.subheader("📥 Importer des données")
    st.warning(
        "⚠️ L'importation remplacera toutes les données actuelles. "
        "Faites une sauvegarde avant d'importer."
    )
    fichier = st.file_uploader(
        "Sélectionner un fichier de sauvegarde (.json)",
        type=["json"],
    )

    if fichier is not None:
        try:
            donnees_import = json.load(fichier)
            if "championnats" not in donnees_import:
                st.error("Fichier invalide : format non reconnu.")
            else:
                nb_champ = len(donnees_import["championnats"])
                st.success(
                    f"✅ Fichier valide : {nb_champ} championnat(s) trouvé(s)."
                )
                st.write("**Championnats dans ce fichier :**")
                for nom_c in donnees_import["championnats"]:
                    st.write(f"  • {nom_c}")

                if st.button("🔄 Confirmer l'importation",
                              type="primary"):
                    sauvegarder_donnees(donnees_import)
                    st.session_state["champ_actif"] = None
                    st.session_state.pop("resultats_sim", None)
                    st.session_state.pop("compteur_rang", None)
                    st.session_state.pop("tous_scenarios", None)
                    st.success(
                        "✅ Données importées avec succès ! "
                        "Rechargez la page."
                    )
                    st.rerun()
        except Exception as e:
            st.error(f"Erreur lors de la lecture du fichier : {e}")

# =============================================================================
# INTERFACE STREAMLIT
# =============================================================================

def page_gestion_championnats(donnees):
    st.title("🏀 Gestion des Championnats")
    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("➕ Créer un nouveau championnat")
        with st.form("form_nouveau_champ"):
            nom = st.text_input(
                "Nom du championnat",
                placeholder="Ex: NM3 Poule H 2025-2026",
            )
            col_a, col_b = st.columns(2)
            with col_a:
                nb_equipes  = st.number_input(
                    "Nb équipes", min_value=4, max_value=20, value=14)
                nb_journees = st.number_input(
                    "Nb journées", min_value=2, max_value=50, value=26)
            with col_b:
                nb_rel     = st.number_input(
                    "Nb relégations", min_value=0, max_value=10, value=4)
                nb_montees = st.number_input(
                    "Nb montées", min_value=0, max_value=10, value=0,
                    help="Nombre d'équipes accédant au niveau supérieur")

            submitted = st.form_submit_button(
                "Créer le championnat", type="primary")
            if submitted:
                if not nom:
                    st.error("Veuillez saisir un nom.")
                elif nom in donnees["championnats"]:
                    st.error("Un championnat avec ce nom existe déjà.")
                else:
                    donnees["championnats"][nom] = nouveau_championnat(
                        nom, nb_equipes, nb_journees,
                        nb_rel, nb_montees, [], [],
                    )
                    sauvegarder_donnees(donnees)
                    st.success(f"✅ Championnat '{nom}' créé !")
                    st.rerun()

    with col2:
        st.subheader("📋 Championnats existants")
        if not donnees["championnats"]:
            st.info("Aucun championnat créé pour l'instant.")
        else:
            for nom_c, champ in donnees["championnats"].items():
                with st.expander(f"🏆 {nom_c}"):
                    col_x, col_y = st.columns(2)
                    with col_x:
                        st.write(f"**Équipes :** {champ['nb_equipes']}")
                        st.write(f"**Journées :** {champ['nb_journees']}")
                        st.write(f"**Relégations :** "
                                 f"{champ['nb_relegations']}")
                        st.write(f"**Montées :** "
                                 f"{champ.get('nb_montees', 0)}")
                        nb_eq = len(champ.get("equipes", []))
                        nb_j  = len(champ.get("resultats", {}))
                        st.write(f"**Équipes saisies :** {nb_eq}")
                        st.write(f"**Journées jouées :** {nb_j}")
                        st.write(f"**Créé le :** {champ['cree_le']}")
                    with col_y:
                        if st.button("🔧 Ouvrir",
                                     key=f"open_{nom_c}"):
                            st.session_state["champ_actif"] = nom_c
                            st.session_state["page"] = "classement"
                            st.rerun()
                        if st.button("✏️ Modifier",
                                     key=f"edit_{nom_c}"):
                            st.session_state["champ_a_modifier"] = nom_c
                            st.session_state["page"] = \
                                "modifier_championnat"
                            st.rerun()
                        if st.button("🗑️ Supprimer",
                                     key=f"del_{nom_c}"):
                            del donnees["championnats"][nom_c]
                            sauvegarder_donnees(donnees)
                            st.rerun()


def page_modifier_championnat(donnees):
    nom_champ = st.session_state.get("champ_a_modifier")
    if not nom_champ or nom_champ not in donnees["championnats"]:
        st.error("Championnat introuvable.")
        st.session_state["page"] = "championnats"
        st.rerun()
        return

    champ = donnees["championnats"][nom_champ]
    st.title(f"✏️ Modifier — {nom_champ}")
    st.info(
        "⚠️ Les équipes, le calendrier et les résultats déjà "
        "saisis sont conservés."
    )

    with st.form("form_modifier_champ"):
        nouveau_nom = st.text_input("Nom du championnat", value=nom_champ)
        col_a, col_b = st.columns(2)
        with col_a:
            nb_equipes  = st.number_input(
                "Nb équipes", min_value=4, max_value=20,
                value=champ["nb_equipes"])
            nb_journees = st.number_input(
                "Nb journées", min_value=2, max_value=50,
                value=champ["nb_journees"])
        with col_b:
            nb_rel     = st.number_input(
                "Nb relégations", min_value=0, max_value=10,
                value=champ["nb_relegations"])
            nb_montees = st.number_input(
                "Nb montées", min_value=0, max_value=10,
                value=champ.get("nb_montees", 0))

        submitted = st.form_submit_button(
            "💾 Sauvegarder les modifications", type="primary")
        if submitted:
            if not nouveau_nom:
                st.error("Le nom ne peut pas être vide.")
            elif (nouveau_nom != nom_champ and
                  nouveau_nom in donnees["championnats"]):
                st.error("Un championnat avec ce nom existe déjà.")
            else:
                champ["nb_equipes"]     = nb_equipes
                champ["nb_journees"]    = nb_journees
                champ["nb_relegations"] = nb_rel
                champ["nb_montees"]     = nb_montees
                champ["modifie_le"]     = datetime.now().strftime(
                    "%d/%m/%Y %H:%M")
                if nouveau_nom != nom_champ:
                    champ["nom"] = nouveau_nom
                    donnees["championnats"][nouveau_nom] = champ
                    del donnees["championnats"][nom_champ]
                    st.session_state["champ_actif"]      = nouveau_nom
                    st.session_state["champ_a_modifier"] = nouveau_nom
                sauvegarder_donnees(donnees)
                st.success("✅ Championnat modifié avec succès !")
                st.session_state["page"] = "championnats"
                st.rerun()

    if st.button("← Retour sans sauvegarder"):
        st.session_state["page"] = "championnats"
        st.rerun()


def page_equipes(donnees, nom_champ):
    champ = donnees["championnats"][nom_champ]
    st.title(f"👥 Équipes — {nom_champ}")
    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("Saisie des équipes")
        st.info(f"Équipes attendues : {champ['nb_equipes']}")
        equipes_text = st.text_area(
            "Saisir les équipes (une par ligne)",
            value="\n".join(champ.get("equipes", [])),
            height=300,
            placeholder="TEAM A\nTEAM B\n...",
        )
        if st.button("💾 Sauvegarder les équipes", type="primary"):
            equipes = [e.strip() for e in equipes_text.split("\n")
                       if e.strip()]
            if len(equipes) != champ["nb_equipes"]:
                st.error(f"Vous avez saisi {len(equipes)} équipes "
                         f"mais {champ['nb_equipes']} sont attendues.")
            elif len(set(equipes)) != len(equipes):
                st.error("Des équipes sont en double.")
            else:
                champ["equipes"]    = equipes
                champ["modifie_le"] = datetime.now().strftime(
                    "%d/%m/%Y %H:%M")
                sauvegarder_donnees(donnees)
                st.success("✅ Équipes sauvegardées !")
                st.rerun()

    with col2:
        st.subheader("Équipes enregistrées")
        if champ.get("equipes"):
            for i, eq in enumerate(champ["equipes"], 1):
                st.write(f"{i}. {eq}")
        else:
            st.info("Aucune équipe saisie.")


def page_calendrier(donnees, nom_champ):
    champ = donnees["championnats"][nom_champ]
    st.title(f"📅 Calendrier — {nom_champ}")

    if not champ.get("equipes"):
        st.warning("⚠️ Veuillez d'abord saisir les équipes.")
        return

    equipes    = champ["equipes"]
    nb_j       = champ["nb_journees"]
    nb_matchs  = len(equipes) // 2
    calendrier = champ.get("calendrier", [])

    st.info(f"Saisir {nb_j} journées de {nb_matchs} matchs chacune.")
    j_select = st.selectbox(
        "Sélectionner la journée à saisir/modifier",
        range(1, nb_j + 1),
        format_func=lambda x: f"Journée {x}",
    )
    j_idx            = j_select - 1
    matchs_existants = (calendrier[j_idx]
                        if j_idx < len(calendrier) else [])

    st.subheader(f"Journée {j_select}")
    with st.form(f"form_cal_j{j_select}"):
        matchs_j = []
        for m_idx in range(nb_matchs):
            col1, col2, col3 = st.columns([2, 0.3, 2])
            ex = (matchs_existants[m_idx]
                  if m_idx < len(matchs_existants) else {})
            with col1:
                dom = st.selectbox(
                    f"Domicile {m_idx+1}", equipes,
                    index=(equipes.index(ex["domicile"])
                           if ex and ex.get("domicile") in equipes
                           else 0),
                    key=f"dom_{j_select}_{m_idx}",
                )
            with col2:
                st.write("")
                st.write("**vs**")
            with col3:
                ext = st.selectbox(
                    f"Extérieur {m_idx+1}", equipes,
                    index=(equipes.index(ex["exterieur"])
                           if ex and ex.get("exterieur") in equipes
                           else min(1, len(equipes)-1)),
                    key=f"ext_{j_select}_{m_idx}",
                )
            matchs_j.append({"domicile": dom, "exterieur": ext})

        if st.form_submit_button("💾 Sauvegarder la journée",
                                  type="primary"):
            equipes_j = []
            for m in matchs_j:
                equipes_j.extend([m["domicile"], m["exterieur"]])
            if len(set(equipes_j)) != len(equipes_j):
                st.error("Une équipe apparaît plusieurs fois "
                         "dans la même journée.")
            else:
                while len(calendrier) <= j_idx:
                    calendrier.append([])
                calendrier[j_idx]   = matchs_j
                champ["calendrier"] = calendrier
                champ["modifie_le"] = datetime.now().strftime(
                    "%d/%m/%Y %H:%M")
                sauvegarder_donnees(donnees)
                st.success(f"✅ Journée {j_select} sauvegardée !")
                st.rerun()

    st.subheader("Calendrier complet")
    if calendrier:
        for j_idx2, matchs_j2 in enumerate(calendrier):
            if matchs_j2:
                with st.expander(f"Journée {j_idx2 + 1}"):
                    for m in matchs_j2:
                        st.write(f"  {m['domicile']} **vs** "
                                 f"{m['exterieur']}")
    else:
        st.info("Aucun match saisi dans le calendrier.")


def page_resultats(donnees, nom_champ):
    champ = donnees["championnats"][nom_champ]
    st.title(f"📝 Résultats — {nom_champ}")

    if not champ.get("equipes"):
        st.warning("⚠️ Veuillez d'abord saisir les équipes.")
        return
    if not champ.get("calendrier"):
        st.warning("⚠️ Veuillez d'abord saisir le calendrier.")
        return

    calendrier  = champ["calendrier"]
    resultats   = champ.get("resultats", {})
    nb_j        = len(calendrier)

    j_select = st.selectbox(
        "Sélectionner la journée",
        range(1, nb_j + 1),
        format_func=lambda x: f"Journée {x}",
    )
    j_key    = str(j_select)
    j_idx    = j_select - 1
    matchs_j = (calendrier[j_idx] if j_idx < len(calendrier) else [])

    if not matchs_j:
        st.warning("Aucun match dans le calendrier pour cette journée.")
        return

    resultats_j = resultats.get(j_key, [])
    st.subheader(f"Journée {j_select}")

    with st.form(f"form_res_j{j_select}"):
        nouveaux_resultats = []
        for m_idx, match in enumerate(matchs_j):
            dom = match["domicile"]
            ext = match["exterieur"]
            ex  = (resultats_j[m_idx]
                   if m_idx < len(resultats_j) else {})

            st.markdown(f"**{dom} vs {ext}**")

            reporte = st.checkbox(
                "Match reporté",
                value=bool(ex.get("reporte", False)),
                key=f"rep_{j_select}_{m_idx}",
                help="Cocher si ce match a été reporté à une date "
                     "ultérieure.",
            )

            if reporte:
                st.info("⏳ Match reporté — sera simulé comme "
                        "match restant.")
                nouveaux_resultats.append({
                    "domicile":  dom,
                    "exterieur": ext,
                    "reporte":   True,
                    "score_dom": 0,
                    "score_ext": 0,
                    "penalite":  False,
                    "vainqueur": None,
                })
            else:
                col1, col2, col3, col4, col5 = st.columns(
                    [2, 1, 1, 2, 2])
                with col1:
                    st.write(f"🏠 {dom}")
                with col2:
                    score_dom = st.number_input(
                        "Score dom",
                        min_value=0, max_value=999,
                        value=int(ex.get("score_dom", 0)),
                        key=f"sd_{j_select}_{m_idx}",
                        label_visibility="collapsed",
                    )
                with col3:
                    score_ext = st.number_input(
                        "Score ext",
                        min_value=0, max_value=999,
                        value=int(ex.get("score_ext", 0)),
                        key=f"se_{j_select}_{m_idx}",
                        label_visibility="collapsed",
                    )
                with col4:
                    st.write(f"✈️ {ext}")
                with col5:
                    penalite = st.checkbox(
                        "Pénalité/Forfait",
                        value=bool(ex.get("penalite", False)),
                        key=f"pen_{j_select}_{m_idx}",
                    )

                vainqueur = None
                if penalite:
                    vainqueur = st.selectbox(
                        "Vainqueur (pénalité)",
                        [dom, ext],
                        index=([dom, ext].index(ex["vainqueur"])
                               if ex.get("vainqueur") in [dom, ext]
                               else 0),
                        key=f"vain_{j_select}_{m_idx}",
                    )

                nouveaux_resultats.append({
                    "domicile":  dom,
                    "exterieur": ext,
                    "score_dom": score_dom,
                    "score_ext": score_ext,
                    "penalite":  penalite,
                    "reporte":   False,
                    "vainqueur": vainqueur,
                })
            st.divider()

        if st.form_submit_button("💾 Sauvegarder les résultats",
                                  type="primary"):
            erreur = False
            for res in nouveaux_resultats:
                if not res["reporte"] and not res["penalite"]:
                    if res["score_dom"] == res["score_ext"]:
                        st.error(
                            f"Score nul impossible "
                            f"({res['domicile']} vs {res['exterieur']})"
                        )
                        erreur = True
                        break
            if not erreur:
                resultats[j_key]    = nouveaux_resultats
                champ["resultats"]  = resultats
                champ["modifie_le"] = datetime.now().strftime(
                    "%d/%m/%Y %H:%M")
                sauvegarder_donnees(donnees)
                st.success(f"✅ Résultats de la journée "
                           f"{j_select} sauvegardés !")
                st.rerun()

    st.subheader("Résultats enregistrés")
    for j_k, res_j in sorted(resultats.items(),
                              key=lambda x: int(x[0])):
        with st.expander(f"Journée {j_k}"):
            for res in res_j:
                if res.get("reporte"):
                    st.write(
                        f"  ⏳ {res['domicile']} vs "
                        f"{res['exterieur']} — **REPORTÉ**"
                    )
                elif res.get("penalite"):
                    st.write(
                        f"  {res['domicile']} 0-0 "
                        f"{res['exterieur']} "
                        f"(Pénalité → {res['vainqueur']})"
                    )
                else:
                    st.write(
                        f"  {res['domicile']} "
                        f"**{res['score_dom']}-{res['score_ext']}** "
                        f"{res['exterieur']}"
                    )


def page_classement(donnees, nom_champ):
    champ = donnees["championnats"][nom_champ]
    st.title(f"📊 Classement — {nom_champ}")

    if not champ.get("equipes"):
        st.warning("⚠️ Veuillez d'abord saisir les équipes.")
        return
    if not champ.get("resultats"):
        st.info("Aucun résultat enregistré pour l'instant.")
        return

    classement     = calculer_classement_complet(champ)
    nb_equipes     = champ["nb_equipes"]
    nb_relegations = champ["nb_relegations"]
    nb_montees     = champ.get("nb_montees", 0)
    nb_maintien    = nb_equipes - nb_relegations
    nb_j_jouees    = len(champ["resultats"])
    matchs_rest    = get_matchs_restants(champ)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Journées jouées", nb_j_jouees)
    with col2:
        st.metric("Journées restantes",
                  champ["nb_journees"] - nb_j_jouees)
    with col3:
        st.metric("Matchs restants", len(matchs_rest))
    with col4:
        mode = ("Exhaustive" if len(matchs_rest) <= SEUIL_EXHAUSTIF
                else "Monte Carlo")
        st.metric("Mode simulation", mode)

    st.divider()
    st.subheader("Classement actuel")

    df_cl = pd.DataFrame(classement)
    df_cl = df_cl.rename(columns={
        "rang":         "Rang",
        "equipe":       "Équipe",
        "pts":          "Pts",
        "j":            "J",
        "v":            "V",
        "d":            "D",
        "pts_marques":  "Pour",
        "pts_encaisses":"Contre",
        "diff":         "Diff",
    })

    def get_zone(rang):
        if rang <= nb_montees:    return "🔵 Montée"
        elif rang <= nb_maintien: return "✅ Maintien"
        else:                     return "❌ Relégation"

    df_cl["Zone"] = df_cl["Rang"].apply(get_zone)

    def colorier_ligne(row):
        rang = row["Rang"]
        if rang <= nb_montees:    return ["background-color: #d6eaf8"] * len(row)
        elif rang <= nb_maintien: return ["background-color: #d4edda"] * len(row)
        else:                     return ["background-color: #fadbd8"] * len(row)

    st.dataframe(
        df_cl.style.apply(colorier_ligne, axis=1),
        use_container_width=True,
        hide_index=True,
    )

    col_l1, col_l2, col_l3 = st.columns(3)
    with col_l1:
        if nb_montees > 0:
            st.markdown(f"🔵 **Zone de montée** (Top {nb_montees})")
    with col_l2:
        st.markdown("✅ **Zone de maintien**")
    with col_l3:
        st.markdown(f"❌ **Zone de relégation** (Bottom {nb_relegations})")

    st.divider()
    st.subheader("Évolution du classement")
    fig_evo = graphique_evolution_classement(champ)
    if fig_evo:
        st.plotly_chart(fig_evo, use_container_width=True)
    else:
        st.info("Pas encore assez de données pour afficher l'évolution.")


def page_simulation(donnees, nom_champ):
    champ = donnees["championnats"][nom_champ]
    st.title(f"🎲 Simulation — {nom_champ}")

    if not champ.get("equipes"):
        st.warning("⚠️ Veuillez d'abord saisir les équipes.")
        return

    matchs_rest = get_matchs_restants(champ)
    nb_matchs   = len(matchs_rest)

    if nb_matchs == 0:
        st.success("✅ Toutes les journées sont terminées !")
        return

    mode         = ("exhaustive" if nb_matchs <= SEUIL_EXHAUSTIF
                    else "monte_carlo")
    nb_scenarios = (2 ** nb_matchs if mode == "exhaustive"
                    else NB_SIMULATIONS_MC)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Matchs restants", nb_matchs)
    with col2:
        st.metric("Mode",
                  "Exhaustive" if mode == "exhaustive"
                  else "Monte Carlo")
    with col3:
        st.metric("Scénarios",
                  f"{nb_scenarios:,}" if mode == "exhaustive"
                  else f"{NB_SIMULATIONS_MC:,} (aléatoires)")

    if mode == "exhaustive":
        st.success(f"✅ Simulation exhaustive : {nb_scenarios:,} scénarios")
    else:
        st.warning(
            f"⚠️ Monte Carlo : {nb_matchs} matchs restants → "
            f"{NB_SIMULATIONS_MC:,} simulations aléatoires."
        )

    st.divider()
    st.subheader("⚙️ Paramètres de simulation")
    diff_moyen = st.slider(
        "Écart de points moyen pour les matchs simulés",
        min_value=1, max_value=30, value=10, step=1,
        help="Écart de points moyen entre vainqueur et perdant.",
    )
    st.caption(
        f"Avec cet écart : vainqueur ≈ {70 + diff_moyen//2} pts | "
        f"perdant ≈ {70 - diff_moyen//2} pts"
    )
    st.divider()

    with st.expander("Voir les matchs restants"):
        for m in matchs_rest:
            st.write(f"J{m['journee']} — "
                     f"{m['domicile']} vs {m['exterieur']}")

    if st.button("🚀 Lancer la simulation", type="primary"):
        with st.spinner("Simulation en cours..."):
            debut = time.time()
            resultats_sim, compteur_rang, tous_scenarios, mode_ret, nb_total = \
                lancer_simulation(champ, diff_moyen)
            duree = time.time() - debut

        if resultats_sim is None:
            st.error("Erreur lors de la simulation.")
            return

        st.success(f"✅ Simulation terminée en {duree:.2f} secondes !")
        st.session_state["resultats_sim"]   = resultats_sim
        st.session_state["compteur_rang"]   = compteur_rang
        st.session_state["tous_scenarios"]  = tous_scenarios
        st.session_state["mode_sim"]        = mode_ret
        st.session_state["nb_total_sim"]    = nb_total
        st.session_state["matchs_rest_sim"] = matchs_rest

    if "resultats_sim" in st.session_state:
        resultats_sim  = st.session_state["resultats_sim"]
        compteur_rang  = st.session_state["compteur_rang"]
        tous_scenarios = st.session_state.get("tous_scenarios", [])
        mode_ret       = st.session_state["mode_sim"]
        nb_total       = st.session_state["nb_total_sim"]
        matchs_rest_sim = st.session_state.get("matchs_rest_sim",
                                                matchs_rest)
        nb_montees     = champ.get("nb_montees", 0)
        nb_equipes     = champ["nb_equipes"]
        nb_maintien    = nb_equipes - champ["nb_relegations"]

        st.subheader("Résultats de la simulation")

        tabs = ["📊 Probabilités de maintien"]
        if nb_montees > 0:
            tabs.append("🔵 Probabilités de montée")
        tabs.append("📈 Distribution des classements")
        tabs.append("🔍 Scénarios personnalisés")

        tab_list = st.tabs(tabs)
        tab_idx  = 0

        # Onglet maintien
        with tab_list[tab_idx]:
            fig_sim = graphique_probabilites(resultats_sim, champ)
            st.plotly_chart(fig_sim, use_container_width=True)

            df_sim = pd.DataFrame(resultats_sim)
            df_sim["Statut"] = df_sim["pct"].apply(statut_maintien)
            df_affich = df_sim.rename(columns={
                "equipe":    "Équipe",
                "maintien":  "Scén. Maintien",
                "relegation":"Scén. Relégation",
                "pct":       "% Maintien",
            })[["Équipe", "Scén. Maintien",
                "Scén. Relégation", "% Maintien", "Statut"]]

            def colorier_sim(row):
                pct = row["% Maintien"]
                if pct == 100.0:   c = "#d4edda"
                elif pct >= 90.0:  c = "#d0f0c0"
                elif pct >= 70.0:  c = "#fef9e7"
                elif pct >= 50.0:  c = "#fdebd0"
                elif pct > 0.0:    c = "#fadbd8"
                else:              c = "#f0f0f0"
                return [f"background-color: {c}"] * len(row)

            st.dataframe(
                df_affich.style.apply(colorier_sim, axis=1),
                use_container_width=True, hide_index=True,
            )
        tab_idx += 1

        # Onglet montée
        if nb_montees > 0:
            with tab_list[tab_idx]:
                fig_montee = graphique_probabilites_montee(resultats_sim)
                if fig_montee:
                    st.plotly_chart(fig_montee,
                                    use_container_width=True)

                df_montee = pd.DataFrame(resultats_sim)
                df_montee = df_montee.sort_values(
                    "pct_montee", ascending=False)
                df_montee["Statut"] = df_montee["pct_montee"].apply(
                    statut_montee)
                df_aff_m = df_montee.rename(columns={
                    "equipe":    "Équipe",
                    "montee":    "Scén. Montée",
                    "pct_montee":"% Montée",
                })[["Équipe", "Scén. Montée", "% Montée", "Statut"]]
                st.dataframe(df_aff_m, use_container_width=True,
                             hide_index=True)
            tab_idx += 1

        # Onglet distribution
        with tab_list[tab_idx]:
            st.subheader("Distribution des classements finaux")
            st.caption(
                "Probabilité d'arriver à chaque place finale. "
                "Les places à 0% sont exclues."
            )
            for item in resultats_sim:
                eq   = item["equipe"]
                dist = compteur_rang.get(eq, {})
                rangs_ok = sorted(
                    [r for r in range(1, nb_equipes + 1)
                     if dist.get(r, 0) > 0]
                )
                if not rangs_ok:
                    continue
                with st.expander(
                    f"{eq} — Maintien : {item['pct']:.2f}%"
                ):
                    dist_data = {
                        f"{r}e place": [
                            f"{dist[r]:,}",
                            f"{dist[r]/nb_total*100:.2f}%",
                        ]
                        for r in rangs_ok
                    }
                    df_dist = pd.DataFrame(
                        dist_data, index=["Scénarios", "%"])

                    def colorier_dist(col):
                        rang = int(col.name.replace("e place", ""))
                        if rang <= nb_montees:       c = "#d6eaf8"
                        elif rang <= nb_maintien:    c = "#d4edda"
                        else:                        c = "#fadbd8"
                        return [f"background-color: {c}"] * len(col)

                    st.dataframe(
                        df_dist.style.apply(colorier_dist, axis=0),
                        use_container_width=True,
                    )
        tab_idx += 1

        # Onglet scénarios personnalisés
        with tab_list[tab_idx]:
            st.subheader("🔍 Scénarios Personnalisés")
            st.write(
                "Définissez le statut final souhaité pour chaque "
                "équipe et analysez les scénarios correspondants."
            )

            if not tous_scenarios:
                st.warning(
                    "Les scénarios détaillés ne sont disponibles "
                    "qu'en mode exhaustif ou après une nouvelle "
                    "simulation."
                )
            else:
                equipes = champ["equipes"]

                st.subheader("Définir les conditions")
                conditions = {}

                nb_cols = 3
                cols    = st.columns(nb_cols)

                for idx, eq in enumerate(equipes):
                    with cols[idx % nb_cols]:
                        statut = st.selectbox(
                            eq,
                            options=[
                                "— (indifférent)",
                                "monte",
                                "se maintient",
                                "est relégué",
                            ],
                            key=f"cond_{eq}",
                        )
                        if statut == "monte":
                            conditions[eq] = "monte"
                        elif statut == "se maintient":
                            conditions[eq] = "maintien"
                        elif statut == "est relégué":
                            conditions[eq] = "relegue"

                st.divider()

                if not conditions:
                    st.info(
                        "Sélectionnez au moins une condition "
                        "pour lancer l'analyse."
                    )
                else:
                    st.write("**Conditions sélectionnées :**")
                    for eq, stat in conditions.items():
                        emoji = ("🔵" if stat == "monte" else
                                 "✅" if stat == "maintien" else "❌")
                        st.write(f"  {emoji} **{eq}** → {stat}")

                    if st.button("🔍 Analyser ces scénarios",
                                  type="primary"):
                        (nb_ok, pct_ok,
                         proba_match,
                         matchs_obligatoires) = \
                            analyser_scenarios_personnalises(
                                tous_scenarios, conditions,
                                matchs_rest_sim, nb_total,
                            )

                        st.session_state["analyse_perso"] = {
                            "nb_ok":               nb_ok,
                            "pct_ok":              pct_ok,
                            "proba_match":         proba_match,
                            "matchs_obligatoires": matchs_obligatoires,
                            "conditions":          conditions,
                        }

                    if "analyse_perso" in st.session_state:
                        ap = st.session_state["analyse_perso"]

                        st.divider()

                        # Résultat global
                        col_r1, col_r2 = st.columns(2)
                        with col_r1:
                            st.metric(
                                "Scénarios correspondants",
                                f"{ap['nb_ok']:,} / {nb_total:,}",
                            )
                        with col_r2:
                            st.metric(
                                "Probabilité",
                                f"{ap['pct_ok']:.2f}%",
                            )

                        if ap["nb_ok"] == 0:
                            st.error(
                                "❌ Aucun scénario ne correspond "
                                "à ces conditions. Cette combinaison "
                                "est impossible."
                            )
                        else:
                            # Matchs obligatoires
                            st.subheader(
                                "✅ Résultats obligatoires "
                                "(communs à 100% des scénarios)"
                            )
                            if ap["matchs_obligatoires"]:
                                for m in ap["matchs_obligatoires"]:
                                    st.success(
                                        f"J{m['journee']} — "
                                        f"**{m['vainqueur']}** doit "
                                        f"gagner contre "
                                        f"{''.join([m['domicile'] if m['vainqueur'] == m['exterieur'] else m['exterieur']])}"
                                    )
                            else:
                                st.info(
                                    "Aucun résultat n'est obligatoire "
                                    "dans tous les scénarios."
                                )

                            # Probabilités par match
                            st.subheader(
                                "📊 Probabilité de victoire par match "
                                "dans ces scénarios"
                            )
                            rows_pm = [[
                                "Journée", "Domicile",
                                "Extérieur",
                                "% Dom gagne", "% Ext gagne",
                                "Favori",
                            ]]
                            for pm in ap["proba_match"]:
                                favori = (
                                    pm["domicile"]
                                    if pm["pct_dom"] >= pm["pct_ext"]
                                    else pm["exterieur"]
                                )
                                rows_pm.append([
                                    f"J{pm['journee']}",
                                    pm["domicile"],
                                    pm["exterieur"],
                                    f"{pm['pct_dom']:.1f}%",
                                    f"{pm['pct_ext']:.1f}%",
                                    favori,
                                ])

                            df_pm = pd.DataFrame(
                                rows_pm[1:],
                                columns=rows_pm[0],
                            )

                            def colorier_pm(row):
                                pd_val = float(
                                    row["% Dom gagne"].replace("%", ""))
                                pe_val = float(
                                    row["% Ext gagne"].replace("%", ""))
                                colors = [""] * len(row)
                                if pd_val == 100.0:
                                    colors[3] = "background-color: #d4edda"
                                    colors[4] = "background-color: #fadbd8"
                                elif pe_val == 100.0:
                                    colors[3] = "background-color: #fadbd8"
                                    colors[4] = "background-color: #d4edda"
                                elif pd_val >= 70:
                                    colors[3] = "background-color: #d4edda"
                                elif pe_val >= 70:
                                    colors[4] = "background-color: #d4edda"
                                return colors

                            st.dataframe(
                                df_pm.style.apply(
                                    colorier_pm, axis=1),
                                use_container_width=True,
                                hide_index=True,
                            )

                            st.caption(
                                "🟢 = résultat très favorable (≥70%) | "
                                "🔴 = résultat défavorable | "
                                "100% = résultat obligatoire"
                            )

        st.caption(
            f"Mode : {'Exhaustive' if mode_ret == 'exhaustive' else 'Monte Carlo'} "
            f"| Scénarios : {nb_total:,} | "
            f"Écart moyen simulé : {diff_moyen} pts"
            if "diff_moyen" in dir() else
            f"Mode : {'Exhaustive' if mode_ret == 'exhaustive' else 'Monte Carlo'} "
            f"| Scénarios : {nb_total:,}"
        )


def page_rapport(donnees, nom_champ):
    champ = donnees["championnats"][nom_champ]
    st.title(f"📄 Rapport PDF — {nom_champ}")

    if not champ.get("equipes"):
        st.warning("⚠️ Veuillez d'abord saisir les équipes.")
        return
    if not champ.get("resultats"):
        st.warning("⚠️ Aucun résultat enregistré.")
        return

    classement    = calculer_classement_complet(champ)
    resultats_sim = st.session_state.get("resultats_sim", None)
    compteur_rang = st.session_state.get("compteur_rang", None)
    mode_sim      = st.session_state.get("mode_sim", None)
    nb_total      = st.session_state.get("nb_total_sim", None)

    if resultats_sim is None:
        st.info(
            "💡 Pour inclure les probabilités dans le rapport, "
            "lancez d'abord une simulation."
        )

    st.subheader("Contenu du rapport")
    col1, col2 = st.columns(2)
    with col1:
        st.write("✅ Classement actuel")
        st.write("✅ Statistiques par équipe")
        if resultats_sim:
            st.write("✅ Probabilités de maintien")
            if champ.get("nb_montees", 0) > 0:
                st.write("✅ Probabilités de montée")
            st.write("✅ Distribution des classements")
    with col2:
        st.write(f"✅ Championnat : {nom_champ}")
        st.write(f"✅ Date : {datetime.now().strftime('%d/%m/%Y')}")

    st.divider()

    if st.button("📄 Générer et télécharger le PDF", type="primary"):
        with st.spinner("Génération du PDF..."):
            pdf_bytes = generer_pdf_streamlit(
                champ, classement, resultats_sim,
                compteur_rang, mode_sim, nb_total,
            )
        nom_fichier = (
            f"rapport_{nom_champ.replace(' ', '_')}_"
            f"{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
        )
        st.download_button(
            label="⬇️ Télécharger le rapport PDF",
            data=pdf_bytes,
            file_name=nom_fichier,
            mime="application/pdf",
            type="primary",
        )
        st.success("✅ PDF généré avec succès !")

# =============================================================================
# APPLICATION PRINCIPALE
# =============================================================================

def main():
    if "page" not in st.session_state:
        st.session_state["page"] = "accueil"
    if "champ_actif" not in st.session_state:
        st.session_state["champ_actif"] = None

    donnees   = charger_donnees()
    nom_champ = st.session_state.get("champ_actif")
    champ_ok  = (nom_champ is not None and
                 nom_champ in donnees["championnats"])

    with st.sidebar:
        st.title("""🏀 Simulateur FFBB
        Créé par Raphaël Halbwachs""")
        st.divider()

        championnats_liste = list(donnees["championnats"].keys())
        if championnats_liste:
            champ_select = st.selectbox(
                "Championnat actif",
                ["-- Sélectionner --"] + championnats_liste,
                index=(championnats_liste.index(nom_champ) + 1
                       if nom_champ in championnats_liste else 0),
            )
            if champ_select != "-- Sélectionner --":
                if champ_select != nom_champ:
                    st.session_state["champ_actif"] = champ_select
                    st.session_state.pop("resultats_sim",  None)
                    st.session_state.pop("compteur_rang",  None)
                    st.session_state.pop("tous_scenarios", None)
                    st.session_state.pop("analyse_perso",  None)
                    st.rerun()
                nom_champ = champ_select
                champ_ok  = True
        else:
            st.info("Aucun championnat créé.")

        st.divider()
        st.subheader("Navigation")

        pages = [
            ("🏠", "accueil",      "Accueil"),
            ("🏆", "championnats", "Championnats"),
            ("💾", "sauvegarde",   "Sauvegarde"),
        ]
        if champ_ok:
            pages += [
                ("👥", "equipes",    "Équipes"),
                ("📅", "calendrier", "Calendrier"),
                ("📝", "resultats",  "Résultats"),
                ("📊", "classement", "Classement"),
                ("🎲", "simulation", "Simulation"),
                ("📄", "rapport",    "Rapport PDF"),
            ]

        for icone, page_id, label in pages:
            if st.button(
                f"{icone} {label}",
                use_container_width=True,
                type=("primary"
                      if st.session_state["page"] == page_id
                      else "secondary"),
            ):
                st.session_state["page"] = page_id
                st.rerun()

        if champ_ok:
            st.divider()
            st.caption(f"**Actif :** {nom_champ}")

    page = st.session_state["page"]

    if page == "accueil":
        st.title("🏀 Simulateur de Fin de Saison FFBB")
        st.markdown("""
        ### Bienvenue !

        Cette application vous permet de simuler les scénarios
        de fin de saison pour n'importe quel championnat FFBB.

        #### Fonctionnalités
        - 🏆 Gestion de plusieurs championnats (NM3, PRM, etc.)
        - 👥 Saisie des équipes et du calendrier
        - 📝 Saisie des résultats match par match
        - ⏳ Gestion des matchs reportés et des pénalités
        - 📊 Classement automatique avec règles de départage FFBB
        - 📈 Évolution du classement au fil des journées
        - 🎲 Simulation exhaustive ou Monte Carlo
        - 🔵 Probabilités de montée et de maintien
        - 📈 Distribution des classements finaux
        - 🔍 Analyse de scénarios personnalisés
        - 💾 Sauvegarde et restauration des données
        - 📄 Génération de rapport PDF

        #### Règles FFBB appliquées
        | Paramètre | Valeur |
        |-----------|--------|
        | Victoire | 2 points |
        | Défaite normale | 1 point |
        | Défaite par pénalité/forfait | 0 point |
        | Match reporté | Non comptabilisé (simulé) |
        | Départage 1 | Points confrontations directes |
        | Départage 2 | Différentiel confrontations directes |
        | Départage 3 | Points marqués confrontations directes |
        | Départage 4 | Différentiel général |
        | Départage 5 | Points marqués général |
        """)

    elif page == "championnats":
        page_gestion_championnats(donnees)
    elif page == "modifier_championnat":
        page_modifier_championnat(donnees)
    elif page == "sauvegarde":
        page_sauvegarde(donnees)
    elif page == "equipes" and champ_ok:
        page_equipes(donnees, nom_champ)
    elif page == "calendrier" and champ_ok:
        page_calendrier(donnees, nom_champ)
    elif page == "resultats" and champ_ok:
        page_resultats(donnees, nom_champ)
    elif page == "classement" and champ_ok:
        page_classement(donnees, nom_champ)
    elif page == "simulation" and champ_ok:
        page_simulation(donnees, nom_champ)
    elif page == "rapport" and champ_ok:
        page_rapport(donnees, nom_champ)
    else:
        st.warning("⚠️ Veuillez sélectionner un championnat.")
        st.session_state["page"] = "championnats"
        st.rerun()


main()
