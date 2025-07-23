from pydantic import BaseModel
from typing import List, Tuple
from config import OPENAI_API_KEY 
from openai import OpenAI

class Question(BaseModel):
    card_type: str
    question: str
    
class Questions(BaseModel):
    questions: list[Question]

def generate_questions(chunks, language="german", questions_per_chunk=10):
    prompt = """
            You're an assistant creating flashcards from academic material.
            Given the following text, generate questions in {language} for each of the following flashcard types:
            
            Definition: What is the definition of the key concept in the text?
            Fact Recall: What is a key fact mentioned in the text?
            Conceptual Understanding: How does the concept in the text relate to other concepts?
            Application: How can the concept in the text be applied in a real-world scenario?
            Comparison: How does the concept in the text compare to similar concepts?
            Classification: How would you classify the concept in the text?
            Cloze: Create a fill-in-the-blank question based on the text.
            True/False: Create a true/false statement based on the text.
            Cause-Effect: What cause-and-effect relationships are described in the text?
            Study/Finding: What is a key study or finding mentioned in the text?

            Only generate questions for the types that are relevant to the text. 
            
            !!! GENERATE EXACTLY {count} questions !!!
            
            TEXT:
            \"\"\"{your_chunk_here}\"\"\"
            """
    
    openai_client = OpenAI(api_key=OPENAI_API_KEY)
    questions = []
    for chunk in chunks:
        user_prompt = prompt.format(your_chunk_here=chunk, language=language, count=questions_per_chunk)
        response = openai_client.responses.parse(
            model="gpt-4o-mini",
            input=[
                {"role": "user", "content": user_prompt}
            ],
            text_format = Questions
        )
        questions.extend(response.output_parsed.questions[:questions_per_chunk])
        # print(f"Generated {len(response.output_parsed.questions)} questions for chunk {i+1}/{len(chunks)}")
    return questions