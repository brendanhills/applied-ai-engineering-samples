# Copyright 2024 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.



import asyncio
import asyncpg
import pandas as pd
import numpy as np
from pgvector.asyncpg import register_vector
from google.cloud.sql.connector import Connector
from langchain_community.embeddings import VertexAIEmbeddings
from google.cloud import bigquery
from dbconnectors import pgconnector
from agents import EmbedderAgent
from sqlalchemy.sql import text
from utilities import VECTOR_STORE,PG_SCHEMA, PROJECT_ID, PG_INSTANCE, PG_DATABASE, PG_USER, PG_PASSWORD, PG_REGION, BQ_OPENDATAQNA_DATASET_NAME, DATA_SOURCE, BQ_REGION, EMBEDDING_MODEL

import logging
logger = logging.getLogger(__name__)

embedder = EmbedderAgent(EMBEDDING_MODEL)
 
async def store_schema_embeddings(table_details_embeddings, 
                            tablecolumn_details_embeddings, 
                            project_id,
                            instance_name,
                            database_name,
                            schema,
                            database_user,
                            database_password,
                            region,
                            VECTOR_STORE):
    """ 
    Store the vectorised table and column details in the DB table.
    This code may run for a few minutes.  
    """

    if VECTOR_STORE == "cloudsql-pgvector":
    
        loop = asyncio.get_running_loop()
        async with Connector(loop=loop) as connector:
            # Create connection to Cloud SQL database.
            conn: asyncpg.Connection = await connector.connect_async(
                f"{project_id}:{region}:{instance_name}",  # Cloud SQL instance connection name
                "asyncpg",
                user=f"{database_user}",
                password=f"{database_password}",
                db=f"{database_name}",
            )

            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            await register_vector(conn)

            # await conn.execute(f"DROP SCHEMA IF EXISTS {pg_schema} CASCADE")        

            # await conn.execute(f"CREATE SCHEMA {pg_schema}")        

            # await conn.execute("DROP TABLE IF EXISTS table_details_embeddings")
            # Create the `table_details_embeddings` table to store vector embeddings.
            await conn.execute(
                """CREATE TABLE IF NOT EXISTS table_details_embeddings(
                                    source_type VARCHAR(100) NOT NULL,
                                    table_schema VARCHAR(1024) NOT NULL,
                                    table_name VARCHAR(1024) NOT NULL,
                                    content TEXT,
                                    embedding vector(768))"""
            )

            # Store all the generated embeddings back into the database.
            for index, row in table_details_embeddings.iterrows():
                await conn.execute(
                    f"""
                    DELETE FROM table_details_embeddings
                    WHERE
                    table_schema = '{row["table_schema"]}'
                    and
                    table_name = '{row["table_name"]}';
                    """
                )
                await conn.execute(
                    "INSERT INTO table_details_embeddings (source_type,table_schema, table_name, content, embedding) VALUES ($1, $2, $3, $4, $5)",
                    DATA_SOURCE,
                    row["table_schema"],
                    row["table_name"],
                    row["content"],
                    np.array(row["embedding"]),
                )

            # await conn.execute("DROP TABLE IF EXISTS tablecolumn_details_embeddings")
            # Create the `table_details_embeddings` table to store vector embeddings.
            await conn.execute(
                """CREATE TABLE IF NOT EXISTS tablecolumn_details_embeddings(
                                    source_type VARCHAR(100) NOT NULL,
                                    table_schema VARCHAR(1024) NOT NULL,
                                    table_name VARCHAR(1024) NOT NULL,
                                    column_name VARCHAR(1024) NOT NULL,
                                    content TEXT,
                                    embedding vector(768))"""
            )

            # Store all the generated embeddings back into the database.
            for index, row in tablecolumn_details_embeddings.iterrows():
                await conn.execute(
                    f"""
                    DELETE FROM tablecolumn_details_embeddings
                    WHERE table_schema = '{row["table_schema"]}'
                    and
                    table_name = '{row["table_name"]}'
                    and 
                    column_name = '{row["column_name"]}';
                    """
                )
                await conn.execute(
                    "INSERT INTO tablecolumn_details_embeddings (source_type,table_schema, table_name, column_name, content, embedding) VALUES ($1, $2, $3, $4, $5, $6)",
                    DATA_SOURCE,
                    row["table_schema"],
                    row["table_name"],
                    row["column_name"],
                    row["content"],
                    np.array(row["embedding"]),
                )
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            await register_vector(conn)

            # await conn.execute("DROP TABLE IF EXISTS example_prompt_sql_embeddings")
            await conn.execute(
                        """CREATE TABLE IF NOT EXISTS example_prompt_sql_embeddings(
                                            table_schema VARCHAR(1024) NOT NULL,
                                            example_user_question text NOT NULL,
                                            example_generated_sql text NOT NULL,
                                            embedding vector(768))"""
                        )

            await conn.close()


    elif VECTOR_STORE == "bigquery-vector": 
         
        client=bigquery.Client(project=project_id)

        #Store table embeddings
        client.query_and_wait(f'''CREATE TABLE IF NOT EXISTS `{project_id}.{schema}.table_details_embeddings` (
            source_type string NOT NULL, table_schema string NOT NULL, table_name string NOT NULL, content string, embedding ARRAY<FLOAT64>)''')
        #job_config = bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE")
        table_details_embeddings['source_type']=DATA_SOURCE
        table_name_list = []
        for _, row in table_details_embeddings.iterrows():
            table_name_list.append("'"+row["table_name"]+"'")
        table_name_string = ",".join(table_name_list)
        query_string = f''' DELETE FROM `{project_id}.{schema}.table_details_embeddings` WHERE table_schema = '{row["table_schema"]}' AND table_name IN( {table_name_string} )'''

        logger.info(f'Clean up table_details_embeddings: {query_string=}')
        client.query_and_wait(query_string)

        logger.info(f"Storing table embeddings to BQ {project_id}.{schema}.table_details_embeddings'")
        client.load_table_from_dataframe(table_details_embeddings,f'{project_id}.{schema}.table_details_embeddings')

        #Store column embeddings
        client.query_and_wait(f'''CREATE TABLE IF NOT EXISTS `{project_id}.{schema}.tablecolumn_details_embeddings` (
            source_type string NOT NULL, table_schema string NOT NULL, table_name string NOT NULL, column_name string NOT NULL,
            content string, embedding ARRAY<FLOAT64>)''')
        
        column_query_string = f'''DELETE FROM `{project_id}.{schema}.tablecolumn_details_embeddings` WHERE table_schema = '{row["table_schema"]}' AND table_name IN( {table_name_string}) '''
        logger.info(f'Clean up tablecolumn_details_embeddings: {column_query_string=}')
        logger.debug(column_query_string)
        client.query_and_wait(column_query_string)

        #job_config = bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE")
        tablecolumn_details_embeddings['source_type']=DATA_SOURCE
        #for _, row in tablecolumn_details_embeddings.iterrows():
        #    query_string = f'''DELETE FROM `{project_id}.{schema}.tablecolumn_details_embeddings`
        #            WHERE table_schema= '{row["table_schema"]}' and table_name= '{row["table_name"]}' and column_name= '{row["column_name"]}' '''
        #                
        #    logger.info(f'Delete tablecolumn_details_embeddings row: {query_string=} ')
        #    client.query_and_wait(query_string)
  

        logger.info(f"Storing column embeddings to BQ {project_id}.{schema}.tablecolumn_details_embeddings")
        client.load_table_from_dataframe(tablecolumn_details_embeddings,f'{project_id}.{schema}.tablecolumn_details_embeddings')


        client.query_and_wait(f'''CREATE TABLE IF NOT EXISTS `{project_id}.{schema}.example_prompt_sql_embeddings` (
                              table_schema string NOT NULL, example_user_question string NOT NULL, example_generated_sql string NOT NULL,
                              embedding ARRAY<FLOAT64>)''')
                              
    else: raise ValueError("Please provide a valid Vector Store.")
    return "Embeddings are stored successfully"

async def add_sql_embedding(user_question, generated_sql, database):
        
        emb=embedder.create(user_question)

        if VECTOR_STORE == "cloudsql-pgvector":
        #    sql=  f'''MERGE INTO example_prompt_sql_embeddings as tgt
        #    using (SELECT '{user_question}' as example_user_question) as src 
        #    on tgt.example_user_question=src.example_user_question 
        #    when not matched then
        #    insert (table_schema, example_user_question,example_generated_sql,embedding) 
        #    values('{database}','{user_question}','{generated_sql}','{(emb)}')
        #    when matched then update set
        #    table_schema = '{database}',
        #    example_generated_sql = '{generated_sql}',
        #    embedding = '{(emb)}' '''

        # #    print(sql)
        #    conn=pgconnector.pool.connect()
        #    await conn.execute(text(sql))
        #    pgconnector.retrieve_df(sql)
            loop = asyncio.get_running_loop()
            async with Connector(loop=loop) as connector:
                    # Create connection to Cloud SQL database.
                conn: asyncpg.Connection = await connector.connect_async(
                        f"{PROJECT_ID}:{PG_REGION}:{PG_INSTANCE}",  # Cloud SQL instance connection name
                        "asyncpg",
                        user=f"{PG_USER}",
                        password=f"{PG_PASSWORD}",
                        db=f"{PG_DATABASE}",
                    )

                await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
                await register_vector(conn)

                await conn.execute("DELETE FROM example_prompt_sql_embeddings WHERE table_schema= $1 and example_user_question=$2",
                                    database,
                                    user_question)
                cleaned_sql =generated_sql.replace("\n", " ")
                
                await conn.execute(
                                "INSERT INTO example_prompt_sql_embeddings (table_schema, example_user_question, example_generated_sql, embedding) VALUES ($1, $2, $3, $4)",
                                database,
                                user_question,
                                cleaned_sql,
                                np.array(emb),
                            )

        elif VECTOR_STORE == "bigquery-vector":

            client=bigquery.Client(project=PROJECT_ID)
        
            client.query_and_wait(f'''CREATE TABLE IF NOT EXISTS `{PROJECT_ID}.{BQ_OPENDATAQNA_DATASET_NAME}.example_prompt_sql_embeddings` (
                table_schema string NOT NULL, example_user_question string NOT NULL, example_generated_sql string NOT NULL,
                embedding ARRAY<FLOAT64>)''')
            client.query_and_wait(f'''DELETE FROM `{PROJECT_ID}.{BQ_OPENDATAQNA_DATASET_NAME}.example_prompt_sql_embeddings`
                                WHERE table_schema= '{database}' and example_user_question= '{user_question}' '''
                                    )
                        # embedding=np.array(row["embedding"])
            cleaned_sql = generated_sql.replace("\n", " ")

            client.query_and_wait(f'''INSERT INTO `{PROJECT_ID}.{BQ_OPENDATAQNA_DATASET_NAME}.example_prompt_sql_embeddings` 
                        VALUES ("{database}","{user_question}" , 
                        "{cleaned_sql}",{emb})''')
        return 1



if __name__ == '__main__': 
    from retrieve_embeddings import retrieve_embeddings
    from utilities import PG_SCHEMA, PROJECT_ID, PG_INSTANCE, PG_DATABASE, PG_USER, PG_PASSWORD, PG_REGION
    VECTOR_STORE = "cloudsql-pgvector"
    t, c = retrieve_embeddings(VECTOR_STORE, PG_SCHEMA) 
    asyncio.run(store_schema_embeddings(t, 
                            c, 
                            PROJECT_ID,
                            PG_INSTANCE,
                            PG_DATABASE,
                            PG_SCHEMA,
                            PG_USER,
                            PG_PASSWORD,
                            PG_REGION,
                            VECTOR_STORE = VECTOR_STORE))




# # TODO: Optional: to embed and store currently generated and working SQL 
# def pg_embed_new_sql(user_question, generated_sql):
#   try:
#     embeddings_service = VertexAIEmbeddings()

#     desc = f"""example_user_question: {user_question} | example_generated_sql: {generated_sql}"""
#     dict_exp = {"prompt": user_question,"sql": generated_sql, "detailed_description": desc}
#     sql_example_df = pd.DataFrame(dict_exp, index=[0])
#     example_sql_details_chunked = []
#     for index, row in sql_example_df.iterrows():
#         example_user_question = row["prompt"]
#         example_generated_sql = row["sql"]
#         detailed_description = row["detailed_description"]
#         r = {"example_user_question": example_user_question,"example_generated_sql": example_generated_sql,"content": detailed_description}
#         example_sql_details_chunked.append(r)

#     print("example_sql_details_chunked: "+ str(example_sql_details_chunked))

#     for chunk in example_sql_details_chunked:
#       request = chunk["content"]
#       response = text_embedding(request)
#       print("request: "+ request)
#       chunk["embedding"] = response

#     # Store the generated embeddings in a pandas dataframe.
#     example_prompt_sql_embeddings = pd.DataFrame(example_sql_details_chunked)
#     return example_prompt_sql_embeddings
#   except Exception as e:
#     print("Issue while creating the embedding!! ")
#     print(str(e))
#     return 0

