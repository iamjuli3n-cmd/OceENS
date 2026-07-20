import pandas as pd
import sys
import re
from database import engine
from sqlmodel import Session, select, func
from models import  Survey, Submission, Answer, Option,Module

def process_section(session,df,column_name, initial_question_id, module_id=None, teacher=None):
    loc = df.columns.get_loc(column_name)
    question_id=initial_question_id
    print(df[column_name])

    # Process answers
    for index,answer_row in df[column_name].items():
        text_fr=answer_row.split("/")[0].strip()
        
        option_id = session.exec(select(Option.option_id).where(Option.question_id==question_id,Option.text_fr==text_fr)).first()
        print(text_fr, option_id)
        answer=Answer(
            submission_id=submission_ids[index],
            question_id=question_id,
            option_id=option_id,
            module_id=module_id,
            teacher=teacher,
        )
        session.add(answer)
        session.flush()
        
    # Process Insatisfaction (next question)
    question_id=initial_question_id+1
    print(df.columns[loc+1])
    for index,answer_row in df[df.columns[loc+1]].items():
        print(answer_row)
        if pd.isna(answer_row):
            continue
        for choice in answer_row.split(";"): # Multiple choice question
            if len(choice)==0:
                continue
            text_fr=choice.split("/")[0].strip()
            
            option_id = session.exec(select(Option.option_id).where(Option.question_id==question_id,Option.text_fr==text_fr)).first()
            print(text_fr, option_id)
            if option_id is None:
                continue
            answer=Answer(
                submission_id=submission_ids[index],
                question_id=question_id,
                option_id=option_id,
                module_id=module_id,
                teacher=teacher,
            )
            session.add(answer)
            session.flush()
    
    # Process Insatisfaction Open Question (next question)
    question_id=initial_question_id+2
    print(df.columns[loc+2])
    for index,answer_row in df[df.columns[loc+2]].items():
        print(answer_row)
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
    
    # Process Satisfaction Open Question (next question)
    question_id=initial_question_id+4
    print(df.columns[loc+3])
    for index,answer_row in df[df.columns[loc+3]].items():
        print(answer_row)
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
        if "avez-vous" not in df.columns[loc-1].casefold():
            print(f"ERROR: Attendance question missing for {column_name}.\nCheck Syllabus or Forms xlsx.")
            exit(1)
        question_id=11
        for index,answer_row in df[df.columns[loc-1]].items():
            if pd.isna(answer_row):
                continue
            text_fr=answer_row.split("/")[0].strip()
            
            option_id = session.exec(select(Option.option_id).where(Option.question_id==question_id,Option.text_fr==text_fr)).first()
            print(text_fr, option_id)
            answer=Answer(
                submission_id=submission_ids[index],
                question_id=question_id,
                option_id=option_id,
                module_id=module_id,
                teacher=teacher
            
            )
            session.add(answer)
            session.flush()

def process_section_with_teacher(session,df,column_name, initial_question_id, module_id, teacher_name):

    # Process answers Attendance
    loc = df.columns.get_loc(column_name)
    question_id=11
    for index,answer_row in df[df.columns[loc-1]].items():
        if pd.isna(answer_row):
            continue
        text_fr=answer_row.split("/")[0].strip()
        
        option_id = session.exec(select(Option.option_id).where(Option.question_id==question_id,Option.text_fr==text_fr)).first()
        print(text_fr, option_id)
        answer=Answer(
            submission_id=submission_ids[index],
            question_id=question_id,
            option_id=option_id,
            module_id=module_id,
            teacher=teacher
        
        )
        session.add(answer)
        session.flush()

def extract_module_and_teacher(column_name):
    # 1. This regex captures:
    #    Group 1: Everything between 'pour ' and ' avec' (The Module Segment)
    #    Group 2: Everything between 'avec [type] ' and the next comma (The Teacher Segment)
    pattern = r"pour (.*?) avec (?:l'enseignant(?:e)?|cet enseignant\(e\))\s*([^,]+)?"
    
    match = re.search(pattern, column_name)
    if not match:
        return None, None

    module_segment = match.group(1)
    teacher_segment = match.group(2)

    # --- CLEAN MODULE LOGIC ---
    # If 'du module' exists, we check if there is a name after it.
    # If not, we take the name appearing before it.
    if "du module" in module_segment:
        parts = module_segment.split("du module")
        # If there's text after 'du module', use it; otherwise, use the text before it.
        module_name = parts[-1].strip() if parts[-1].strip() else parts[0].split("partie")[-1].strip()
    else:
        # Otherwise, just strip 'le module' or 'la partie'
        module_name = re.sub(r"^(le module|la partie|le module de la partie)", "", module_segment).strip()

    # --- CLEAN TEACHER LOGIC ---
    # If the teacher segment is empty, it means 'cet enseignant(e)' was used.
    teacher_name = teacher_segment.strip() if teacher_segment else "None"

    return module_name, teacher_name

if __name__ == "__main__":
    if len(sys.argv) < 6:
        print(f"{sys.argv[0]} SYLLABUS_FILE FORMS_FILE PROGRAM SEMESTER SCHOOL_YEAR")
        exit(0)
    syllabus_file,forms_file,program,semester,school_year=sys.argv[1:6]
    session=Session(engine)
    survey=Survey(template_id=1,
                    program=program,
                    semester=semester,
                    school_year=school_year,
                    status=0)
    session.add(survey)
    session.flush()  # Pour obtenir le survey_id généré
    survey_id = survey.survey_id
    print(survey_id)

    if syllabus_file:
        df = pd.read_excel(syllabus_file)
        modules={}
        for idx, row in df.iterrows():
            module=Module(
                name=row["name"].strip(),
                teacher=row["teachers"].strip(),
                ue=row["ue"].strip(),
                is_optional=int(row["is_optional"]),
                one_teacher_in_list=int(row["one_teacher_in_list"]),
                survey_id=survey_id
            )
            session.add(module)
            session.flush()
            modules[module.name]=module
        print(modules)
    
    if forms_file:
        print(forms_file, program, semester, school_year)
        df = pd.read_excel(forms_file)

        submission_ids=[]
        for created_at in df['Heure de fin']:
            submission = Submission(survey_id=survey_id,created_at=created_at.strftime('%Y-%m-%d %X'))
            session.add(submission)
            session.flush()
            submission_ids.append(submission.submission_id)

        #df.replace(r"\xa0", '*', regex=True)
        df = df[df.columns.drop(list(df.filter(regex='Feedback -')))]
        df = df[df.columns.drop(list(df.filter(regex='Points -')))]
        df = df[df.columns.drop(list(df.filter(regex='Grade posted time')))]
        df = df[df.columns.drop(['Id','Heure de début','Heure de fin','Adresse de messagerie','Nom','Total points','Quiz feedback'])]

        # Section Campus        
        mask = df.columns.str.contains("expérience étudiante") & df.columns.str.contains("campus")
        target_cols = df.columns[mask].tolist()
        print(target_cols)
        process_section(session,df,target_cols[0],1)
        # Section Formation        
        mask = df.columns.str.contains("formation") & df.columns.str.contains("campus")
        target_cols = df.columns[mask].tolist()
        print(target_cols)
        process_section(session,df,target_cols[0],6)

        # Section Module/Enseignant
        for module_name in modules:
            module=modules[module_name]
            if module.is_optional or module.one_teacher_in_list:
                continue
            print(module)
            for teacher in module.teacher.split(","):
                mask = df.columns.str.contains(module.name,case=False) & df.columns.str.contains(teacher,case=False)
                target_cols = df.columns[mask].tolist()
                if len(target_cols)==0:
                    print(f"ERROR: No question found for {module.name} / {teacher}. Please check the syllabus or the forms.")
                    exit(1)
                print(target_cols)
                process_section(session,df,target_cols[0],12, module.module_id, teacher)
                #exit(1)


        # for column_name in df.columns:
        #     if "expérience étudiante" in column_name and "campus" in column_name:
        #         process_section(session,df,column_name,1)
        #     elif "formation" in column_name and "campus" in column_name:
        #         process_section(session,df,column_name,6)
        #     elif "enseignant" in column_name and "quel" in column_name.casefold():
        #         pass
        #     elif "enseignant" in column_name:
        #         #print(column_name.split("/")[0])
        #         module_name,teacher_name = extract_module_and_teacher(column_name.split("/")[0])
        #         #print(f"Module {module_name} / Teacher {teacher_name}")
        #         

                
                
                    
        session.commit()
        print(survey_id)
        
        