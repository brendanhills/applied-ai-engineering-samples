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


import json 
from abc import ABC
from .core import Agent 
from vertexai.generative_models import HarmCategory, HarmBlockThreshold

import logging
logger = logging.getLogger(__name__)

class ResponseAgent(Agent, ABC):
    """
    An agent that generates natural language responses to user questions based on SQL query results.

    This agent acts as a data assistant, interpreting SQL query results and transforming them into user-friendly, natural language answers. It utilizes a language model (currently Gemini) to craft responses that effectively convey the information derived from the data.

    Attributes:
        agentType (str): Indicates the type of agent, fixed as "ResponseAgent".

    Methods:
        run(user_question, sql_result) -> str:
            Generates a natural language response to the user's question based on the SQL query result.

            Args:
                user_question (str): The question asked by the user in natural language.
                sql_result (str): The result of the SQL query executed to answer the question.

            Returns:
                str: The generated natural language response.
    """


    agentType: str = "ResponseAgent"

    # TODO: Make the LLM Validator optional
    def run(self, user_question, sql_result):

        context_prompt = f"""

            You are a Data Assistant that helps to answer users' questions on their data within their databases.
            The user has provided the following question in natural language: "{str(user_question)}"

            The system has returned the following result after running the SQL query: "{str(sql_result)}".

            Provide a natural sounding response to the user to answer the question with the SQL result provided to you.
        """

        logger.debug(f"{self.model_id=}")
        if self.model_id.startswith('gemini'):
            context_query = self.model.generate_content(context_prompt, stream=False)
            generated_sql = str(context_query.candidates[0].text)

        else:
            context_query = self.model.predict(context_prompt, max_output_tokens = 8000, temperature=0)
            generated_sql = str(context_query.candidates[0])
        
        return generated_sql

    