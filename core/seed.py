"""Peuplement initial de la base de données (seed).

Ce module remplit la base avec des données de départ : filières (toujours
synchronisées depuis un CSV), fournisseur LLM par défaut (idempotent), puis un
jeu de données de démonstration (utilisateurs, sondages, réponses...) UNIQUEMENT
si la base est vide.

Point d'entrée : `seed_all_if_necessary()`, appelé au démarrage de l'app.
"""

from sqlmodel import Session, delete, select
from pathlib import Path
import logging

import csv
import json
from models import (
    Program,
    User,
    Role,
    Template,
    Section,
    Question,
    Option,
    Module,
    Survey,
    Respondent,
    Answer,
    Submission,
    Prompt,
    LLMModelPrice,
    LLMProvider,
    Stat,
)
from core.database import engine

logger = logging.getLogger("uvicorn")



ADDITIONAL_STUDENT_USERS = [
    (9, "oceens.student07@epf.fr"),
    (10, "oceens.student08@epf.fr"),
    (11, "oceens.student09@epf.fr"),
    (12, "oceens.student10@epf.fr"),
    (13, "oceens.student11@epf.fr"),
    (14, "oceens.student12@epf.fr"),
    (15, "oceens.student13@epf.fr"),
    (16, "oceens.student14@epf.fr"),
    (17, "oceens.student15@epf.fr"),
    (18, "oceens.student16@epf.fr"),
    (19, "oceens.student17@epf.fr"),
    (20, "oceens.student18@epf.fr"),
    (21, "oceens.student19@epf.fr"),
    (22, "oceens.student20@epf.fr"),
]


# submission_id, user_id, created_at
SEEDED_SUBMISSIONS = [
    (1, 1, "2026-06-30 16:24:04"),
    (2, 2, "2026-06-30 16:27:04"),
    (3, 3, "2026-06-30 16:22:04"),
    (4, 4, "2026-06-30 16:26:04"),
    (5, 5, "2026-06-30 16:32:04"),
    (6, 6, "2026-06-30 16:32:04"),
    (7, 9, "2026-06-30 16:36:04"),
    (8, 10, "2026-06-30 16:39:04"),
    (9, 11, "2026-06-30 16:43:04"),
    (10, 12, "2026-06-30 16:47:04"),
]


SEEDED_SURVEYS = [
    {
        "survey_id": 1,
        "program": "MDAI5",
        "campus": "Montpellier",
        "answers_file": "seed_answers.csv",
    },
    {
        "survey_id": 2,
        "program": "MDAI4",
        "campus": "Montpellier",
        "answers_file": "seed_answers_survey_2.csv",
    },
    {
        "survey_id": 3,
        "program": "MIAN5",
        "campus": "Saint-Nazaire",
        "answers_file": "seed_answers_survey_3.csv",
    },
    {
        "survey_id": 4,
        "program": "MDID5",
        "campus": "Troyes",
        "answers_file": "seed_answers_survey_4.csv",
    },
]


def seed_users(session: Session):
    """Remplit la table users."""

    user_data = [
        (1, "antoine.gademer@epf.fr"),
        (2, "bob.leponge@epfedu.fr"),
        (3, "peter.parker@epfedu.fr"),
        (4, "mickey.mouse@epfedu.fr"),
        (5, "naruto.uzumaki@epfedu.fr"),
        (6, "yassine.gharbi@epfedu.fr"),
        (7, "arnaud.jousset@epf.fr"),
        (8, "etienne.gibaud@epf.fr"),
        *ADDITIONAL_STUDENT_USERS,
    ]
    for u_data in user_data:
        user = User(user_id=u_data[0], mail=u_data[1])
        session.merge(
            user
        )  # Utilisation de merge pour éviter les erreurs si l'ID existe déjà
    session.commit()


def seed_roles(session: Session):
    """Remplit la table roles."""

    role_data = [
        (1, "admin"),
        (1, "program_manager:MDAI5"),
        (6, "admin"),
        (6, "campus_manager:Montpellier"),
        (7, "admin"),
        (8, "admin"),
    ]
    for r_data in role_data:
        role = Role(user_id=r_data[0], role=r_data[1])
        session.merge(
            role
        )  # Utilisation de merge pour éviter les erreurs si l'ID existe déjà
    session.commit()


def seed_templates(session: Session):
    """Remplit la table templates."""
    templates_data = [
        {"template_id": 1, "name": "Sondage_Semestriel_2025", "user_id": 1, "active": True},
        {"template_id": 2, "name": "Sondage_Court",            "user_id": 1, "active": True},
        {"template_id": 3, "name": "Évaluation_Pédagogique",   "user_id": 1, "active": True},
    ]
    for data in templates_data:
        session.merge(Template(**data))
    session.commit()


def seed_sections(session: Session):
    """Remplit la table sections."""
    sections_data = [
        # ── Template 1 : Sondage_Semestriel_2025 ─────────────────────────
        {"template_id": 1, "section_id": 1, "name": "Campus",             "order": 1, "section_type": "C"},
        {"template_id": 1, "section_id": 2, "name": "Formation",          "order": 2, "section_type": "P"},
        {"template_id": 1, "section_id": 3, "name": "Module / Enseignant","order": 3, "section_type": "ME"},
        {"template_id": 1, "section_id": 4, "name": "Recommandation",     "order": 4, "section_type": "R"},

        # ── Template 2 : Sondage_Court (version allégée) ─────────────────
        {"template_id": 2, "section_id": 5, "name": "Campus",             "order": 1, "section_type": "C"},
        {"template_id": 2, "section_id": 6, "name": "Formation",          "order": 2, "section_type": "P"},
        {"template_id": 2, "section_id": 7, "name": "Module / Enseignant","order": 3, "section_type": "ME"},
        {"template_id": 2, "section_id": 8, "name": "Recommandation",     "order": 4, "section_type": "R"},

        # ── Template 3 : Évaluation_Pédagogique (modules uniquement) ─────
        {"template_id": 3, "section_id": 9,  "name": "Module / Enseignant","order": 1, "section_type": "ME"},
        {"template_id": 3, "section_id": 10, "name": "Recommandation",     "order": 2, "section_type": "R"},
    ]
    for data in sections_data:
        session.merge(Section(**data))
    session.commit()


def seed_questions(session: Session):
    """Remplit la table questions."""
    questions_data = [
        (
            1,
            "QCU_Satisfaction",
            "FR_EN",
            "Dans l'ensemble, par rapport à votre expérience étudiante à l'EPF sur le campus de [CAMPUS], vous êtes :",
            "Overall, compared to your student experience at EPF on the [CAMPUS] campus, you are:",
            False,
        ),
        (
            1,
            "QCM_Insatisfaction",
            "FR_EN",
            "Votre insatisfaction est liée à un ou plusieurs des éléments suivants :",
            "Your dissatisfaction is related to one or more of the following factors:",
            False,
        ),
        (
            1,
            "Question_ouverte",
            "FR_EN",
            "Expliquez précisément en quoi vous n'êtes pas satisfait de votre expérience étudiante à l'EPF. N'hésitez pas à illustrer votre avis par des exemples et à proposer des pistes d'amélioration.",
            "Explain precisely why you might feel dissatisfied by your student experience at EPF. Don't hesitate to illustrate your opinion with examples and to suggest ways for improvement.",
            False,
        ),
        (
            1,
            "Question_ouverte",
            "FR_EN",
            "Malgré votre réponse précédente, quels éléments positifs pouvez-vous quand même retenir ?",
            "Despite your previous answer, what positive aspects can you still take away from this?",
            True,
        ),
        (
            1,
            "Question_ouverte",
            "FR_EN",
            "Expliquez précisément en quoi vous êtes satisfait de votre expérience étudiante à l'EPF. N'hésitez pas à illustrer votre avis par des exemples.",
            "Explain precisely why you might feel satisfied by your student experience at EPF. Don't hesitate to illustrate your opinion with examples.",
            True,
        ),
        (
            2,
            "QCU_Satisfaction",
            "FR_EN",
            "Dans l'ensemble, par rapport à votre expérience globale de la formation [FORMATION] sur le campus de [CAMPUS], vous êtes :",
            "Overall, compared to your overall experience of the [FORMATION] program on the [CAMPUS] campus, you are:",
            False,
        ),
        (
            2,
            "QCM_Insatisfaction",
            "FR_EN",
            "Votre insatisfaction est liée à un ou plusieurs des éléments suivants :",
            "Your dissatisfaction is related to one or more of the following factors:",
            False,
        ),
        (
            2,
            "Question_ouverte",
            "FR_EN",
            "Expliquez précisément en quoi vous n'êtes pas satisfait de votre expérience étudiante à l'EPF. N'hésitez par exemple à illustrer votre avis par des exemples.",
            "Explain precisely why you might feel dissatisfied by your student experience at EPF. Don't hesitate to illustrate your opinion with examples.",
            False,
        ),
        (
            2,
            "Question_ouverte",
            "FR_EN",
            "Malgré votre réponse précédente, quels éléments positifs pouvez-vous quand même retenir ?",
            "Despite your previous answer, what positive aspects can you still take away from this?",
            True,
        ),
        (
            2,
            "Question_ouverte",
            "FR_EN",
            "Expliquez précisément en quoi vous êtes satisfait de votre expérience étudiante à l'EPF. N'hésitez pas à illustrer votre avis par des exemples.",
            "Explain precisely why you might feel satisfied by your student experience at EPF. Don't hesitate to illustrate your opinion with examples.",
            True,
        ),
        (
            3,
            "QCU_Attendance",
            "FR_EN",
            "Avez-vous suivi ce module ?",
            "Did you take this module?",
            False,
        ),
        (
            3,
            "QCU_Satisfaction",
            "FR_EN",
            "Dans l'ensemble, pour le module [MODULE] avec l'enseignant [ENSEIGNANT], en tenant compte de l'organisation, des ressources et de la pédagogie, vous êtes :",
            "Overall, for the module [MODULE] with the teacher [ENSEIGNANT], taking into account the organization, resources and pedagogy, you are:",
            False,
        ),
        (
            3,
            "QCM_Insatisfaction",
            "FR_EN",
            "Votre insatisfaction est liée à un ou plusieurs des éléments suivants :",
            "Your dissatisfaction is related to one or more of the following factors:",
            False,
        ),
        (
            3,
            "Question_ouverte",
            "FR_EN",
            "Expliquez précisément en quoi vous n'êtes pas satisfait du ou des points choisis ci-dessus. N'hésitez pas à illustrer votre avis par des exemples.",
            "Explain specifically why you are not satisfied with the point(s) chosen above. Please feel free to illustrate your opinion with examples.",
            False,
        ),
        (
            3,
            "Question_ouverte",
            "FR_EN",
            "Malgré votre réponse précédente, quels éléments positifs pouvez-vous quand même retenir ?",
            "Despite your previous answer, what positive aspects can you still take away from this?",
            True,
        ),
        (
            3,
            "Question_ouverte",
            "FR_EN",
            "Expliquez précisément en quoi vous êtes satisfait par l'expérience de ce module avec cet enseignant(e). N'hésitez pas à illustrer votre avis par des exemples.",
            "Explain precisely why you might feel satisfied by your experience in this course with this teacher. Don't hesitate to illustrate your opinion with examples.",
            True,
        ),
        (
            4,
            "NPS",
            "FR_EN",
            "Seriez-vous prêts à recommander la formation à un ami ?",
            "Would you recommend the program to a friend?",
            False,
        ),
    ]

    # ── Template 2 : Sondage_Court ───────────────────────────────────────
    # section_id 5 (C) : 2 questions
    questions_data += [
        (5, "QCU_Satisfaction",  "FR_EN",
         "Comment évaluez-vous votre satisfaction globale vis-à-vis de la vie sur le campus ?",
         "How would you rate your overall satisfaction with campus life?", False),
        (5, "Question_ouverte",  "FR_EN",
         "Avez-vous des suggestions pour améliorer la vie sur le campus ?",
         "Do you have any suggestions to improve campus life?", True),

    # section_id 6 (P) : 2 questions
        (6, "QCU_Satisfaction",  "FR_EN",
         "Comment évaluez-vous votre satisfaction globale vis-à-vis de votre formation ce semestre ?",
         "How would you rate your overall satisfaction with your program this semester?", False),
        (6, "Question_ouverte",  "FR_EN",
         "Qu'est-ce qui vous a le plus marqué dans votre formation ce semestre ? (positif ou négatif)",
         "What stood out the most to you about your program this semester? (positive or negative)", True),

    # section_id 7 (ME) : 3 questions
        (7, "QCU_Attendance",   "FR_EN",
         "Avez-vous suivi ce module ?",
         "Did you attend this module?", False),
        (7, "QCU_Satisfaction", "FR_EN",
         "Comment évaluez-vous ce module et l'enseignant(e) en quelques mots ?",
         "How would you rate this module and the teacher overall?", False),
        (7, "Question_ouverte", "FR_EN",
         "Un commentaire libre sur ce module ou cet(te) enseignant(e) ?",
         "Any free comment about this module or teacher?", True),

    # section_id 8 (R) : 1 question
        (8, "NPS", "FR_EN",
         "Recommanderiez-vous cette formation à un ami ou un collègue ?",
         "Would you recommend this program to a friend or colleague?", False),
    ]

    # ── Template 3 : Évaluation_Pédagogique ──────────────────────────────
    # section_id 9 (ME) : 5 questions
    questions_data += [
        (9, "QCU_Attendance",      "FR_EN",
         "Avez-vous participé à ce module ?",
         "Did you participate in this module?", False),
        (9, "QCU_Satisfaction",    "FR_EN",
         "Dans l'ensemble, êtes-vous satisfait(e) de la qualité pédagogique de ce module ?",
         "Overall, are you satisfied with the teaching quality of this module?", False),
        (9, "QCM_Insatisfaction",  "FR_EN",
         "Si vous n'êtes pas satisfait(e), quels aspects ont posé problème ?",
         "If you are not satisfied, which aspects were problematic?", False),
        (9, "Question_ouverte",    "FR_EN",
         "Quels points forts avez-vous appréciés dans ce module ?",
         "What strengths did you appreciate in this module?", True),
        (9, "Question_ouverte",    "FR_EN",
         "Quelles améliorations suggèreriez-vous pour ce module ?",
         "What improvements would you suggest for this module?", True),

    # section_id 10 (R) : 1 question
        (10, "NPS", "FR_EN",
         "Dans quelle mesure recommanderiez-vous cette formation à quelqu'un de votre entourage ?",
         "To what extent would you recommend this program to someone you know?", False),
    ]

    for question_id, q_data in enumerate(questions_data, start=1):
        question = Question(
            question_id=question_id,
            section_id=q_data[0],
            question_type=q_data[1],
            language=q_data[2],
            text_fr=q_data[3],
            text_en=q_data[4],
            is_optional=q_data[5],
        )
        session.merge(question)
    session.commit()


def seed_options(session: Session):
    """Remplit la table options."""
    options_data = [
        (1, "Totalement satisfait", "Totally satisfied", 1),
        (1, "Très satisfait", "Very satisfied", 1),
        (1, "Plutôt satisfait", "Somewhat satisfied", 1),
        (1, "Plutôt pas satisfait", "Somewhat dissatisfied", 0),
        (1, "Pas du tout satisfait", "Not at all satisfied", 0),
        (1, "Totalement insatisfait", "Totally dissatisfied", 0),
        (2, "La scolarité", "The scolarity service", None),
        (2, "Le service des examens", "The examination service", None),
        (2, "La direction", "The management", None),
        (2, "L'expérience associative", "The associative experience", None),
        (
            2,
            "Les locaux et les moyens à disposition",
            "The buildings and resources available",
            None,
        ),
        (2, "L'ambiance entre les élèves", "The atmosphere among students", None),
        (2, "L'ambiance avec le personnel", "The atmosphere with staff", None),
        (6, "Totalement satisfait", "Totally satisfied", 1),
        (6, "Très satisfait", "Very satisfied", 1),
        (6, "Plutôt satisfait", "Somewhat satisfied", 1),
        (6, "Plutôt pas satisfait", "Somewhat dissatisfied", 0),
        (6, "Pas du tout satisfait", "Not at all satisfied", 0),
        (6, "Totalement insatisfait", "Totally dissatisfied", 0),
        (7, "L'emploi du temps", "Timetable", None),
        (7, "Les examens et évaluations", "Exams and assessments", None),
        (
            7,
            "La disponibilité du Responsable Pédagogique",
            "Availability of the Academic Advisor",
            None,
        ),
        (
            7,
            "L'accompagnement du Responsable Pédagogique",
            "Support from the Academic Advisor",
            None,
        ),
        (11, "Oui", "Yes", 1),
        (11, "Non", "No", 0),
        (12, "Totalement satisfait", "Totally satisfied", 1),
        (12, "Très satisfait", "Very satisfied", 1),
        (12, "Plutôt satisfait", "Somewhat satisfied", 1),
        (12, "Plutôt pas satisfait", "Somewhat dissatisfied", 0),
        (12, "Pas du tout satisfait", "Not at all satisfied", 0),
        (12, "Totalement insatisfait", "Totally dissatisfied", 0),
        (
            13,
            "L'organisation des séances et du module",
            "The organization of the sessions and of the module",
            None,
        ),
        (
            13,
            "Les pré-requis et les objectifs du module",
            "The prerequisites and objectives of the module",
            None,
        ),
        (
            13,
            "Les ressources pédagogiques mises à disposition",
            "The teaching resources made available",
            None,
        ),
        (
            13,
            "Les évaluations associées au module",
            "The assessments associated with the module",
            None,
        ),
        (
            13,
            "L'intérêt du module dans le cursus",
            "The relevance of the module in the program",
            None,
        ),
        (
            13,
            "Les explications et les retours de l'enseignant",
            "The teacher's explanations and feedback",
            None,
        ),
        (
            13,
            "L'implication et la disponibilité de l'enseignant",
            "The teacher's involvement and availability",
            None,
        ),
        (
            13,
            "L'attitude professionnelle et juste de l'enseignant",
            "The teacher's professional and fair attitude",
            None,
        ),
    ]

    SATISFACTION = [
        ("Totalement satisfait",    "Totally satisfied",       1),
        ("Très satisfait",          "Very satisfied",           1),
        ("Plutôt satisfait",        "Somewhat satisfied",       1),
        ("Plutôt pas satisfait",    "Somewhat dissatisfied",    0),
        ("Pas du tout satisfait",   "Not at all satisfied",     0),
        ("Totalement insatisfait",  "Totally dissatisfied",     0),
    ]
    OUI_NON = [("Oui", "Yes", 1), ("Non", "No", 0)]

    # Template 2 — question IDs 18 (QCU_Sat campus), 20 (QCU_Sat formation),
    #              22 (Attendance), 23 (QCU_Sat module)
    for qid in (18, 20, 23):
        for fr, en, pos in SATISFACTION:
            options_data.append((qid, fr, en, pos))
    for fr, en, pos in OUI_NON:
        options_data.append((22, fr, en, pos))

    # Template 3 — question IDs 26 (Attendance), 27 (QCU_Sat), 28 (QCM_Insatisfaction)
    for fr, en, pos in OUI_NON:
        options_data.append((26, fr, en, pos))
    for fr, en, pos in SATISFACTION:
        options_data.append((27, fr, en, pos))
    for fr, en in [
        ("L'organisation des séances",             "The organization of sessions"),
        ("Les objectifs et pré-requis du module",  "The module objectives and prerequisites"),
        ("Les ressources pédagogiques",            "Teaching resources"),
        ("Les méthodes d'évaluation",              "Assessment methods"),
        ("La qualité des explications",            "Quality of explanations"),
        ("La disponibilité de l'enseignant(e)",    "Teacher availability"),
    ]:
        options_data.append((28, fr, en, None))

    for opt_data in options_data:
        option = Option(
            question_id=opt_data[0],
            text_fr=opt_data[1],
            text_en=opt_data[2],
            is_positive=opt_data[3],
        )
        session.merge(option)
    session.commit()


def _normalize_header(value: str) -> str:
    """Normalise un en-tête de colonne CSV pour comparaison robuste.

    Minuscules, accents retirés, espaces → underscores. Permet de retrouver une
    colonne quelle que soit sa casse ou son accentuation ("Numéro" == "numero").
    """
    return (
        (value or "")
        .strip()
        .lower()
        .replace("é", "e")
        .replace("è", "e")
        .replace("ê", "e")
        .replace("à", "a")
        .replace(" ", "_")
    )


def _get_csv_value(row: dict, *possible_names: str) -> str:
    """Récupère une valeur de ligne CSV en tolérant les variantes d'en-tête.

    Essaie plusieurs noms de colonne possibles (après normalisation) et renvoie
    la première valeur trouvée, ou "" si aucune ne correspond.
    """
    # Réindexer la ligne avec des clés normalisées
    normalized_row = {_normalize_header(key): value for key, value in row.items()}

    # Tester chaque nom candidat jusqu'à en trouver un présent
    for name in possible_names:
        key = _normalize_header(name)
        if key in normalized_row:
            return (normalized_row[key] or "").strip()

    return ""


def seed_programs(session: Session):
    """Remplit la table programs depuis import/Program_list.csv."""

    # Clean table first
    session.exec(delete(Program))

    csv_path = Path("import/Program_list.csv")

    if not csv_path.exists():
        logger.warning("[SEED] import/Program_list.csv introuvable.")
        return

    inserted = 0

    with csv_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        sample = csv_file.read(2048)
        csv_file.seek(0)

        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=";,")
        except csv.Error:
            dialect = csv.excel
            dialect.delimiter = ";"

        reader = csv.reader(csv_file, dialect=dialect)

        for row in reader:
            if len(row) < 3:
                continue

            code = (row[0] or "").strip().upper()
            name = (row[1] or "").strip()
            campus = (row[2] or "").strip()

            if not code or not name or not campus:
                continue

            program = Program(
                code=code,
                name=name,
                campus=campus,
            )

            session.merge(program)
            inserted += 1

    session.commit()
    logger.debug(
        f"[SEED] {inserted} programme(s) inséré(s)/mis à jour depuis Liste_Formations.csv."
    )


def seed_surveys(session: Session):
    """Remplit la table surveys."""
    for survey_data in SEEDED_SURVEYS:
        program = session.get(Program, survey_data["program"])
        if program is None or program.campus != survey_data["campus"]:
            raise ValueError(
                "Formation de seed absente ou campus incohérent : "
                f"{survey_data['program']} / {survey_data['campus']}"
            )

        survey = Survey(
            template_id=1,
            survey_id=survey_data["survey_id"],
            program=survey_data["program"],
            semester="Automne",
            status=1,
            school_year="2026-2027",
            password=None,
        )
        session.merge(survey)
    session.commit()


def seed_modules(session: Session):
    """Remplit la table modules.

    Chaque tuple : (module_id, name, teacher, ue, <inutilisé, ancien flag UE
    optionnelle>, one_teacher_in_list, template_id, <inutilisé>).
    """
    modules_data = [
        (
            1,
            "Introduction to Cloud",
            "Théo B.",
            "UE1 – Software as a Service",
            0,
            0,
            1,
            1,
        ),
        (
            2,
            "Coding Agents Management",
            "Xavier C.",
            "UE1 – Software as a Service",
            0,
            0,
            1,
            1,
        ),
        (
            3,
            "Complex Web Services",
            "Xavier C.",
            "UE1 – Software as a Service",
            0,
            0,
            1,
            1,
        ),
        (
            4,
            "Machine Learning and Deep Learning",
            "Thalita D.",
            "UE2 – Machine Learning Theory & Practice",
            0,
            0,
            1,
            1,
        ),
        (
            5,
            "Natural Language Processing",
            "Maksim K.",
            "UE2 – Machine Learning Theory & Practice",
            0,
            0,
            1,
            1,
        ),
        (
            6,
            "GenAI : Applied Large Language Models",
            "Enzo F.",
            "UE2 – Machine Learning Theory & Practice",
            0,
            0,
            1,
            1,
        ),
        (
            7,
            "Data Governance and Data Quality Management",
            "Cédrine M., Daniel B.",
            "UE3 – Data Strategy",
            0,
            0,
            1,
            1,
        ),
        (
            8,
            "Cybersecurity and Data Protection",
            "Florian L.",
            "UE3 – Data Strategy",
            0,
            0,
            1,
            1,
        ),
        (
            9,
            "Analytics & Experimentation",
            "Issame B.",
            "UE3 – Data Strategy",
            0,
            0,
            1,
            1,
        ),
        (
            10,
            "Data and Ethics",
            "Ikram C.",
            "UE4 – Responsible Data Science",
            0,
            0,
            1,
            1,
        ),
        (
            11,
            "Data Law",
            "Joey B. F., Robert R., Hannah G.",
            "UE4 – Responsible Data Science",
            0,
            0,
            1,
            1,
        ),
        (
            12,
            "Socio-Ecological impact of IT",
            "Sonia T., Sylvie M.",
            "UE4 – Responsible Data Science",
            0,
            0,
            1,
            1,
        ),
        (
            13,
            "Unmodelable Reality",
            "Valentin B.",
            "UE4 – Responsible Data Science",
            0,
            0,
            1,
            1,
        ),
        (
            14,
            "Time Series Analysis",
            "Abdoul Salam D.",
            "UE5A – Advanced Machine Learning",
            0,
            0,
            1,
            1,
        ),
        (
            15,
            "From Poc to Prod",
            "Guillaume D.",
            "UE5A – Advanced Machine Learning",
            0,
            0,
            1,
            1,
        ),
        (
            16,
            "Data Mining and Machine Learning on Graphs",
            "Domenico M.",
            "UE5A – Advanced Machine Learning",
            0,
            0,
            1,
            1,
        ),
        (
            17,
            "Remote Sensing and Computer Vision with Machine Learning",
            "Abelle C., Antoine G.",
            "UE5A – Advanced Machine Learning",
            0,
            0,
            1,
            1,
        ),
        (
            18,
            "Semester's project (Agile Coach)",
            "Olivier D., Luigi N.",
            "UE6A – Major’s Project S9",
            0,
            1,
            1,
            1,
        ),
        (
            19,
            "Semester's project (Engineering Coach)",
            "Thalita D., Xavier C.",
            "UE6A – Major’s Project S9",
            0,
            1,
            1,
            1,
        ),
        (
            20,
            "Professionalization",
            "Louis G.",
            "UE6A – Major’s Project S9",
            0,
            0,
            1,
            1,
        ),
    ]

    for survey_data in SEEDED_SURVEYS:
        module_offset = (survey_data["survey_id"] - 1) * len(modules_data)
        for m_data in modules_data:
            module = Module(
                module_id=m_data[0] + module_offset,
                name=m_data[1],
                teacher=m_data[2],
                ue=m_data[3],
                one_teacher_in_list=bool(m_data[5]),
                template_id=m_data[6],
                survey_id=survey_data["survey_id"],
            )
            session.merge(module)
    session.commit()


def seed_respondents(session: Session):
    """Remplit la table respondents."""

    for survey_data in SEEDED_SURVEYS:
        for _submission_id, user_id, created_at in SEEDED_SUBMISSIONS:
            respondent = Respondent(
                survey_id=survey_data["survey_id"],
                user_id=user_id,
                submission_date=created_at,
            )
            session.merge(respondent)
    session.commit()


def seed_submissions(session: Session):
    """Remplit la table submissions."""

    submissions_per_survey = len(SEEDED_SUBMISSIONS)
    for survey_data in SEEDED_SURVEYS:
        submission_offset = (
            survey_data["survey_id"] - 1
        ) * submissions_per_survey
        for submission_id, _user_id, created_at in SEEDED_SUBMISSIONS:
            submission = Submission(
                survey_id=survey_data["survey_id"],
                submission_id=submission_id + submission_offset,
                created_at=created_at,
            )
            session.merge(submission)
    session.commit()


STAT_COLOR_THRESHOLDS = {
    "campus_satisfaction": {"color_scale":{20: "red", 50: "orange", 100: "green"},"section_type":"C", "short":"C","label":"Satisfaction campus","suffix":"%","show_explicit_positive":False},
    "program_satisfaction": {"color_scale":{20: "red", 50: "orange", 100: "green"},"section_type":"P", "short":"F","label":"Satisfaction formation","suffix":"%","show_explicit_positive":False},
    "recommendation_score": {"color_scale":{-33: "red", 33: "orange", 100: "green"},"section_type":"R", "short":"NPS","label":"Score de recommandation","suffix":"","show_explicit_positive":True},
}

def seed_stats(session: Session):
    """Remplit la table stats."""

    for stat in STAT_COLOR_THRESHOLDS:
        stats = Stat(
            name=stat,
            color_scale=json.dumps(STAT_COLOR_THRESHOLDS[stat]["color_scale"]),
            section_type=STAT_COLOR_THRESHOLDS[stat]["section_type"],
            short=STAT_COLOR_THRESHOLDS[stat]["short"],
            label=STAT_COLOR_THRESHOLDS[stat]["label"],
            suffix=STAT_COLOR_THRESHOLDS[stat]["suffix"],

            show_explicit_positive=STAT_COLOR_THRESHOLDS[stat]["show_explicit_positive"],
        )
        session.add(stats)
    session.commit()


def seed_answers(session: Session):
    """Remplit la table answers."""

    for survey_data in SEEDED_SURVEYS:
        csv_path = Path("import") / survey_data["answers_file"]

        if not csv_path.exists():
            logger.warning(f"[SEED] {csv_path} introuvable.")
            continue

        with csv_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.reader(csv_file, delimiter=";")
            next(reader, None)  # skip the headers
            for r_data in reader:
                answer = Answer(
                    submission_id=int(r_data[0]),
                    question_id=int(r_data[1]),
                    module_id=int(r_data[2]) if r_data[2] else None,
                    teacher=r_data[3] or None,
                    option_id=int(r_data[4]) if r_data[4] else None,
                    value=r_data[5] or None,
                )

                session.add(answer)

    session.commit()

DEFAULT_PROVIDER_NAME = "Ollama EPF"


def seed_llm_providers(session: Session):
    """Crée le fournisseur LLM historique s'il n'existe pas.

    Relançable sans doublon : la présence est testée sur `name`, qui sert de
    clé fonctionnelle. Aucune clé d'API n'est écrite ici, uniquement le nom de
    la variable d'environnement qui la porte.
    """

    existing = session.exec(
        select(LLMProvider).where(LLMProvider.name == DEFAULT_PROVIDER_NAME)
    ).first()
    if existing:
        return

    session.add(
        LLMProvider(
            name=DEFAULT_PROVIDER_NAME,
            api_type="ollama",
            base_url="https://locallm.mde.epf.fr/ollama",
            api_key_env="LLM_API_KEY",
            default_model="gemma4:26b",
            is_active=True,
        )
    )
    session.commit()


# Tarifs de départ, en dollars par million de tokens (entrée, sortie).
#
# Seuls des tarifs vérifiables sont pré-remplis : les modèles Anthropic (grille
# publique) et le serveur Ollama de l'école, gratuit à l'appel puisque
# auto-hébergé. Les autres fournisseurs (OpenAI, Mistral, Groq…) sont laissés
# à saisir dans `/backend/llm/prices` : inventer un tarif afficherait un
# montant faux avec l'autorité d'un montant réel.
#
# `provider_id` reste NULL : ces tarifs valent pour le nom de modèle quel que
# soit l'endpoint qui le sert.
DEFAULT_MODEL_PRICES = (
    ("claude-opus-5", 5.00, 25.00, "Grille publique Anthropic"),
    ("claude-sonnet-5", 3.00, 15.00, "Grille publique Anthropic"),
    ("claude-haiku-4-5", 1.00, 5.00, "Grille publique Anthropic"),
    ("gemma4:26b", 0.00, 0.00, "Ollama auto-hébergé (EPF) : pas de coût à l'appel"),
)


def seed_model_prices(session: Session):
    """Insère les tarifs connus, sans écraser ceux déjà saisis.

    Relançable : la présence est testée sur le couple (modèle, fournisseur
    générique). Un tarif corrigé à la main en administration n'est donc jamais
    réécrit au redémarrage suivant.
    """
    for model, price_in, price_out, note in DEFAULT_MODEL_PRICES:
        existing = session.exec(
            select(LLMModelPrice).where(
                LLMModelPrice.model == model,
                LLMModelPrice.provider_id.is_(None),
            )
        ).first()
        if existing:
            continue

        session.add(
            LLMModelPrice(
                model=model,
                provider_id=None,
                input_price_per_mtok=price_in,
                output_price_per_mtok=price_out,
                note=note,
            )
        )

    session.commit()


def seed_prompts(session: Session):
    """Remplit la table prompts."""

    prompt = Prompt(
        description="Phrases représentatives (positives et négatives) avec Gemma4",
        model="gemma4:26b",
        prompt_text="""
Tu trouveras ci-dessous une une liste de réponses à une question de satisfaction.
1/ Regroupe les phrases positives et les phrases négatives en deux catégories sous forme de liste à puce avec une phrase par ligne). En cas de doublon, ne met qu'une seule ligne et rajoute le nombre d’occurrences entre parenthèse. Si une catégorie est vide ne l'affiche pas.
2/ Si il y a plus de trois phrases dans la catégorie, affiche les trois phrases les plus représentatives de la catégories. Si une catégorie est vide ne l'affiche pas.
3/ Ordonne les phrases de la plus pertinente à la moins pertinente.  Si une catégorie est vide ne l'affiche pas.
CONSERVES TOUJOURS LES VERBATIMS DES REPONSES.

Réponses : ```{ANSWERS}```
"""
    )
    session.merge(
        prompt
    )  # Utilisation de merge pour éviter les erreurs si l'ID existe déjà
    session.commit()


def seed_all_if_necessary():
    """Point d'entrée du seed, appelé au démarrage de l'application.

    Toujours exécuté : synchro des filières et du fournisseur LLM par défaut
    (idempotents). Le jeu de données de démo n'est inséré que si la base est
    vide (test: présence d'au moins un utilisateur).
    """
    with Session(engine) as session:
        # Toujours synchroniser les programmes depuis le CSV
        seed_programs(session)

        # Toujours garantir la présence du fournisseur LLM par défaut : les
        # bases déjà déployées doivent l'obtenir sans repasser par un seed
        # complet. La fonction est idempotente.
        seed_llm_providers(session)

        # Idem pour la grille tarifaire : les bases déjà déployées doivent
        # obtenir les tarifs connus sans repasser par un seed complet.
        seed_model_prices(session)

        # Seeder le reste uniquement si la base est vide
        if session.query(User).first():
            return

        seed_users(session)
        seed_roles(session)

        seed_templates(session)
        seed_sections(session)
        seed_questions(session)
        seed_options(session)

        seed_surveys(session)
        seed_modules(session)
        seed_respondents(session)
        seed_submissions(session)

        seed_answers(session)

        seed_prompts(session)

        seed_stats(session)

        logger.debug("Database seeding completed successfully!")
