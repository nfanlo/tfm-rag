# TFM-RAG

### Description:

The project involves creating a database through PDF files in Neo4j regarding contracts and insurance policies of clients from an insurance company.
Once the above is achieved. utilize Retriever-Augmented Generation (RAG) to converse about the ingested documents in Neo4j through an application created using the Streamlit framework.

### Dev Instructions:
To clone the repository navigate to the destination folder in the terminal and clone the repository type the following on terminal:

For macOS/Windows:

```
git clone <repository_url>
```

Once the repository is cloned install Miniconda on your local machine.

### **Install [Miniconda](https://docs.anaconda.com/free/miniconda/index.html)**

After install Miniconda locally, navigate through the terminal to the cloned repository, execute the yaml file (env.yml) with the following command:

For macOS/Windows:

```
conda env create -f env.yml
````

Running this code will create a new conda environment called tfm-rag with python3.11 installing the necessary libraries for the project available in the requirements.txt file of the project

After installing the project's requirements.txt. Create a folder named config and inside it create a file named config.py with the following:

```python
config = {
    "openai_api_key": "YOUR_OPENAI_API_KEY",
    "neo4j_url": "YOUR_NEO4J_DATABASE_URL",
    "neo4j_password": "YOUR_NEO4J_DATABASE_PASSWORD",
    "llmsherpa_api_url": "YOUR_LLMSHERPA_API_URL"}
```

In the src/load-data-neo4j folder the following files exist:

1. load-data.py: This file will utilize the PDF files in the /newdata folder and upload them to the corresponding Neo4j database, creating the necessary nodes and relationships for the project. Once the corresponding PDF files are preprocessed, they will be moved to the /data-loaded folder of the project. To execute the load-data.py file navigate to the directory where the file is located and run the following command in the terminal with the project's environment activated:
   
```
python load_data.py
```

2. data-embedding.py: This .py file will utilize the nodes and relationships created in the preprocessing of files to create the embeddings necessary for later use with RAG on the Neo4j database. To execute the data-embedding.py file ensure you have completed step 1 and once the process is complete, type the following in the terminal:

```
python embedding_data.py
````

Once this process of data ingestion and transformation into embeddings is completed, proceed to the next steps.

To run the chatbot application created with Streamlit navigate to the project's src/streamlit folder once the file ingestion into Neo4j is finished and type the following in the terminal:

```
python -m streamlit run tfm_api.py
```
