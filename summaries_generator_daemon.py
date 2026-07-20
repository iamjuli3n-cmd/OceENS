from database import engine
from sqlmodel import Session, select, func
from models import Summary, Answer, Prompt, Question,Module,Program, Survey
import requests_cache
import json
from datetime import datetime
from markdown_it import MarkdownIt
import time
import os
from dotenv import load_dotenv


load_dotenv()


import sys, signal
def signal_handler(signal, frame):
    print("\nprogram exiting gracefully")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)


LLM_API_KEY= os.getenv("LLM_API_KEY")  # fill the api_key in the .env 
OLLAMA_URL="https://locallm.mde.epf.fr/ollama"
OLLAMA_HEADERS={'Authorization':f"Bearer {LLM_API_KEY}", 'Content-type': 'application/json'}

import requests

def checkModel(modelName,session=requests.Session()):
    modelList=[]
    r = session.get(f"{OLLAMA_URL}/api/tags", headers=OLLAMA_HEADERS)
    if r.status_code == 200:
        json = r.json()
        
        if "models" in json.keys():
            for model in json["models"]:
                modelList.append(model['name'])
                if model['name'] == modelName:
                    return True
        else:
            raise Exception(f"Error : {json}")
    else:
        raise Exception(f"Failed with error code {r.status_code}")
    print(f"{modelName} not found in {modelList}")
    return False

def askModel(modelName, prompt,session=requests.Session(),timeout=60,seed=42):
    json_data={"model":modelName,"prompt": prompt, "stream":False, "options": {"seed": seed}}
    # Available options (other than seed): https://github.com/ollama/ollama/blob/main/docs/api.md#request-reproducible-outputs
    r = session.post(f"{OLLAMA_URL}/api/generate", headers=OLLAMA_HEADERS, json=json_data,timeout=timeout)
    if r.status_code == 200:
        json = r.json()
        del(json["context"])
        if "response" in json:
            return json["response"], json, r.status_code
        else:
            return None, json, r.status_code
    else:
        return None, None, r.status_code

if __name__ == "__main__":

    md = MarkdownIt()

    session_llm = requests_cache.CachedSession('cache_llm.db',allowable_methods=['GET', 'POST'],expire_after = requests_cache.NEVER_EXPIRE)
    
    llm_ok=None

    while (True):
    
        with Session(engine) as session:
            summary_row = session.exec(select(Summary).where(Summary.http_status==0)).first()
            

            if not summary_row:
                print("Pas de résumé à réaliser.")
                session.commit()
                time.sleep(30)
                continue
            # print(summary_row)

        

            model,prompt = session.exec(select(Prompt.model,Prompt.prompt_text).where(Prompt.prompt_id==summary_row.prompt_id)).first()

            # print(model)
            # print(prompt)

            if llm_ok is None:
                try:
                    llm_ok=checkModel(model)
                    if llm_ok:
                        print("LLM server respond and the model was found")
                    else:
                        print("LLM server respond and the model was NOT found")
                        exit(1)
                except Exception as e:
                    print(f"LLM server response error ({e}).\n(ex: 404=Not found, 401=Authentication error).\nSkipping LLM summarisation")
                    exit(1)

            # question,campus,program,module_name = session.exec(select(Question.text_fr,Program.campus, Program.name, Module.name).select_from(Question).join(Survey,Survey.survey_id==summary_row.survey_id).join(Program, Program.code == Survey.program, isouter=True)
            #     .join(Module, Module.module_id == summary_row.module_id, isouter=True).where(Question.question_id==summary_row.question_id)).first()
            
            # print(question,campus,program,module_name )
            #question = question.replace([])

            if summary_row.module_id:
                summary_verbatim = session.exec(select(Answer.value).where(Answer.question_id==summary_row.question_id,Answer.module_id==summary_row.module_id,Answer.teacher==summary_row.teacher)).all()
            else:
                summary_verbatim = session.exec(select(Answer.value).where(Answer.question_id==summary_row.question_id)).all()

            print(summary_verbatim)

            
            
            full_prompt=prompt.replace("{ANSWERS}",'|'.join(summary_verbatim))
            # print(full_prompt)

            if llm_ok:
                llm_answer, llm_metadata, status_code = askModel(model,full_prompt,session=session_llm,timeout=120)
                # print(llm_answer)
                # print(llm_metadata)
                # print(status_code)

                dt = datetime.fromisoformat(llm_metadata["created_at"].replace('Z', '+00:00'))
                date_pretty = dt.strftime("%d/%m/%Y %H:%M")
                metadata_text=f"Réponse synthétisée par {llm_metadata["model"]} le {date_pretty} en {llm_metadata["total_duration"]/1000000000:.1f}s ({1000000000*llm_metadata["eval_count"]/llm_metadata["eval_duration"]:.1f} token/s)"
                print(metadata_text)

                summary_row.summary_text = md.render(llm_answer)
                summary_row.metadata_text = metadata_text
                summary_row.http_status=status_code
                session.add(summary_row)
                
                session.commit()
        
