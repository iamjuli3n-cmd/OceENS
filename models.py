from typing import Optional

from sqlalchemy import Column, ForeignKey, Integer, String, Text
from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    __tablename__ = "users"

    user_id: Optional[int] = Field(
        default=None, sa_column=Column("user_id", Integer, primary_key=True)
    )
    mail: Optional[str] = Field(default=None, sa_column=Column("mail", String))


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

    survey_id: Optional[int] = Field(
        default=None, sa_column=Column("survey_id", Integer, primary_key=True)
    )

    template_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            "template_id",
            Integer,
            ForeignKey("templates.template_id"),
        ),
    )

    program: Optional[str] = Field(
        default=None,
        sa_column=Column(
            "program",
            String,
            ForeignKey("programs.code"),
            nullable=True,
        ),
    )

    semester: Optional[str] = Field(default=None, sa_column=Column("semester", String))
    # 1 : Active / 0 : Closed
    status: Optional[int] = Field(default=None, sa_column=Column("status", Integer))
    school_year: Optional[str] = Field(
        default=None, sa_column=Column("school_year", String)
    )
    password: Optional[str] = Field(default=None, sa_column=Column("password", String))


class Section(SQLModel, table=True):
    __tablename__ = "sections"

    section_id: Optional[int] = Field(
        default=None, sa_column=Column("section_id", Integer, primary_key=True)
    )

    template_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            "template_id",
            Integer,
            ForeignKey("templates.template_id"),
        ),
    )

    name: Optional[str] = Field(default=None, sa_column=Column("name", String))
    order: Optional[int] = Field(default=None, sa_column=Column("order", Integer))
    section_type: Optional[str] = Field(
        default=None, sa_column=Column("section_type", String)
    )


class Question(SQLModel, table=True):
    __tablename__ = "questions"

    
    section_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            "section_id", Integer, ForeignKey("sections.section_id")
        ),
    )
    question_id: Optional[int] = Field(
        default=None, sa_column=Column("question_id", Integer, primary_key=True)
    )
    question_type: Optional[str] = Field(
        default=None, sa_column=Column("question_type", String)
    )
    language: Optional[str] = Field(default=None, sa_column=Column("language", String))
    text_fr: Optional[str] = Field(default=None, sa_column=Column("text_fr", Text))
    text_en: Optional[str] = Field(default=None, sa_column=Column("text_en", Text))


class Option(SQLModel, table=True):
    __tablename__ = "options"

    question_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            "question_id",
            Integer,
            ForeignKey("questions.question_id"),
        ),
    )
    option_id: Optional[int] = Field(
        default=None, sa_column=Column("option_id", Integer, primary_key=True)
    )
    text_fr: Optional[str] = Field(default=None, sa_column=Column("text_fr", Text))
    text_en: Optional[str] = Field(default=None, sa_column=Column("text_en", Text))
    is_positive: Optional[int] = Field(
        default=None, sa_column=Column("is_positive", Integer)
    )


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
    survey_id: Optional[int] = Field(
        default=None,
        sa_column=Column("survey_id", Integer, ForeignKey("surveys.survey_id")),
    )


class Answer(SQLModel, table=True):
    __tablename__ = "answers"

    answer_id: Optional[int] = Field(
        default=None,
        sa_column=Column("answer_id", Integer, primary_key=True, autoincrement=True),
    )

    submission_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            "submission_id",
            Integer,
            ForeignKey("submissions.submission_id"),
            nullable=False,
        ),
    )

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

    question_id: Optional[int] = Field(
        default=None,
        sa_column=Column("question_id", Integer, ForeignKey("questions.question_id")),
    )

    option_id: Optional[int] = Field(
        default=None,
        sa_column=Column("option_id", Integer, ForeignKey("options.option_id")),
    )

    value: Optional[str] = Field(default=None, sa_column=Column("value", Text))


class Respondent(SQLModel, table=True):
    __tablename__ = "respondents"

    # Composite Primary Key (survey_id,user_id)

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

    # If submission_date is NULL --> Not yet answered
    submission_date: Optional[str] = Field(
        default=None, sa_column=Column("submission_date", String)
    )


class Submission(SQLModel, table=True):
    __tablename__ = "submissions"

    submission_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            "submission_id",
            Integer,
            primary_key=True,
            autoincrement=True,
        ),
    )

    survey_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            "survey_id",
            Integer,
            ForeignKey("surveys.survey_id"),
            nullable=False,
        ),
    )

    created_at: Optional[str] = Field(
        default=None,
        sa_column=Column("created_at", String),
    )


class Program(SQLModel, table=True):
    __tablename__ = "programs"

    code: str = Field(sa_column=Column("code", String, primary_key=True))

    name: str = Field(sa_column=Column("name", String, nullable=False))

    campus: str = Field(sa_column=Column("campus", String, nullable=False))

class Role(SQLModel, table=True):
    __tablename__ = "roles"

    # Composite primary key (user_id,role,program_code)

    user_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            "user_id", Integer, ForeignKey("users.user_id"), primary_key=True
        ),
    )

    role: str = Field(sa_column=Column("name", String, primary_key=True))

class Prompt(SQLModel, table=True):
    __tablename__ = "prompts"

    prompt_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            "prompt_id",
            Integer,
            primary_key=True,
            autoincrement=True,
        ),
    )

    description: Optional[str] = Field(sa_column=Column("description", String))

    model: Optional[str] = Field(sa_column=Column("model", String))

    prompt_text: Optional[str] = Field(sa_column=Column("prompt_text", Text))

class Summary(SQLModel, table=True):
    __tablename__ = "summaries"

    summary_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            "summary_id",
            Integer,
            primary_key=True,
            autoincrement=True,
        ),
    )

    survey_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            "survey_id",
            Integer,
            ForeignKey("surveys.survey_id"),
            nullable=False,
        ),
    )

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
        sa_column=Column("teacher", String, ForeignKey("modules.teacher"), nullable=True),
    )

    question_id: Optional[int] = Field(
        default=None,
        sa_column=Column("question_id", Integer, ForeignKey("questions.question_id")),
    )

    prompt_id: Optional[int] = Field(
        default=None,
        sa_column=Column("prompt_id", Integer, ForeignKey("prompts.prompt_id")),
    )

    http_status: Optional[int] = Field(
        default=None, sa_column=Column("http_status", Integer)
    )

    summary_text: Optional[str] = Field(sa_column=Column("summary_text", Text))

    metadata_text: Optional[str] = Field(sa_column=Column("metadata_text", Text))



