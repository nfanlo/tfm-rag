import pandas as pd
from datetime import datetime
import os
import streamlit as st
from streamlit.logger import get_logger
from langchain.callbacks.base import BaseCallbackHandler
from langchain_community.graphs.neo4j_graph import Neo4jGraph
from utils import extract_title_and_question
from chains_rag import load_embedding, load_llm, llm_chain, qa_rag_chain, llm_ticket

import sys
sys.path.append('/Users/nfanlo/dev')
from config.config import config

# Change the following variables to your own Neo4j instance
NEO4J_USER = "neo4j"
NEO4J_DATABASE = "neo4j"
NEO4J_PASSWORD = config["neo4j_password"]
NEO4J_URL = config["neo4j_url"]
neo4j_graph = Neo4jGraph(url=NEO4J_URL, username=NEO4J_USER, password=NEO4J_PASSWORD, database=NEO4J_DATABASE)

logger = get_logger(__name__)

llm_name = 'gpt-3.5'
embed_model_id = 'sentence-transformers/all-MiniLM-L6-v2'

llm = load_llm(llm_name, logger=logger)
embeddings, dimension = load_embedding(logger=logger)

llm_chain = llm_chain(llm)
rag_chain = None

def initialize_rag_chain(contract_name):
    global rag_chain
    rag_chain = qa_rag_chain(llm, embeddings, doc_name=contract_name, embeddings_url=NEO4J_URL, username=NEO4J_USER, password=NEO4J_PASSWORD, database=NEO4J_DATABASE)

class StreamHandler(BaseCallbackHandler):
    def __init__(self, container, initial_text=""):
        self.container = container
        self.text = initial_text
    def on_llm_new_token(self, token: str, **kwargs) -> None:
        self.text += token
        self.container.markdown(self.text)

col1, col2 = st.columns([3, 1])

with col1:
    st.image("images/grupo_asv_logo.jpeg", width=150)

def update_rag_reports(user_input, assistant_llm_chain, assistant_rag_chain, contract_name, username):
    csv_path = "dashboard-data/rag-reports.csv"
    if not os.path.exists("dashboard-data"):
        os.makedirs("dashboard-data")
    try:
        df_rag_reports = pd.read_csv(csv_path)
    except FileNotFoundError:
        df_rag_reports = pd.DataFrame(columns=['Index', 'Date', 'Document', 'User_Input', 'Assistant_llm_chain', 'Assistant_rag_chain', 'User'])
        df_rag_reports.to_csv(csv_path, index=False)

    index_counter = len(df_rag_reports) + 1
    now = datetime.now()
    date_time = now.strftime("%Y-%m-%d %H:%M:%S")
    new_row = {'Index': index_counter, 
               'Date': date_time, 
               'Document': contract_name, 
               'User_Input': user_input,
               'Assistant_llm_chain': assistant_llm_chain, 
               'Assistant_rag_chain': assistant_rag_chain,
               'User': username}

    df_rag_reports = pd.concat([df_rag_reports, pd.DataFrame([new_row])], ignore_index=True)
    df_rag_reports.to_csv(csv_path, index=False)

def chat_input(name):
    user_input = st.chat_input("¿En qué puedo ayudarte hoy?")
    if user_input:
        if name == "Activado" and not st.session_state.get('contract_name'):
            st.error("Por favor, introduzca el nombre del contrato.")
            return

        if name == "Activado" and not rag_chain:
            initialize_rag_chain(st.session_state['contract_name'])

        with st.chat_message("user"):
            st.write(user_input)

        if output_function is None:
            st.error("La función de salida no está definida.")
            return

        with st.chat_message("assistant"):
            st.caption(f"RAG: {name}")
            stream_handler = StreamHandler(st.empty())
            try:
                result = output_function({
                    "input_text": user_input,
                    "question": user_input,
                    "chat_history": [],
                    "contract_name": st.session_state['contract_name']
                }, callbacks=[stream_handler])["answer"]
            except Exception as e:
                st.error(f"Error al generar la respuesta: {str(e)}")
                return

            if result:
                output = result
                st.session_state["user_input"].append(user_input)
                st.session_state["generated"].append(output)
                st.session_state["rag_mode"].append(name)

                update_rag_reports(user_input, "", output if name == "Activado" else "", st.session_state['contract_name'], st.session_state['username'])
            else:
                st.error("No se pudo generar una respuesta.")

def display_chat():
    if "generated" not in st.session_state:
        st.session_state[f"generated"] = []

    if "user_input" not in st.session_state:
        st.session_state[f"user_input"] = []

    if "rag_mode" not in st.session_state:
        st.session_state[f"rag_mode"] = []

    if st.session_state[f"generated"]:
        size = len(st.session_state[f"generated"])
        for i in range(max(size - 3, 0), size):
            with st.chat_message("user"):
                st.write(st.session_state[f"user_input"][i])

            with st.chat_message("assistant"):
                st.caption(f"RAG: {st.session_state[f'rag_mode'][i]}")
                st.write(st.session_state[f"generated"][i])

        with st.expander("¿No encuentras lo que buscas?"):
            st.write("Generar automáticamente un borrador para un ticket interno a nuestro equipo de soporte.")
            st.button("Generar ticket", type="primary", key="show_ticket", on_click=open_sidebar,)
        with st.container():
            st.write("&nbsp;")

def mode_select() -> str:
    options = ["Desactivado", "Activado"]
    mode = st.radio("Seleccione el modo RAG", options, horizontal=True)
    if mode == "Activado":
        contract_name = st.text_input('Nombre del contrato', key='contract_name_input')
        if contract_name:
            st.session_state['contract_name'] = contract_name
            initialize_rag_chain(contract_name)
    return mode

if 'contract_name' not in st.session_state:
    st.session_state['contract_name'] = ""

name = mode_select()

output_function = None
if name == "Desactivado":
    output_function = llm_chain
elif name == "Activado":
    output_function = rag_chain

if name == "Activado" and output_function is None:
    st.error("El campo se encuentra vacío. Introduzca el nombre del contrato.")

def generate_ticket():
    q_prompt = st.session_state["user_input"][-1] if st.session_state["user_input"] else "No input provided"
    n_contract = st.session_state["contract_name"] if st.session_state["contract_name"] else "No contract name provided"

    llm_response = llm_ticket(q_prompt, llm)
    
    new_title, new_question = extract_title_and_question(llm_response["answer"])
    return q_prompt, new_title, new_question, n_contract

def close_sidebar():
    q_prompt, new_title, new_question, n_contract = generate_ticket()

    csv_path = "dashboard-data/ticket-reports.csv"
    if not os.path.exists("dashboard-data"):
        os.makedirs("dashboard-data")
    if not os.path.exists(csv_path):
        df_ticket_reports = pd.DataFrame(columns=['Index', 'Date', 'User', 'Document', 'Original_title_question', 'New_title_question', 'New_user_question'])
        df_ticket_reports.to_csv(csv_path, index=False)
    else:
        try:
            df_ticket_reports = pd.read_csv(csv_path)
        except pd.errors.EmptyDataError:
            df_ticket_reports = pd.DataFrame(columns=['Index', 'Date', 'User', 'Document' 'Original_title_question', 'New_title_question', 'New_user_question'])
    index_counter = len(df_ticket_reports) + 1
    now = datetime.now()
    date_time = now.strftime("%Y-%m-%d %H:%M:%S")
    username = st.session_state['username']
    new_row = {'Index': index_counter, 'Date': date_time, 'User': username, 'Original_title_question': q_prompt,
               'New_title_question': new_title, 'New_user_question': new_question, 'Document': n_contract}
    
    df_ticket_reports = pd.concat([df_ticket_reports, pd.DataFrame([new_row])], ignore_index=True)
    df_ticket_reports.to_csv(csv_path, index=False)
    st.session_state.open_sidebar = False

def open_sidebar():
    st.session_state.open_sidebar = True

if not "open_sidebar" in st.session_state:
    st.session_state.open_sidebar = False

if st.session_state.open_sidebar:
    q_prompt, new_title, new_question, n_contract = generate_ticket()
    with st.sidebar:
        st.title("Borrador de ticket")
        st.write("Borrador del ticket generado automáticamente")
        st.text_input("Nuevo título", new_title)
        st.text_input("Nombre del contrato", n_contract)
        st.text_area("Nueva descripción", new_question)
        st.button(
            "Enviar al equipo de soporte",
            type="primary",
            key="submit_ticket",
            on_click=close_sidebar)

if 'username' not in st.session_state:
    st.session_state['username'] = ''

if 'login_button' not in st.session_state:
    st.session_state['login_button'] = False

if st.session_state['username'] == '' and not st.session_state['login_button']:
    st.title("Iniciar sesión")
    st.text_input("Usuario", key='username_input')
    if st.button("Entrar"):
        if st.session_state['username_input']:
            st.session_state['username'] = st.session_state['username_input']
            st.session_state['login_button'] = True
        else:
            st.error("Escriba el nombre de usuario")
else:
    display_chat()
    chat_input(name)
