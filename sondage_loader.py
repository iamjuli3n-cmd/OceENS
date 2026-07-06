import sqlite3
from dataclasses import dataclass, field
from typing import List, Dict, Any

# -----------------------------------------------------------------------------
# 0. Fonction utilitaire de nettoyage des textes (Correction Encodage)
# -----------------------------------------------------------------------------


def clean_mojibake(text: Any) -> str:
    """
    Détecte et répare automatiquement les caractères accentués mal encodés
    provenant de la base de données (ex: 'prÃªts' -> 'prêts').
    """
    if not isinstance(text, str):
        return str(text) if text is not None else ""
    try:
        # Tente de restaurer la chaîne si elle a été encodée en UTF-8 puis lue en Latin-1
        return text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        # En cas d'échec, application d'un dictionnaire de secours pour les cas fréquents
        replacements = {
            "Ã©": "é",
            "Ã¨": "è",
            "Ã ": "à",
            "Ã§": "ç",
            "Ã¹": "ù",
            "Ã¢": "â",
            "Ãª": "ê",
            "Ã®": "î",
            "Ã´": "ô",
            "Ã‰": "É",
            "Ã ": "À",
            "Ãª": "ê",
            "Ã»": "û",
        }
        for bad, good in replacements.items():
            text = text.replace(bad, good)
        return text


# -----------------------------------------------------------------------------
# 1. Définition des Dataclasses (Modèles propres pour la Visualisation)
# -----------------------------------------------------------------------------


@dataclass
class OptionData:
    option_id: int
    text: str


@dataclass
class AnswerData:
    answer_id: int
    value: str
    submission_id: int | None = None
    module_id: int | None = None
    ue: str = ""
    module: str = ""
    teacher: str = ""


@dataclass
class QuestionData:
    question_id: int
    text: str
    category: str
    question_type: str
    options: List[OptionData] = field(default_factory=list)
    reponses: List[AnswerData] = field(default_factory=list)


@dataclass
class SectionData:
    section_id: int
    nom: str
    order: int
    questions: List[QuestionData] = field(default_factory=list)


@dataclass
class ModuleData:
    module_id: int
    nom: str
    ue: str
    teacher: str  # Corrigé au singulier d'après la structure réelle


@dataclass
class FullSurvey:
    """Objet racine contenant tout le contexte et les données nettoyées d'un survey"""

    template_id: int
    survey_id: int
    campus: str
    program: str
    semester: str
    school_year: str  # Corrigé d'après models.py (scolaire en minuscule)
    modules: List[ModuleData] = field(default_factory=list)
    sections: List[SectionData] = field(default_factory=list)

    def to_flat_dataframe_records(self) -> List[Dict[str, Any]]:
        """
        Génère une liste de dictionnaires à plat, idéale pour Pandas :
        df = pd.DataFrame(survey.to_flat_dataframe_records())
        """
        records = []
        for section in self.sections:
            for question in section.questions:
                for answer in question.reponses:
                    records.append(
                        {
                            "campus": self.campus,
                            "program": self.program,
                            "semester": self.semester,
                            "school_year": self.school_year,
                            "submission_id": answer.submission_id,
                            "ue": answer.ue,
                            "module": answer.module,
                            "teacher": answer.teacher,
                            "section": section.nom,
                            "question_id": question.question_id,
                            "text": question.text,
                            "question_type": question.question_type,
                            "category": question.category,
                            "answer_id": answer.answer_id,
                            "answer_value": answer.value,
                        }
                    )
        return records


# -----------------------------------------------------------------------------
# 2. Le chargeur de données (Loader)
# -----------------------------------------------------------------------------


def load_sondage_complet(db_path: str, survey_id: int) -> FullSurvey:
    """
    Se connecte à la base SQLite, extrait les données du survey cible,
    nettoie les chaînes de caractères et structure le tout sous forme d'objet.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # Accès aux colonnes par nom
    cursor = conn.cursor()

    def get_row_field(row: sqlite3.Row, *possible_names) -> str:
        keys = row.keys()
        for name in possible_names:
            if name in keys:
                return row[name]
        return ""

    # --- A. Infos du survey ---
    cursor.execute(
        "SELECT * FROM surveys WHERE survey_id = ?",
        (survey_id,),
    )
    survey_row = cursor.fetchone()
    if not survey_row:
        conn.close()
        raise ValueError(f"Sondage introuvable ( Sondage: {survey_id})")

    survey = FullSurvey(
        template_id=survey_row["template_id"],
        survey_id=survey_row["survey_id"],
        campus=clean_mojibake(survey_row["campus"]),
        program=clean_mojibake(survey_row["program"]),
        semester=clean_mojibake(survey_row["semester"]),
        school_year=clean_mojibake(survey_row["school_year"]),
    )

    # --- B. Récupération des Modules ---
    cursor.execute(
        "SELECT * FROM Modules WHERE survey_id = ?",
        (survey_id,),
    )
    for row in cursor.fetchall():
        survey.modules.append(
            ModuleData(
                module_id=row["module_id"],
                nom=clean_mojibake(row["name"]),
                ue=clean_mojibake(row["ue"]),
                teacher=clean_mojibake(row["teacher"]),
            )
        )
    modules_by_id = {module.module_id: module for module in survey.modules}

    # --- C. Récupération des Sections ---
    cursor.execute(
        "SELECT * FROM Sections WHERE template_id = ? ORDER BY 'order'",
        (survey.template_id,),
    )
    sections_dict = {}
    for row in cursor.fetchall():
        sec = SectionData(
            section_id=row["section_id"],
            nom=clean_mojibake(row["name"]),
            order=row["order"],
        )
        sections_dict[sec.section_id] = sec
        survey.sections.append(sec)

    # --- D. Récupération des Questions ---
    cursor.execute(
        "SELECT * FROM questions WHERE template_id = ?", (survey.template_id,)
    )
    questions_dict = {}
    for row in cursor.fetchall():
        q = QuestionData(
            question_id=row["question_id"],
            text=clean_mojibake(row["text"]),
            category=clean_mojibake(row["category"]),
            question_type=clean_mojibake(row["question_type"]),
        )
        questions_dict[(row["section_id"], row["question_id"])] = q
        if row["section_id"] in sections_dict:
            sections_dict[row["section_id"]].questions.append(q)

    # --- E. Récupération des Options de réponses (QCM/QCU) ---
    cursor.execute("SELECT * FROM Options WHERE template_id = ?", (survey.template_id,))
    for row in cursor.fetchall():
        opt = OptionData(
            option_id=row["option_id"],
            text=clean_mojibake(row["text"]),
        )
        q_key = (row["section_id"], row["question_id"])
        if q_key in questions_dict:
            questions_dict[q_key].options.append(opt)

    # --- F. Récupération des Réponses soumises avec contexte module / UE ---

    cursor.execute(
        """
        SELECT
            a.answer_id,
            a.value,
            a.submission_id,
            a.section_id,
            a.question_id,
            a.module_id,
            a.teacher AS answer_teacher,

            m.name AS module_name,
            m.ue AS module_ue,
            m.teacher AS module_teacher
        FROM Answers a
        LEFT JOIN Modules m
            ON m.module_id = a.module_id
            AND m.survey_id = a.survey_id
        WHERE a.survey_id = ?
        """,
        (survey_id,),
    )

    for row in cursor.fetchall():
        module_id = row["module_id"]

        teacher_answer = row["answer_teacher"] if "answer_teacher" in row.keys() else ""
        module_teacher = row["module_teacher"] if "module_teacher" in row.keys() else ""

        rep = AnswerData(
            answer_id=row["answer_id"],
            value=clean_mojibake(row["value"]),
            submission_id=row["submission_id"] if "submission_id" in row.keys() else None,
            module_id=module_id,
            ue=clean_mojibake(row["module_ue"]),
            module=clean_mojibake(row["module_name"]),
            teacher=clean_mojibake(teacher_answer or module_teacher),
        )

        q_key = (row["section_id"], row["question_id"])
        if q_key in questions_dict:
            questions_dict[q_key].reponses.append(rep)

    conn.close()
    return survey
