import pandas as pd
import sys
import re
from database import engine
from sqlmodel import Session, select, func
from models import  Survey, Submission, Answer, Option,Module,Program

def process_section(session,df,column_name, initial_question_id, module_id=None, teacher=None, rowsMask=None):
    if rowsMask is not None:
        df=df[rowsMask]
    loc = df.columns.get_loc(column_name)
    question_id=initial_question_id

    # Process answers
    for index,answer_row in df[column_name].items():
        text_fr=answer_row.split("/")[0].strip()
        
        option_id = session.exec(select(Option.option_id).where(Option.question_id==question_id,Option.text_fr==text_fr)).first()
        answer=Answer(
            submission_id=submission_ids[index],
            question_id=question_id,
            option_id=option_id,
            module_id=module_id,
            teacher=teacher.title(), # Capitalize first letter of each word
        )
        session.add(answer)
        session.flush()
        
    # Process Insatisfaction (next question)
    question_id=initial_question_id+1
    for index,answer_row in df[df.columns[loc+1]].items():
        if pd.isna(answer_row):
            continue
        for choice in answer_row.split(";"): # Multiple choice question
            if len(choice)==0:
                continue
            text_fr=choice.split("/")[0].strip()
            
            option_id = session.exec(select(Option.option_id).where(Option.question_id==question_id,Option.text_fr==text_fr)).first()
            if option_id is None:
                continue
            answer=Answer(
                submission_id=submission_ids[index],
                question_id=question_id,
                option_id=option_id,
                module_id=module_id,
                teacher=teacher.title(), # Capitalize first letter of each word
            )
            session.add(answer)
            session.flush()
    
    # Process Insatisfaction Open Question (next question)
    question_id=initial_question_id+2
    for index,answer_row in df[df.columns[loc+2]].items():
        if pd.isna(answer_row):
            continue
        answer=Answer(
            submission_id=submission_ids[index],
            question_id=question_id,
            value=answer_row,
            module_id=module_id,
            teacher=teacher.title(), # Capitalize first letter of each word
        )
        session.add(answer)
        session.flush()
    
    # Process Satisfaction Open Question (next question)
    question_id=initial_question_id+4
    for index,answer_row in df[df.columns[loc+3]].items():
        if pd.isna(answer_row):
            continue
        answer=Answer(
            submission_id=submission_ids[index],
            question_id=question_id,
            value=answer_row,
            module_id=module_id,
            teacher=teacher,
        )
        session.add(answer)
        session.flush()
    
    # Process answers Attendance
    if module_id:
        if rowsMask is not None:
            question_id=11
            option_id=24 # Oui
            for attendance in rowsMask:
                if attendance:
                    answer=Answer(
                        submission_id=submission_ids[index],
                        question_id=question_id,
                        option_id=option_id,
                        module_id=module_id,
                        teacher=teacher
                    
                    )
                    session.add(answer)
                    session.flush()
        else:
            if "avez-vous" in df.columns[loc-1].casefold():
                
                question_id=11
                for index,answer_row in df[df.columns[loc-1]].items():
                    if pd.isna(answer_row):
                        continue
                    text_fr=answer_row.split("/")[0].strip()
                    
                    option_id = session.exec(select(Option.option_id).where(Option.question_id==question_id,Option.text_fr==text_fr)).first()
                    answer=Answer(
                        submission_id=submission_ids[index],
                        question_id=question_id,
                        option_id=option_id,
                        module_id=module_id,
                        teacher=teacher
                    
                    )
                    session.add(answer)
                    session.flush()
            else: # No "avez-vous" question --> Yes for everyone
                question_id=11
                option_id=24 # Oui
                for submission_id in submission_ids:
                    answer=Answer(
                        submission_id=submission_id,
                        question_id=question_id,
                        option_id=option_id,
                        module_id=module_id,
                        teacher=teacher
                    
                    )
                    session.add(answer)
                    session.flush()
        
       
if __name__ == "__main__":
    if len(sys.argv) < 6:
        print(f"{sys.argv[0]} SYLLABUS_FILE FORMS_FILE PROGRAM SEMESTER SCHOOL_YEAR")
        exit(0)
    syllabus_file,forms_file,program,semester,school_year=sys.argv[1:6]
    session=Session(engine)
    program_row = session.exec(select(Program).where(Program.code==program)).first()
    if not program_row:
        print(f"Le code {program} n'existe pas dans la base Program. Merci de vérifier.")
        exit(1)
    survey = session.exec(select(Survey).where(Survey.program==program,
                    Survey.semester==semester,
                    Survey.school_year==school_year)).first()
    if survey is not None:
        print(f"Un sondage existe déjà pour la même formation/même semestre/même année.\nid:{survey.survey_id}")
        exit(1)
    survey=Survey(template_id=1,
                    program=program,
                    semester=semester,
                    school_year=school_year,
                    status=0)
    session.add(survey)
    session.flush()  # Pour obtenir le survey_id généré
    survey_id = survey.survey_id

    if syllabus_file:
        df = pd.read_excel(syllabus_file)
        modules={}
        for idx, row in df.iterrows():
            module=Module(
                name=row["name"].strip(),
                teacher=row["teachers"].strip(),
                ue=row["ue"].strip(),
                one_teacher_in_list=int(row["one_teacher_in_list"]),
                survey_id=survey_id
            )
            session.add(module)
            session.flush()
            modules[module.name]=module
    
    if forms_file:
        df = pd.read_excel(forms_file)

        submission_ids=[]
        for created_at in df['Heure de fin']:
            submission = Submission(survey_id=survey_id,created_at=created_at.strftime('%Y-%m-%d %X'))
            session.add(submission)
            session.flush()
            submission_ids.append(submission.submission_id)

        #df.replace(r"\xa0", '*', regex=True)
        try:
            df = df[df.columns.drop(list(df.filter(regex='Feedback -')))]
            df = df[df.columns.drop(list(df.filter(regex='Points -')))]
            df = df[df.columns.drop(list(df.filter(regex='Grade posted time')))]
            df = df[df.columns.drop(['Id','Heure de début','Heure de fin','Adresse de messagerie','Nom','Total points','Quiz feedback'])]
        except KeyError as e:
            print(f'{e}')

        # Section Campus        
        mask = df.columns.str.contains("expérience étudiante") & df.columns.str.contains("campus")
        target_cols = df.columns[mask].tolist()
        process_section(session,df,target_cols[0],1)
        # Section Formation        
        mask = df.columns.str.contains("formation") & df.columns.str.contains("campus")
        target_cols = df.columns[mask].tolist()
        process_section(session,df,target_cols[0],6)

        # Section Module/Enseignant
        for module_name in modules:
            module=modules[module_name]
            if module.one_teacher_in_list:
                mask = df.columns.str.contains(module.name,case=False) & (df.columns.str.contains("quel",case=False) | df.columns.str.contains("qui",case=False))
                target_cols = df.columns[mask].tolist()
                if len(target_cols)==0:
                        print(f"ERROR: No question found for {module.name} avec mot clef \"quel\" ou \"qui\". Please check the syllabus or the forms.")
                        exit(1)
                loc = df.columns.get_loc(target_cols[0])
                for teacher in module.teacher.split(","):
                    teacher=teacher.strip()
                    rowsMask = (df[target_cols[0]].str.casefold()==teacher.casefold())
                    if not rowsMask.any():
                        print(f"ERROR : Teacher |{teacher.casefold()}| not found in the answers of |{target_cols[0]}|")
                        print(df[target_cols[0]].str.casefold().unique())
                        exit(1)
                    process_section(session,df,df.columns[loc+1],12, module.module_id, teacher, rowsMask)
            else:
                for teacher in module.teacher.split(","):
                    teacher=teacher.strip()
                    mask = df.columns.str.contains(module.name,case=False) & df.columns.str.contains(teacher,case=False)
                    target_cols = df.columns[mask].tolist()
                    if len(target_cols)==0:
                        print(f"ERROR: No question found for {module.name} / {teacher}. Please check the syllabus or the forms.")
                        exit(1)
                    process_section(session,df,target_cols[0],12, module.module_id, teacher)
                    #exit(1)
        session.commit()
        print(f"Nouveu sondage publié. (id:{survey_id})")
        
        