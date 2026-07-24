"""Schemas Pydantic des corps de requete."""

import json

from typing import List, Optional
from pydantic import BaseModel


class SurveyCreate(BaseModel):
    template_id: int
    campus: str
    program: str
    semester: str
    school_year: str
    user_id: Optional[int] = 1


class ModuleCreate(BaseModel):
    id: int
    name: str
    one_teacher_in_list: bool = False
    teachers: List[str]


class UECreate(BaseModel):
    id: int
    name: str
    modules: List[ModuleCreate]


class SurveyFullCreate(BaseModel):
    template_id: int
    campus: str
    program: str
    semester: str
    school_year: str
    ues: List[UECreate]
    students: List[str]


class AnswerItem(BaseModel):
    section_id: int
    question_id: int
    value: str
    option_id: Optional[int] = None
    module_id: Optional[int] = None
    teacher: Optional[str] = None


class SurveySubmission(BaseModel):
    answers: List[AnswerItem]


class RoleUpdate(BaseModel):
    roles: List[str]


class SurveyStudentsAdd(BaseModel):
    emails: List[str]

class SummaryRequest(BaseModel):
    prompt_id: int




import json

# └────────────────────────────────────────────────────────────────────────┘

# ┌─ Fonction utilitaire : Vérification des rôles autorisés ────────────────────┐
