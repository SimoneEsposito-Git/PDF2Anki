from langchain_community.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain.docstore.document import Document
from config import OPENAI_API_KEY

def build_vectorstore(chunks, ):
    docs = [Document(page_content=c) for c in chunks]
    embedding = OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY)
    return Chroma.from_documents(docs, embedding)