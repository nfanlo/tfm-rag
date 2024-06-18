from typing import List, Any
from torch import cuda
from langchain_openai import ChatOpenAI
from langchain.prompts.chat import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from langchain.chains.qa_with_sources import load_qa_with_sources_chain
from langchain_community.vectorstores.neo4j_vector import Neo4jVector
from langchain.chains.qa_with_sources.retrieval import RetrievalQAWithSourcesChain
from langchain_community.embeddings.sentence_transformer import SentenceTransformerEmbeddings
from utils import BaseLogger
from connect_test import testnodes_neo4j
import sys
sys.path.append('/Users/nfanlo/dev')
from config.config import config

NEO4J_USER = "neo4j"
NEO4J_DATABASE = "neo4j"
NEO4J_PASSWORD = config["neo4j_password"]
NEO4J_URL = config["neo4j_url"]
OPENAI_PASSWORD = config['openai_api_key']

embed_model_id = 'sentence-transformers/all-MiniLM-L6-v2'

device = f'cuda:{cuda.current_device()}' if cuda.is_available() else 'cpu'

def load_embedding(logger=BaseLogger()):
    """Function that loads the selected embedding for later use in RAG mode"""

    embeddings = SentenceTransformerEmbeddings(model_name="all-MiniLM-L6-v2")
    dimension = 384
    logger.info("Embedding: Using SentenceTransformer")
    return embeddings, dimension

def load_llm(llm_name, logger=BaseLogger()):
    """Function that loads the selected model in the streamlit application. 
    The function waits for the input of the model name in str between gpt-3.5 or gpt-4"""
    
    if llm_name == 'gpt-4':
        logger.info('LLM: GPT-4')
        return ChatOpenAI(temperature=0.2, model_name='gpt-4', streaming=True, openai_api_key=OPENAI_PASSWORD)
    elif llm_name == 'gpt-3.5':
        logger.info('LLM: GPT 3.5-turbo')
        return ChatOpenAI(temperature=0.2, model_name='gpt-3.5-turbo', streaming=True, openai_api_key=OPENAI_PASSWORD)
    else:
        logger.info('NO LLM MODEL SELECTED')
        logger.info('LLM: GPT 3.5-turbo')
        return ChatOpenAI(temperature=0.2, model_name='gpt-3.5-turbo', streaming=True, openai_api_key=OPENAI_PASSWORD)

def llm_chain(llm):
    """Function that generates a response from the llm model when RAG mode is disabled. 
    The function waits for the selected llm model. This function will process the user input 
    and generate the complete response flow with the llm model."""

    testnodes_neo4j(NEO4J_URL, NEO4J_USER, NEO4J_PASSWORD, show_nodes=False) #Change True: Show number of nodes in Neo4j DB
    template = """
    You are a GPT lawyer, the best specialist in contracts and Spanish laws that helps with answering general questions.
    Generate concise answers and should not exceed 200 words. Remember response only in Spanish text.
    If you don't know the answer, just say that you don't know, don't try to make up an answer.
    """
    system_message_prompt = SystemMessagePromptTemplate.from_template(template)
    human_template = "{text}"
    human_message_prompt = HumanMessagePromptTemplate.from_template(human_template)
    chat_prompt = ChatPromptTemplate.from_messages([system_message_prompt, human_message_prompt])

    def llm_output(user_input: str, callbacks: List[Any], prompt=chat_prompt) -> str:
        answer = llm(prompt.format_prompt(text=user_input).to_messages(), callbacks=callbacks).content
        return {"answer": answer}
    return llm_output

def qa_rag_chain(llm, embeddings, embeddings_url, username, password, database, doc_name):
    """Function that generates a response from the RAG system when the mode is activated. 
    The function expects the llm model, the embedding model, the contract name and the instance 
    variables from the Neo4j database. 
    The function will search the database for the chunks of text most similar to the user input 
    and generate the complete response flow with the llm model"""

    testnodes_neo4j(NEO4J_URL, NEO4J_USER, NEO4J_PASSWORD, show_nodes=False)
    print("DOCUMENT NAME:", doc_name)

    #Cypher query to retrieve chunk Neo4j contracts for user question
    sample_query = """
    WITH node AS doc, score AS similarity
    ORDER BY similarity DESC LIMIT 5
    CALL {
        WITH doc
        MATCH (e:Embedding)-[:HAS_EMBEDDING]->(chunk:Chunk)
        OPTIONAL MATCH (chunk)-[:HAS_PARENT]->(section:Section)
        OPTIONAL MATCH (section)-[:HAS_DOCUMENT]->(document:Document)
        RETURN chunk AS result, section, document}
    WITH result, section, document, similarity
    RETURN 
        result.sentences AS text,
        similarity AS score,
        {documentName: document.name,
        sectionTitle: section.title,
        pageIndex: result.page_idx} AS metadata
    """
    #Template to generate QA with contracts retrieved from Neo4j
    general_system_template = """
    You are a GPT lawyer, the best specialist in contracts and Spanish laws.
    The next context contains fragments of text from a contract for one of the Spanish clients of an insurance company.
    Your role is to use the following pieces of context and your knowledge of Spanish laws and contracts to provide a 
    response using the context pieces about the customer contract.
    ####
    {summaries}
    ####
    Follow these steps to answer the customer queries.
    Step 1: Read slowly, relate and keep in mind the context pieces of the contract and the Question about the client.
    Step 2: Think and generate a coherent answer to the final question using your knowledge of general contracts and law 
    and Spanish along with context pieces from the client's contract.
    Generate concise answers and shoud not exceed 200 words. Remeber response only in Spanish text.
    If you don't know the answer, just say you don't know, don't try to make up an answer.
    """
    general_user_template = "Input:```{input_text}```"

    messages = [SystemMessagePromptTemplate.from_template(general_system_template),
                HumanMessagePromptTemplate.from_template(general_user_template)]
    qa_prompt = ChatPromptTemplate.from_messages(messages)

    qa_chain = load_qa_with_sources_chain(llm, chain_type="stuff", prompt=qa_prompt)

    graph_response = Neo4jVector.from_existing_index(
        embedding=embeddings,
        url=embeddings_url,
        username=username,
        password=password,
        database=database,
        index_name="chunkVectorIndex",
        node_label="Embedding",
        embedding_node_property="value",
        text_node_property="sentences",
        retrieval_query=sample_query)

    graph_response_qa = RetrievalQAWithSourcesChain(
        combine_documents_chain=qa_chain,
        retriever=graph_response.as_retriever(search_kwargs={"k": 2}), #Number of relevant chunks retrieved
        reduce_k_below_max_tokens=True,
        max_tokens_limit=3375, #GPT 3.5-turbo. Can be raised to 7000 for GPT 4
        return_source_documents=True)
    
    return graph_response_qa

def llm_ticket(user_input, llm):
    """Function that generates a report ticket from a user's input when the caller has not responded correctly. 
    The function waits for the user to enter the chat when they have pressed the generate ticket button and the llm model selected. 
    This function will generate a new title and more extensive question about the entry that the user has entered for subsequent analysis by the support team."""

    gen_system_template = """
    You're an expert in formulating high quality questions in Spanish text. 
    Can you formulate a question in the same style, detail and tone as the following example questions?
    ---
    Don't make anything up, only use information in the following question.
    Return a title for the question, and the question post itself.
    Return example:
    ---
    Title: How do I use the Neo4j Python driver?
    Question: I'm trying to connect to Neo4j using the Python driver, but I'm getting an error.
    ---
    Remember to always respond only in Spanish text.
    """
    system_prompt = SystemMessagePromptTemplate.from_template(gen_system_template, template_format="jinja2")

    chat_prompt = ChatPromptTemplate.from_messages([
        system_prompt,
        SystemMessagePromptTemplate.from_template(
            """
            Respond in the following format or you will be unplugged.
            Title: New title
            Question: New question
            """),
        HumanMessagePromptTemplate.from_template("{text}")])
    
    llm_output = llm_chain(llm)
    llm_response = llm_output(f"Here's the question to rewrite in the expected format: ```{user_input}```", [], chat_prompt)
    
    return llm_response
