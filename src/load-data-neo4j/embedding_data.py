import json
import sys
from datetime import datetime
from torch import cuda
from neo4j import GraphDatabase
from langchain.embeddings.huggingface import HuggingFaceEmbeddings

sys.path.append('/Users/nfanlo/dev')
from config.config import config

#Change the following variables to your own Neo4j instance
NEO4J_USER = "neo4j"
NEO4J_DATABASE = "neo4j"
NEO4J_PASSWORD = config["neo4j_password"]
NEO4J_URL = config["neo4j_url"]

#Select 'all-MiniLM-L6-v2' for embedding text (low resources)
embed_model_id = 'sentence-transformers/all-MiniLM-L6-v2'

device = f'cuda:{cuda.current_device()}' if cuda.is_available() else 'cpu'
def embedding_model():
    return HuggingFaceEmbeddings(model_name=embed_model_id,
        model_kwargs={'device': device},
        encode_kwargs={'device': device, 'batch_size': 128})

def create_embedding(node, property):
    """Function to create embeddings from chunks of the Neo4j database.
    The function expects a tuple with the name of the node and the name of 
    the property to apply the selected embedding"""

    driver = GraphDatabase.driver(NEO4J_URL, auth=(NEO4J_USER, NEO4J_PASSWORD), database=NEO4J_DATABASE)
    embed_model = embedding_model()

    with driver.session() as session:
        try:
            results = session.run(f"MATCH (chunk:{node}) -[:HAS_PARENT]-> (s:Section) RETURN id(chunk) AS id, s.title + ' >> ' + chunk.{property} AS text")
            count = 0

            for result in results:
                id = result["id"]
                text = result["text"]
                embedding = embed_model.embed_documents(text)
                embedding_str = json.dumps(embedding)

                #Embeddng: Create Embeddng node with 'key', 'embedding'
                #Relationship id-Embedding: Creates relationship [:HAS_EMBEDDING] from id to Embedding node
                cypher = "CREATE (e:Embedding) SET e.key=$key, e.value=$embedding"
                cypher = cypher + " WITH e MATCH (n) WHERE id(n) = $id CREATE (n) -[:HAS_EMBEDDING]-> (e)"
                session.run(cypher,key=property, embedding=embedding_str, id=id )

                count += 1
                
                #Restart embeding_model after 30 counts to avoid connection errors with very long processes
                if count % 30 == 0:
                    embed_model = embedding_model()

            print(f'Processed {str(count)} ||| Node: {node} ||| Property: {property}')
            print('-----------------------------------------------------------------')
            return count

        except Exception as e:
            print('-----------------------------------------------------------------')
            print(f"CONECTION ERROR: {e}")

        finally:
            session.close()

#Select the nodes and properties to apply embeddings function
#Change it into your database nodes
nodes_to_process = [("Chunk", "sentences"), ("Table", "name")]

for node in nodes_to_process:
    print(f'PROCESING {node} TO EMBEDDINGS:')
    print('-----------------------------------------------------------------')
    startTimeemb = datetime.now()
    print(f'START TIME EMB: {startTimeemb}')
    create_embedding(*node)
    print(f'END TIME EMB: {datetime.now() - startTimeemb}')
    print('-----------------------------------------------------------------')