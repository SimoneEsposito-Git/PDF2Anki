from core.question_gen import Question
from openai import OpenAI
import os

def generate_answer(question: Question, vectorstore, language="german"):
    prompt = """
    Respond to the following question using the provided context. Be concise and clear. Responses should be no longer than 1 or 2 sentences.
    Only use the information provided in the context to answer the question. Provide the answer in {language}.
    
    use HTML formatting where helpful:
        - Use <strong></strong> for key terms. (Do NOT use ** or __)
        - Use <ul><li>...</li></ul> for bullet points.
        - <table> for comparisons.
    
    Context: {context}
    Question: [{question_type}] {question}
    """

    relevant_chunks = vectorstore.similarity_search(question.question, k=4)
    context = "\n".join(chunk.page_content for chunk in relevant_chunks)

    prompt = prompt.format(
        context=context,
        question=question.question,
        question_type=question.card_type,
        language=language
    )

    api_key = os.environ.get("OPENAI_API_KEY")
    client = OpenAI(api_key=api_key)
    response = client.responses.create(
        model="gpt-4o-mini",
        input=[
            {"role": "user", "content": prompt}
        ]
    )

    content = response.output_text.strip()
    return content