import pandas as pd
from typing import Dict, Any

def get_visualisation_context(survey_obj) -> Dict[str, Any]:
    """
    Prépare les données pour le filtrage et l'agrégation côté client (Drill-down).
    Calcule les KPI globaux en backend pour garantir la robustesse.
    """
    records = survey_obj.to_flat_dataframe_records()
    
    # Remplacement des variables non résolues dans les titres de graphes
    campus = survey_obj.campus or ""
    formation = survey_obj.formation or ""
    module_name = survey_obj.modules[0].nom if len(survey_obj.modules) == 1 else "ce module"
    enseignant_name = survey_obj.modules[0].enseignant if len(survey_obj.modules) == 1 else "l'enseignant"

    clean_records = []
    for r in records:
        if "OUVERTE" not in str(r.get("Type_Question", "")).upper():
            # Correction des placeholders
            for field in ["Section", "Question"]:
                if r.get(field):
                    val = str(r[field])
                    val = val.replace("[CAMPUS]", campus)
                    val = val.replace("[FORMATION]", formation)
                    val = val.replace("[MODULE]", module_name)
                    val = val.replace("[ENSEIGNANT]", enseignant_name)
                    r[field] = val
            clean_records.append(r)
    
    ues = list(set([m.ue for m in survey_obj.modules if m.ue]))
    modules = [{"id": m.id_module, "nom": m.nom, "ue": m.ue} for m in survey_obj.modules]
    
    df = pd.DataFrame(clean_records)
    satisfaction_pct = 0
    recommandation_avg = 0
    
    if not df.empty:
        # Taux de satisfaction globale (Questions de type QCU_Satisfaction)
        df_sat = df[df['Type_Question'].astype(str).str.contains('SATISFACTION', case=False, na=False)]
        sat_positive = ["Très satisfait", "Plutôt satisfait", "Totalement satisfait"]
        if not df_sat.empty:
            total_sat = len(df_sat)
            pos_sat = len(df_sat[df_sat['Valeur_Reponse'].isin(sat_positive)])
            satisfaction_pct = round((pos_sat / total_sat) * 100, 1) if total_sat > 0 else 0

        # Taux de recommandation (NPS)
        df_nps = df[df['Type_Question'].astype(str).str.contains('NPS', case=False, na=False)]
        if not df_nps.empty:
            valid_nps = pd.to_numeric(df_nps['Valeur_Reponse'], errors='coerce').dropna()
            if not valid_nps.empty:
                # Moyenne sur 10
                recommandation_avg = round(valid_nps.mean(), 1)
                
    return {
        "kpis": {
            "satisfaction": satisfaction_pct,
            "nps": recommandation_avg
        },
        "filters": {
            "ues": ues,
            "modules": modules
        },
        "records": clean_records
    }
