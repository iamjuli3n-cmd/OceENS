from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sqlmodel import Session, select

from core.database import engine
from models import Answer, Module, Option, Program, Question, Section, Submission, Survey


def clean_mojibake(text: Any) -> str:
    """Repair the most common UTF-8-as-Latin-1 decoding error."""
    if not isinstance(text, str):
        return str(text) if text is not None else ""
    try:
        return text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


@dataclass
class OptionData:
    option_id: int
    text_fr: str
    text_en: str
    is_positive: Optional[bool]


@dataclass
class AnswerData:
    answer_id: int
    value: str
    submission_id: Optional[int] = None
    module_id: Optional[int] = None
    option_id: Optional[int] = None
    option_text_fr: str = ""
    option_text_en: str = ""
    is_positive: Optional[bool] = None
    ue: str = ""
    module: str = ""
    teacher: str = ""


@dataclass
class QuestionData:
    question_id: int
    text_fr: str
    text_en: str
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
    teacher: str


@dataclass
class FullSurvey:
    template_id: int
    survey_id: int
    campus: str
    program: str
    semester: str
    school_year: str
    modules: List[ModuleData] = field(default_factory=list)
    sections: List[SectionData] = field(default_factory=list)

    def to_flat_dataframe_records(self) -> List[Dict[str, Any]]:
        records: List[Dict[str, Any]] = []
        for section in self.sections:
            for question in section.questions:
                for answer in question.reponses:
                    records.append(
                        {
                            "campus": self.campus,
                            "program": self.program,
                            "school_year": self.school_year,
                            "semester": self.semester,
                            "ue": answer.ue,
                            "module": answer.module,
                            "teacher": answer.teacher,
                            "section": section.nom,
                            "category": question.category,
                            "question_type": question.question_type,
                            "question_id": question.question_id,
                            "question_text_fr": question.text_fr,
                            "question_text_en": question.text_en,
                            "option_id": answer.option_id,
                            "option_text_fr": answer.option_text_fr,
                            "option_text_en": answer.option_text_en,
                            "is_positive": answer.is_positive,
                            "submission_id": answer.submission_id,
                            "answer_value": answer.value,
                        }
                    )
        return records


def load_sondage_complet(survey_id: int) -> FullSurvey:
    """Load one survey using the post-migration schema with globally unique IDs."""
    with Session(engine) as session:
        survey_row = session.exec(
            select(Survey).where(Survey.survey_id == survey_id)
        ).first()
        if not survey_row:
            raise ValueError(f"Sondage introuvable (sondage : {survey_id})")

        program_row = session.exec(
            select(Program).where(Program.code == survey_row.program)
        ).first()

        survey = FullSurvey(
            template_id=survey_row.template_id,
            survey_id=survey_row.survey_id,
            campus=clean_mojibake(program_row.campus if program_row else ""),
            program=clean_mojibake(survey_row.program),
            semester=clean_mojibake(survey_row.semester),
            school_year=clean_mojibake(survey_row.school_year),
        )

        modules_rows = session.exec(
            select(Module)
            .where(Module.survey_id == survey_id)
            .order_by(Module.ue, Module.name)
        ).all()
        for row in modules_rows:
            survey.modules.append(
                ModuleData(
                    module_id=row.module_id,
                    nom=clean_mojibake(row.name),
                    ue=clean_mojibake(row.ue),
                    teacher=clean_mojibake(row.teacher),
                )
            )

        sections_rows = session.exec(
            select(Section)
            .where(Section.template_id == survey.template_id)
            .order_by(Section.order)
        ).all()
        sections_by_id: Dict[int, SectionData] = {}
        for row in sections_rows:
            section = SectionData(
                section_id=row.section_id,
                nom=clean_mojibake(row.name),
                order=row.order,
            )
            sections_by_id[section.section_id] = section
            survey.sections.append(section)

        questions_rows = session.exec(
            select(Question)
            .join(Section, Section.section_id == Question.section_id)
            .where(Section.template_id == survey.template_id)
            .order_by(Section.order, Question.question_id)
        ).all()
        questions_by_id: Dict[int, QuestionData] = {}
        for row in questions_rows:
            section = sections_by_id.get(row.section_id)
            if not section:
                continue
            question = QuestionData(
                question_id=row.question_id,
                text_fr=clean_mojibake(row.text_fr),
                text_en=clean_mojibake(row.text_en),
                category=section.nom,
                question_type=clean_mojibake(row.question_type),
            )
            questions_by_id[question.question_id] = question
            section.questions.append(question)

        options_rows = session.exec(
            select(Option)
            .join(Question, Question.question_id == Option.question_id)
            .join(Section, Section.section_id == Question.section_id)
            .where(Section.template_id == survey.template_id)
            .order_by(Option.option_id)
        ).all()
        for row in options_rows:
            question = questions_by_id.get(row.question_id)
            if question:
                question.options.append(
                    OptionData(
                        option_id=row.option_id,
                        text_fr=clean_mojibake(row.text_fr),
                        text_en=clean_mojibake(row.text_en),
                        is_positive=(
                            None if row.is_positive is None else bool(row.is_positive)
                        ),
                    )
                )

        answer_rows = session.exec(
            select(
                Answer.answer_id,
                Answer.value,
                Answer.submission_id,
                Answer.question_id,
                Answer.module_id,
                Answer.option_id,
                Answer.teacher.label("answer_teacher"),
                Module.name.label("module_name"),
                Module.ue.label("module_ue"),
                Module.teacher.label("module_teacher"),
                Option.text_fr.label("option_text_fr"),
                Option.text_en.label("option_text_en"),
                Option.is_positive,
            )
            .join(Submission, Submission.submission_id == Answer.submission_id)
            .join(Module, Module.module_id == Answer.module_id, isouter=True)
            .join(Option, Option.option_id == Answer.option_id, isouter=True)
            .where(Submission.survey_id == survey_id)
            .order_by(Answer.answer_id)
        ).all()

        for row in answer_rows:
            question = questions_by_id.get(row.question_id)
            if not question:
                continue
            option_text_fr = clean_mojibake(row.option_text_fr)
            option_text_en = clean_mojibake(row.option_text_en)
            question.reponses.append(
                AnswerData(
                    answer_id=row.answer_id,
                    value=option_text_fr or clean_mojibake(row.value),
                    submission_id=row.submission_id,
                    module_id=row.module_id,
                    option_id=row.option_id,
                    option_text_fr=option_text_fr,
                    option_text_en=option_text_en,
                    is_positive=(
                        None if row.is_positive is None else bool(row.is_positive)
                    ),
                    ue=clean_mojibake(row.module_ue),
                    module=clean_mojibake(row.module_name),
                    teacher=clean_mojibake(
                        row.answer_teacher or row.module_teacher or ""
                    ),
                )
            )

        return survey
