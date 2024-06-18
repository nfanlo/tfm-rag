import sys
import os
import json
from datetime import datetime
from neo4j import GraphDatabase
import torch.cuda as cuda
from langchain.embeddings.huggingface import HuggingFaceEmbeddings

# Añadir la ruta para importar configuraciones
sys.path.append('/Users/nfanlo/dev')
from config.config import config

# Configuración de Neo4j
NEO4J_USER = "neo4j"
NEO4J_DATABASE = "neo4j"
NEO4J_PASSWORD = config["neo4j_password"]
NEO4J_URL = config["neo4j_url"]

# Selección del modelo para embedding
embed_model_id = 'sentence-transformers/all-MiniLM-L6-v2'

# Configuración del dispositivo
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
            # Seleccionar solo los nodos que no tienen embeddings creados
            results = session.run(f"""
                MATCH (chunk:{node}) -[:HAS_PARENT]-> (s:Section)
                WHERE chunk.embedding_created IS NULL OR chunk.embedding_created = false
                RETURN id(chunk) AS id, s.title + ' >> ' + chunk.{property} AS text
            """)
            count = 0

            for result in results:
                id = result["id"]
                text = result["text"]
                embedding = embed_model.embed_documents([text])  # Cambié esta línea
                embedding_str = json.dumps(embedding[0])  # Convertir el primer resultado a JSON

                # Embedding: Crear nodo de Embedding con 'key' y 'embedding'
                # Relación id-Embedding: Crear relación [:HAS_EMBEDDING] desde id a nodo Embedding
                cypher = "CREATE (e:Embedding) SET e.key=$key, e.value=$embedding"
                cypher = cypher + " WITH e MATCH (n) WHERE id(n) = $id CREATE (n) -[:HAS_EMBEDDING]-> (e)"
                cypher = cypher + " SET n.embedding_created = true"
                session.run(cypher, key=property, embedding=embedding_str, id=id)

                count += 1
                
                # Reiniciar el modelo de embedding después de 30 cuentas para evitar errores de conexión en procesos largos
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

# Seleccionar los nodos y propiedades para aplicar la función de embeddings
# Cambiarlo a los nodos de tu base de datos
nodes_to_process = [("Chunk", "sentences"), ("Table", "name")]

for node in nodes_to_process:
    print(f'PROCESING {node} TO EMBEDDINGS:')
    print('-----------------------------------------------------------------')
    startTimeemb = datetime.now()
    print(f'START TIME EMB: {startTimeemb}')
    create_embedding(*node)
    print(f'END TIME EMB: {datetime.now() - startTimeemb}')
    print('-----------------------------------------------------------------')
