from typing import Optional

from sqlalchemy import Column, ForeignKey, Integer, String, Text
from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    __tablename__ = "users"

    user_id: Optional[int] = Field(
        default=None, sa_column=Column("user_id", Integer, primary_key=True)
    )
    mail: Optional[str] = Field(default=None, sa_column=Column("mail", String))
    role: Optional[str] = Field(default=None, sa_column=Column("role", String))


class Template(SQLModel, table=True):
    __tablename__ = "templates"

    template_id: Optional[int] = Field(
        default=None, sa_column=Column("template_id", Integer, primary_key=True)
    )
    name: Optional[str] = Field(default=None, sa_column=Column("name", String))
    user_id: Optional[int] = Field(
        default=None, sa_column=Column("user_id", Integer, ForeignKey("users.user_id"))
    )


class Survey(SQLModel, table=True):
    __tablename__ = "surveys"

    template_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            "template_id",
            Integer,
            ForeignKey("templates.template_id"),
            primary_key=True,
        ),
    )
    survey_id: Optional[int] = Field(
        default=None, sa_column=Column("survey_id", Integer, primary_key=True)
    )
    campus: Optional[str] = Field(default=None, sa_column=Column("campus", String))
    program: Optional[str] = Field(default=None, sa_column=Column("program", String))
    semester: Optional[str] = Field(default=None, sa_column=Column("semester", String))
    status: Optional[int] = Field(default=None, sa_column=Column("status", Integer))
    school_year: Optional[str] = Field(
        default=None, sa_column=Column("school_year", String)
    )
    password: Optional[str] = Field(default=None, sa_column=Column("password", String))


class Section(SQLModel, table=True):
    __tablename__ = "sections"

    template_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            "template_id",
            Integer,
            ForeignKey("templates.template_id"),
            primary_key=True,
        ),
    )
    section_id: Optional[int] = Field(
        default=None, sa_column=Column("section_id", Integer, primary_key=True)
    )
    name: Optional[str] = Field(default=None, sa_column=Column("name", String))
    order: Optional[int] = Field(default=None, sa_column=Column("order", Integer))
    section_type: Optional[str] = Field(
        default=None, sa_column=Column("section_type", String)
    )


class Question(SQLModel, table=True):
    __tablename__ = "questions"

    template_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            "template_id",
            Integer,
            ForeignKey("templates.template_id"),
            primary_key=True,
        ),
    )
    section_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            "section_id", Integer, ForeignKey("sections.section_id"), primary_key=True
        ),
    )
    question_id: Optional[int] = Field(
        default=None, sa_column=Column("question_id", Integer, primary_key=True)
    )
    category: Optional[str] = Field(default=None, sa_column=Column("category", String))
    question_type: Optional[str] = Field(
        default=None, sa_column=Column("question_type", String)
    )
    language: Optional[str] = Field(default=None, sa_column=Column("language", String))
    text: Optional[str] = Field(default=None, sa_column=Column("text", Text))


class Option(SQLModel, table=True):
    __tablename__ = "options"

    template_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            "template_id",
            Integer,
            ForeignKey("templates.template_id"),
            primary_key=True,
        ),
    )
    section_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            "section_id", Integer, ForeignKey("sections.section_id"), primary_key=True
        ),
    )
    question_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            "question_id",
            Integer,
            ForeignKey("questions.question_id"),
            primary_key=True,
        ),
    )
    option_id: Optional[int] = Field(
        default=None, sa_column=Column("option_id", Integer, primary_key=True)
    )
    text: Optional[str] = Field(default=None, sa_column=Column("text", Text))


class Module(SQLModel, table=True):
    __tablename__ = "modules"

    module_id: Optional[int] = Field(
        default=None, sa_column=Column("module_id", Integer, primary_key=True)
    )
    name: Optional[str] = Field(default=None, sa_column=Column("name", String))
    teacher: Optional[str] = Field(default=None, sa_column=Column("teacher", String))
    ue: Optional[str] = Field(default=None, sa_column=Column("ue", String))
    is_optional: Optional[bool] = Field(
        default=False, sa_column=Column("is_optional", Integer)
    )
    one_teacher_in_list: Optional[bool] = Field(
        default=False, sa_column=Column("one_teacher_in_list", Integer)
    )
    template_id: Optional[int] = Field(
        default=None,
        sa_column=Column("template_id", Integer, ForeignKey("templates.template_id")),
    )
    survey_id: Optional[int] = Field(
        default=None,
        sa_column=Column("survey_id", Integer, ForeignKey("surveys.survey_id")),
    )


class Answer(SQLModel, table=True):
    __tablename__ = "answers"

    template_id: Optional[int] = Field(
        default=None,
        sa_column=Column("template_id", Integer, ForeignKey("surveys.template_id")),
    )
    survey_id: Optional[int] = Field(
        default=None,
        sa_column=Column("survey_id", Integer, ForeignKey("surveys.survey_id")),
    )

    section_id: Optional[int] = Field(
        default=None,
        sa_column=Column("section_id", Integer, ForeignKey("questions.section_id")),
    )
    question_id: Optional[int] = Field(
        default=None,
        sa_column=Column("question_id", Integer, ForeignKey("questions.question_id")),
    )
    answer_id: Optional[int] = Field(
        default=None,
        sa_column=Column("answer_id", Integer, primary_key=True, autoincrement=True),
    )

    submission_id: Optional[str] = Field(
        default=None,
        sa_column=Column("submission_id", Integer, nullable=False),
    )
    value: Optional[str] = Field(default=None, sa_column=Column("value", Text))
    module_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            "module_id",
            Integer,
            ForeignKey("modules.module_id"),
            nullable=True,
        ),
    )

    teacher: Optional[str] = Field(
        default=None,
        sa_column=Column("teacher", String, nullable=True),
    )


class Respondent(SQLModel, table=True):
    __tablename__ = "respondents"

    template_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            "template_id", Integer, ForeignKey("surveys.template_id"), primary_key=True
        ),
    )
    survey_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            "survey_id", Integer, ForeignKey("surveys.survey_id"), primary_key=True
        ),
    )
    user_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            "user_id", Integer, ForeignKey("users.user_id"), primary_key=True
        ),
    )
    submission_date: Optional[str] = Field(
        default=None, sa_column=Column("submission_date", String)
    )
    has_answered: Optional[bool] = Field(
        default=False, sa_column=Column("has_answered", Integer)
    )
