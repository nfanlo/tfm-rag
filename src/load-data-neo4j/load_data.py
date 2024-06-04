import hashlib
import os
import glob
import shutil
import sys
from datetime import datetime
from neo4j import GraphDatabase
from llmsherpa.readers import LayoutPDFReader

sys.path.append('/Users/nfanlo/dev')
from config.config import config

#Change the following variables to your own Neo4j instance
NEO4J_USER = "neo4j"
NEO4J_DATABASE = "neo4j"
NEO4J_PASSWORD = config["neo4j_password"]
NEO4J_URL = config["neo4j_url"]

llmsherpa_api_url = "https://readers.llmsherpa.com/api/document/developer/parseDocument?renderFormat=all"

#Path to select the new files to preprocess in the newdata folder and assign them to the dataloaded folders
file_location = os.path.join(os.path.dirname(__file__), 'newdata')
file_destination = os.path.join(os.path.dirname(__file__), 'dataloaded')

schema_initialized = False

def schemaNeo4j():
    """Function to initialize Neo4j main schema 
    before processing the pdf files"""
    
    global schema_initialized

    if schema_initialized:
        print("Schema already initialized, skipping.")
        return
#
    cypher_schema = [
        "CREATE CONSTRAINT sectionKey IF NOT EXISTS FOR (c:Section) REQUIRE (c.key) IS UNIQUE;",
        "CREATE CONSTRAINT chunkKey IF NOT EXISTS FOR (c:Chunk) REQUIRE (c.key) IS UNIQUE;",
        "CREATE CONSTRAINT documentKey IF NOT EXISTS FOR (c:Document) REQUIRE (c.url_hash) IS UNIQUE;",
        "CREATE CONSTRAINT tableKey IF NOT EXISTS FOR (c:Table) REQUIRE (c.key) IS UNIQUE;",
        "CALL db.index.vector.createNodeIndex('chunkVectorIndex', 'Embedding', 'value', 384, 'COSINE');"]
    
    driver = GraphDatabase.driver(NEO4J_URL, database=NEO4J_DATABASE, auth=(NEO4J_USER, NEO4J_PASSWORD))
    with driver.session() as session:
        try:
            for cypher in cypher_schema:
                session.run(cypher)
        except Exception as e:
            print("An error occurred while creating schema:", e)
    schema_initialized = True
    driver.close()

def processpdfNeo4j(doc, doc_location):
    """Function to process pdf files to the Neo4j Aura database. 
    The function expects a json opened with the LayoutPDFReader 
    library to preprocess in the doc variable and the pdf opened in pdf_file"""

    cypher_pool = [
    #Document: Create Document node with 'url_hash' and 'doc_name' from document loaded
    "MERGE (d:Document {url_hash: $doc_url_hash_val, name: $doc_name_val}) ON CREATE SET d.url = $doc_url_val RETURN d;",  
    #Section: Create Section node with doc_name and url_hash with properties of document loaded
    "MERGE (p:Section {key: $doc_name_val + '_' + $doc_url_hash_val + '|' + $block_idx_val + '|' + $title_hash_val}) ON CREATE SET p.page_idx = $page_idx_val, p.title_hash = $title_hash_val, p.block_idx = $block_idx_val, p.title = $title_val, p.tag = $tag_val, p.level = $level_val RETURN p;",
    #Relationship Doc-Sec: Creates relationship [:HAS_DOCUMENT] from Section to Document
    "MATCH (d:Document {url_hash: $doc_url_hash_val}) MATCH (s:Section {key: $doc_name_val + '_' + $doc_url_hash_val + '|' + $block_idx_val + '|' + $title_hash_val}) MERGE (d)<-[:HAS_DOCUMENT]-(s);",
    #Relationship S1-S2: Creates relationship [:UNDER_SECTION] from Section 2 to Section 1
    "MATCH (s1:Section {key: $doc_name_val + '_' + $doc_url_hash_val + '|' + $parent_block_idx_val + '|' + $parent_title_hash_val}) MATCH (s2:Section {key: $doc_name_val + '_' + $doc_url_hash_val + '|' + $block_idx_val + '|' + $title_hash_val}) MERGE (s1)<-[:UNDER_SECTION]-(s2);",
    #Chunk: Create Chunk node with 'doc_name', 'url_hash', 'sentences_val', 'sentences_hash', 'block_id', 'page_id', 'tag_val' and 'c_level'
    "MERGE (c:Chunk {key: $doc_name_val + '_' + $doc_url_hash_val + '|' + $block_idx_val + '|' + $sentences_hash_val}) ON CREATE SET c.sentences = $sentences_val, c.sentences_hash = $sentences_hash_val, c.block_idx = $block_idx_val, c.page_idx = $page_idx_val, c.tag = $tag_val, c.level = $level_val RETURN c;",
    #Relationship Chunk-Section: Creates relationship [:HAS_PARENT] from Chunk nodes to Section nodes
    "MATCH (c:Chunk {key: $doc_name_val + '_' + $doc_url_hash_val + '|' + $block_idx_val + '|' + $sentences_hash_val}) MATCH (s:Section {key:$doc_name_val + '_' + $doc_url_hash_val + '|' + $parent_block_idx_val + '|' + $parent_hash_val}) MERGE (s)<-[:HAS_PARENT]-(c);",
    #Table: Create Table nodes with 'doc_name', 'url_hash', 'block_id', 'name_val', 'page_id', 'html_val', 'rows_val'
    "MERGE (t:Table {key: $doc_name_val + '_' + $doc_url_hash_val + '|' + $block_idx_val + '|' + $name_val}) ON CREATE SET t.name = $name_val, t.doc_url_hash = $doc_url_hash_val, t.block_idx = $block_idx_val, t.page_idx = $page_idx_val, t.html = $html_val, t.rows = $rows_val RETURN t;",
    #Relationship Table-Section: Creates relationship [:HAS_PARENT] from Table nodes to Section nodes
    "MATCH (t:Table {key: $doc_name_val + '_' + $doc_url_hash_val + '|' + $block_idx_val + '|' + $name_val}) MATCH (s:Section {key: $doc_name_val + '_' + $doc_url_hash_val + '|' + $parent_block_idx_val + '|' + $parent_hash_val}) MERGE (s)<-[:HAS_PARENT]-(t);",
    #Relationship Table-Document: Creates relationship [:HAS_PARENT] from Table nodes to Document nodes if Table nodes dont have [HAS_PARENT] Section
    "MATCH (t:Table {key: $doc_name_val + '_' + $doc_url_hash_val + '|' + $block_idx_val + '|' + $name_val}) MATCH (d:Document {url_hash: $doc_url_hash_val}) MERGE (d)<-[:HAS_PARENT]-(t);"]

    driver = GraphDatabase.driver(NEO4J_URL, database=NEO4J_DATABASE, auth=(NEO4J_USER, NEO4J_PASSWORD))
    with driver.session() as session:
        
        schemaNeo4j()
        cypher = ""
        startTimedb = datetime.now()
        print(f'START TIME PROCESSING PDF FILE TO DB: {startTimedb}')

        #Extract document name from doc_location, removing '.pdf' extension
        doc_name_val = os.path.basename(doc_location)[:-4]
        doc_url_val = doc_location
        doc_url_hash_val = hashlib.md5(doc_url_val.encode("utf-8")).hexdigest()

        #Create Document node
        countDocument = 0
        cypher = cypher_pool[0]
        session.run(cypher, doc_url_hash_val=doc_url_hash_val, doc_url_val=doc_url_val, doc_name_val=doc_name_val)

        #Create Section nodes
        countSection = 0
        for sec in doc.sections():
            sec_title_val = sec.title
            sec_title_hash_val = hashlib.md5(sec_title_val.encode("utf-8")).hexdigest()
            sec_tag_val = sec.tag
            sec_level_val = sec.level
            sec_page_idx_val = sec.page_idx
            sec_block_idx_val = sec.block_idx

            #Merge Section nodes
            if not sec_tag_val == 'table':
                cypher = cypher_pool[1]
                session.run(cypher, page_idx_val=sec_page_idx_val
                                , title_hash_val=sec_title_hash_val
                                , title_val=sec_title_val
                                , tag_val=sec_tag_val
                                , level_val=sec_level_val
                                , block_idx_val=sec_block_idx_val
                                , doc_name_val=doc_name_val
                                , doc_url_hash_val=doc_url_hash_val)

                #Create Relationship [:HAS_DOCUMENT] or [:UNDER_SECTION] for Section nodes
                sec_parent_val = str(sec.parent.to_text())

                #[:HAS_DOCUMENT] Relationship 
                if sec_parent_val == "None":
                    cypher = cypher_pool[2]
                    session.run(cypher, page_idx_val=sec_page_idx_val
                                    , title_hash_val=sec_title_hash_val
                                    , doc_url_hash_val=doc_url_hash_val
                                    , block_idx_val=sec_block_idx_val
                                    , doc_name_val=doc_name_val)
                #[:UNDER_SECTION] Relationship
                else:
                    sec_parent_title_hash_val = hashlib.md5(sec_parent_val.encode("utf-8")).hexdigest()
                    sec_parent_page_idx_val = sec.parent.page_idx
                    sec_parent_block_idx_val = sec.parent.block_idx

                    cypher = cypher_pool[3]
                    session.run(cypher, page_idx_val=sec_page_idx_val
                                    , title_hash_val=sec_title_hash_val
                                    , block_idx_val=sec_block_idx_val
                                    , parent_page_idx_val=sec_parent_page_idx_val
                                    , parent_title_hash_val=sec_parent_title_hash_val
                                    , parent_block_idx_val=sec_parent_block_idx_val
                                    , doc_url_hash_val=doc_url_hash_val
                                    , doc_name_val=doc_name_val)
            countSection += 1

        #Create Chunk nodes
        countChunk = 0
        for chk in doc.chunks():
            chunk_block_idx_val = chk.block_idx
            chunk_page_idx_val = chk.page_idx
            chunk_tag_val = chk.tag
            chunk_level_val = chk.level
            chunk_sentences = "\n".join(chk.sentences)

            #Merge Chunk nodes
            if not chunk_tag_val == 'table':
                chunk_sentences_hash_val = hashlib.md5(chunk_sentences.encode("utf-8")).hexdigest()

                cypher = cypher_pool[4]
                session.run(cypher, sentences_hash_val=chunk_sentences_hash_val
                                , sentences_val=chunk_sentences
                                , block_idx_val=chunk_block_idx_val
                                , page_idx_val=chunk_page_idx_val
                                , tag_val=chunk_tag_val
                                , level_val=chunk_level_val
                                , doc_name_val=doc_name_val
                                , doc_url_hash_val=doc_url_hash_val)

                #Create Relationship [:HAS_PARENT] from Chunk nodes
                chk_parent_val = str(chk.parent.to_text())
                if not chk_parent_val == "None":
                    chk_parent_hash_val = hashlib.md5(chk_parent_val.encode("utf-8")).hexdigest()
                    chk_parent_page_idx_val = chk.parent.page_idx
                    chk_parent_block_idx_val = chk.parent.block_idx

                    cypher = cypher_pool[5]
                    session.run(cypher, sentences_hash_val=chunk_sentences_hash_val
                                    , block_idx_val=chunk_block_idx_val
                                    , parent_hash_val=chk_parent_hash_val
                                    , parent_block_idx_val=chk_parent_block_idx_val
                                    , doc_name_val=doc_name_val
                                    , doc_url_hash_val=doc_url_hash_val)
            countChunk += 1

        #Create Table nodes
        countTable = 0
        for tb in doc.tables():
            page_idx_val = tb.page_idx
            block_idx_val = tb.block_idx
            name_val = 'block#' + str(block_idx_val) + '_' + tb.name
            html_val = tb.to_html()
            rows_val = len(tb.rows)

            #Merge Table nodes
            cypher = cypher_pool[6]
            session.run(cypher, block_idx_val=block_idx_val
                            , page_idx_val=page_idx_val
                            , name_val=name_val
                            , html_val=html_val
                            , rows_val=rows_val
                            , doc_name_val=doc_name_val
                            , doc_url_hash_val=doc_url_hash_val)

            #Create Relationship [:HAS_PARENT] from Table nodes to Section nodes
            table_parent_val = str(tb.parent.to_text())
            if not table_parent_val == "None":
                table_parent_hash_val = hashlib.md5(table_parent_val.encode("utf-8")).hexdigest()
                table_parent_page_idx_val = tb.parent.page_idx
                table_parent_block_idx_val = tb.parent.block_idx

                cypher = cypher_pool[7]
                session.run(cypher, name_val=name_val
                                , block_idx_val=block_idx_val
                                , parent_page_idx_val=table_parent_page_idx_val
                                , parent_hash_val=table_parent_hash_val
                                , parent_block_idx_val=table_parent_block_idx_val
                                , doc_name_val=doc_name_val
                                , doc_url_hash_val=doc_url_hash_val)
                
            #Create Relationship [:HAS_PARENT] from Table nodes to Document nodes
            else:
                cypher = cypher_pool[8]
                session.run(cypher, name_val=name_val
                                , block_idx_val=block_idx_val
                                , doc_name_val=doc_name_val
                                , doc_url_hash_val=doc_url_hash_val)
            countTable += 1
        countDocument += 1

        print('DOCUMENT PROCESSED')
        print('-----------------------------------------------------------------')
        print(f'\'{doc_name_val}\' SUMMARY: ')
        print('SECTIONS: ' + str(countSection))
        print('CHUNKS: ' + str(countChunk))
        print('TABLES: ' + str(countTable))
        print(f'Total time: {datetime.now() - startTimedb}')
        print('-----------------------------------------------------------------')
    print('TOTAL DOCUMENTS PROCESSED:'+' '+str(countDocument))
    
    driver.close()

def move_file_to_loaded_folder(filename):
    if not os.path.exists(file_destination):
        os.makedirs(file_destination)
    shutil.move(filename, os.path.join(file_destination, os.path.basename(filename)))

def main():
    schemaNeo4j()
    pdf_files = glob.glob(file_location + '/*.pdf')
    print('-----------------------------------------------------------------')
    print(f'TOTAL PDF FILES FOUND: {len(pdf_files)}')

    pdf_reader = LayoutPDFReader(llmsherpa_api_url)
    startTime = datetime.now()
    print(f'START TIME: {startTime}')
    for pdf_file in pdf_files:
        try:
            doc = pdf_reader.read_pdf(pdf_file)

            json_filename = os.path.splitext(pdf_file)[0] + '.json'

            with open(json_filename, 'w') as f:
                f.write(str(doc.json))
                
            processpdfNeo4j(doc, pdf_file)
            move_file_to_loaded_folder(pdf_file)

            print(f'Moving file to /dataloaded folder...')
            os.remove(json_filename)

        except Exception as e:
            print(f"An error occurred while processing {pdf_file}: {e}")
    print(f'Total time: {datetime.now() - startTime}')
    print('-----------------------------------------------------------------')
    print('DATA LOADING PROCESS COMPLETED')

if __name__ == "__main__":
    main()
