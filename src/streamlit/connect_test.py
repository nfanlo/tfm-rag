from neo4j import GraphDatabase
import sys
sys.path.append('/Users/nfanlo/dev')
from config.config import config

#Change the following variables to your own Neo4j instance
NEO4J_USER = "neo4j"
NEO4J_DATABASE = "neo4j"
NEO4J_PASSWORD = config["neo4j_password"]
NEO4J_URL = config["neo4j_url"]

def testnodes_neo4j(uri, user, password, show_nodes=False):
    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
        with driver.session() as session:
            result = session.run("MATCH (n) RETURN count(n) AS count")
            print("CONECTION TO NEO4J WORKS")
            if show_nodes == True:
                print("Number of nodes in the database:", result.single()["count"])
    except Exception as e:
        print("CONECTION TO NEO4J FAILED")
        print(f"Connection failed: {e}")
    driver.close()