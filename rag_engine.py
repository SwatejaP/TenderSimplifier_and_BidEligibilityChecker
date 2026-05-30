import os
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_groq import ChatGroq
from langchain.chains import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate

class TenderRAGEngine:
    def __init__(self):
        # 100% Free, Open-Weights Embeddings via HuggingFace
        # Runs locally on CPU very efficiently, no API key required for this specific model load
        self.embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
        
    def create_vector_store(self, raw_text: str):
        """Chunks text and indexes it into a local FAISS vector store in memory."""
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len
        )
        chunks = text_splitter.split_text(raw_text)
        vector_store = FAISS.from_texts(chunks, self.embeddings)
        return vector_store

    def query_tender(self, vector_store, system_prompt: str, user_query: str) -> str:
        """Executes a structured RAG query against the FAISS index."""
        retriever = vector_store.as_retriever(search_kwargs={"k": 5})
        
        # Determine model name dynamically to avoid rate limits
        model_name = "llama-3.1-8b-instant"
        try:
            import streamlit as st
            if "selected_model" in st.session_state:
                model_name = st.session_state.selected_model
        except Exception:
            pass
            
        llm = ChatGroq(
            model=model_name,
            temperature=0,
            max_tokens=1024,
            api_key=os.getenv("GROQ_API_KEY")
        )
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "{input}\n\nContext:\n{context}")
        ])
        
        question_answer_chain = create_stuff_documents_chain(llm, prompt)
        rag_chain = create_retrieval_chain(retriever, question_answer_chain)
        
        response = rag_chain.invoke({"input": user_query})
        return response["answer"]
