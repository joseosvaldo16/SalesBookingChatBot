import os
import re
import json
import csv
import ast
import tiktoken
import aioodbc
from pyodbc import Cursor
import pyodbc
import logging
import asyncio
import pandas as pd
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from io import StringIO, BytesIO
from typing import List, Tuple
from ..models import UserProfile
from botbuilder.core import CardFactory
from azure.storage.blob.aio import BlobServiceClient
from langchain_community.vectorstores.faiss import FAISS
from azure.storage.blob import BlobSasPermissions, generate_blob_sas
from botbuilder.schema import Attachment, Activity, ActivityTypes
from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings
from .gpt_prompts import GPTPrompts
from botbuilder.dialogs import WaterfallStepContext
from config import DatabaseConfig as DB_CONFIG  # Ensure this is correctly imported


class BotUtilities:
    """
    A utility class containing helper methods for the SQLQueryBot.
    """
    def __init__(self, blob_service_client: BlobServiceClient, container_name: str, gpt: AzureChatOpenAI, embedder: AzureOpenAIEmbeddings):
        """
        Initializes the BotUtilities with necessary configurations.

        :param blob_connection_string: Azure Blob Storage connection string.
        :param container_name: Name of the Azure Blob Storage container.
        """
        self.blob_service_client = blob_service_client
        self.container_name = container_name
        self.gpt = gpt
        self.embedder = embedder
        self.container_name = container_name

    # -------------------- Static Utility Methods --------------------
    @staticmethod
    async def process_matched_columns(result_dict, initial_query):
        """
        Processes the result dictionary to generate context, prompts, and confirmation sentences.

        :param result_dict: Dictionary mapping filter values to matching vector dbs and search results.
        :param initial_query: The initial query string provided by the user.
        :return: Tuple of (initial_wContext, response)
        """
        logging.info("Processing matched columns...")
        # Mapping from vector db names to column names
        vector_db_to_column = {
            "Column1_Name_faiss_index": "Column1_Name",        #In this example, the vector db names have the format "Column_Name_faiss_index"
            "Column2_Name_faiss_index": "Column2_Name",        #You can replace these with the actual column names in your database
            "Column3_Name_faiss_index": "Column3_Name",        #And names of the FAISS vector dbs in your system
            "Column4_Name_faiss_index": "Column4_Name",        #Vector dbs contain the unique values for the corresponding column
            "Column5_Name_faiss_index": "Column5_Name",
            "Column6_Name_faiss_index": "Column6_Name",
            "Column7_Name_faiss_index": "Column7_Name",
        }
        # Initialize lists to store context, prompts, and confirmation sentences
        context_parts = []
        prompt_parts = []
        confirmation_parts = []

        # List of all column names for prompts
        all_columns = list(vector_db_to_column.values())

        # Create a list of tasks for each filter value to process concurrently
        tasks = [
            asyncio.create_task(BotUtilities.process_filter_value(vector_db_to_column, filter_value, context_parts, confirmation_parts, prompt_parts, all_columns, data))
            for filter_value, data in result_dict.items()
        ]

        # Run all tasks concurrently
        await asyncio.gather(*tasks)

        # Combine context parts into one string
        context = ', '.join(context_parts) if context_parts else None

        if context:
            initial_wContext = f"{initial_query} {context}"
        else:
            initial_wContext = initial_query

        # Combine prompt parts into one response
        sentences = '\n'.join(prompt_parts) if prompt_parts else None

        # Combine confirmation parts into one response
        confirmations = '\n'.join(confirmation_parts) if confirmation_parts else None

        # Prepare the final response
        if confirmations and sentences:
            # Add a newline between confirmations and sentences
            response = f"{confirmations}\n\n{sentences}"
        elif confirmations:
            response = confirmations
        elif sentences:
            response = sentences
        else:
            response = None

        return initial_wContext, response
    
    # Define an asynchronous function to process each filter value
    @staticmethod
    async def process_filter_value(vector_db_to_column,filter_value,context_parts,confirmation_parts,prompt_parts, all_columns, data):
        """
        Processes a filter value to generate context, prompts, and confirmation sentences.

        :param vector_db_to_column: Mapping from vector db names to column names.
        :param filter_value: The filter value to process.
        :param context_parts: List to store context parts.
        :param confirmation_parts: List to store confirmation sentences.
        :param prompt_parts: List to store prompt sentences.
        :param all_columns: List of all column names for prompts.
        :param data: The data dictionary for the filter value.
        :return: None.
        """
        matching_vector_dbs = data['matching_vector_dbs']

        if len(matching_vector_dbs) == 1:
            # Only one vector db matched
            vector_db_name = matching_vector_dbs[0]
            column_name = vector_db_to_column.get(vector_db_name, vector_db_name)
            # Add to context
            context_parts.append(f"('{filter_value}': {column_name})")
            # Add to confirmation sentences
            confirmation_sentence = f"**{column_name}** will be used to filter on **{filter_value}**.\n\n"
            confirmation_parts.append(confirmation_sentence)
        elif len(matching_vector_dbs) > 1:
            # Multiple vector dbs matched
            columns = [vector_db_to_column.get(db_name, db_name) for db_name in matching_vector_dbs]
            # Create prompt asking user to clarify
            columns_list = ', '.join(f"'{col}'" for col in columns)
            prompt = (
                f"The filter value *'{filter_value}'* matched multiple columns. "
                f"Please clarify if it refers to \n\n{columns_list}.\n\n"
            )
            prompt_parts.append(prompt)
        else:
            # No matches were made; ask the user if the filter refers to any of all columns
            columns_list = ', '.join(f"'{col}'" for col in all_columns)
            prompt = (
                f"The filter value *'{filter_value}'* did not match any known columns. "
                f"Please clarify if it refers to any of the following columns:\n\n{columns_list}.\n\n"
            )
            prompt_parts.append(prompt)
    
    @staticmethod
    def compare_headers_to_results(headers, results) -> list:
        """
        Compares the headers to the results and prompts the user to select the correct values if necessary.

        :param headers: A list of header strings.
        :param results: A list of result rows.
        :return: A list containing a boolean indicating if selection is required and a message string.
        """

        logging.info("Comparing headers to results...")
        def clean_string(s):
            # Remove punctuation, spaces, dashes, and numbers, and convert to lowercase
            return re.sub(r'[^\w\s]', '', s).replace('-', '').replace(' ', '').lower()

        # Mapping of special exceptions
        # These will be used to match (replace) values for which we dont have a database for 
        exceptions = {
            'US': 'United States',
            'The United States': 'United States',
            'USA': 'United States',
            'UK': 'United Kingdom',
            'The United Kingdom': 'United Kingdom',
            'UAE': 'United Arab Emirates',
            'Virgin Islands': 'Virgin Islands (U.S.)', 
            'The Virgin Islands': 'Virgin Islands (U.S.)',
        }

        result_messages = []
        option_counter = 1  # Start the numbering for options
        selection_required = False
        # Iterate through using the index to access both headers and results columns
        for i, header in enumerate(headers):
            matching_result = None
            options = []
            #Iterate through each row
            for row in results:
                if i < len(row) and row[i]:  # Ensure the row has enough columns and the column is not empty
                    # Use the i-th column value as the first result. Index corresponds to the column in the result set
                    first_result = row[i] # Get the first result for the current header
                    clean_header = clean_string(header) # Clean the header of special characters
                    clean_result = clean_string(first_result) # Clean the result of special characters
                    # Check for exception match
                    if clean_header in exceptions:
                        matching_result = f"The value '{header}' matched with **'{exceptions[clean_header]}'** in the database and will be used accordingly\n"
                        break
                    # Check for exact match
                    elif (clean_header == clean_result):
                        matching_result = f"The value '{header}' matched with **'{first_result}'** in the database and will be used accordingly\n"
                        break
                    # If no matches
                    else:
                        options.append(first_result)

            if matching_result:
                result_messages.append(matching_result)
            else:
                # If no exact match, prompt the user to choose from the search results
                if options:
                    
                    logging.info(f"\n\nOptions_Counter:'{option_counter}'\n\nOptions Length:{len(options)}\n\n")
                    selection_required = True
                    options_str = "\n".join([f"{option_counter + j}. {option}" for j, option in enumerate(options)])
                    result_message = (
                        f"\n\nThe header **'{header}'** did not have an exact match or may have multiple possible matches. Please select one or more of the following options\n\n"
                        f"{options_str}\n"
                    )
                    result_messages.append(result_message)
                    option_counter = option_counter + len(options)
                else:
                    result_messages.append(None)

        if selection_required:
            result_messages.append("You can enter the number(s) corresponding to your choice(s). These are only the top 6 similar values. You may ask to select all values that contain a specific word(s) to select more:\n")

        all_messages = "\n".join([message for message in result_messages if message is not None])
        return [selection_required, all_messages]

    @staticmethod
    def clean_sql_query(query: str) -> str:
        """
        Cleans the SQL query by removing code block markers and trimming whitespace.

        :param query: The raw SQL query string.
        :return: Cleaned SQL query string.
        """
        return query.replace("```sql", "").replace("```", "").strip()

    @staticmethod
    def num_tokens_from_messages(messages: List[dict], encoding_name: str = 'gpt-4-0613') -> int:
        """
        Calculates the number of tokens from a list of messages for a given encoding model.

        :param messages: A list of message dictionaries.
        :param encoding_name: The name of the encoding model.
        :return: Total number of tokens.
        """
        encoding = tiktoken.encoding_for_model(encoding_name)
        tokens_per_message = 3
        tokens_per_name = 1
        num_tokens = 0
        for message in messages:
            num_tokens += tokens_per_message
            for key, value in message.items():
                num_tokens += len(encoding.encode(value))
                if key == "name":
                    num_tokens += tokens_per_name
        num_tokens += 3  # Every reply is primed with <|start|>assistant<|message|>
        return num_tokens

    @staticmethod
    def format_sql_query(query: str) -> str:
        """
        Formats the SQL query by adding line breaks before major keywords.

        :param query: The raw SQL query string.
        :return: Formatted SQL query string.
        """
        keywords = [
            'SELECT', 'FROM', 'WHERE', 'GROUP BY', 'ORDER BY',
            'HAVING', 'JOIN', 'INNER JOIN', 'LEFT JOIN', 'RIGHT JOIN', 'OUTER JOIN'
        ]
        for keyword in keywords:
            query = re.sub(f"\\b{keyword}\\b", f"\n  {keyword}", query, flags=re.IGNORECASE)
        return query.lstrip()

    @staticmethod
    def format_cell_data(cell) -> str:
        """
        Formats cell data based on its type.

        :param cell: The cell data to format.
        :return: Formatted cell data as a string.
        """
        if isinstance(cell, date):
            return cell.strftime("%Y-%m-%d")
        elif isinstance(cell, Decimal):
            formatted_number = "{:,.2f}".format(cell.quantize(Decimal('0.01')))
            return formatted_number
        elif isinstance(cell, float):
            return f"{cell:.2f}"
        return str(cell)

    @staticmethod
    def format_result_for_adaptive_card(result_set: List[Tuple], headers: List[str]) -> dict:
        """
        Formats the result set into an adaptive card table structure.

        :param result_set: The query results as a list of tuples.
        :param headers: The list of header strings.
        :return: A dictionary representing the adaptive card table.
        """
        logging.info("Formatting results for adaptive card...")
        adaptive_card_table = {
            "type": "Table",
            "columns": [{"width": "stretch"} for _ in headers],
            "rows": []
        }

        # Create header row with error handling
        header_cells = []
        for header in headers:
            try:
                formatted_header = BotUtilities.format_cell_data(header)
            except Exception as e:
                logging.error(f"Error formatting header cell data: {e}")
                formatted_header = str(header)
            header_cells.append({
                "type": "TableCell",
                "items": [{
                    "type": "TextBlock",
                    "text": formatted_header,
                    "wrap": True,
                    "color": "dark",
                    "weight": "Bolder"
                }]
            })
        adaptive_card_table["rows"].append({"type": "TableRow", "cells": header_cells})

        # Handle special case where result_set contains non-row data (error message)
        if result_set and not isinstance(result_set[0], pyodbc.Row):
            error_message = result_set
            table_cell = {
                "type": "TableCell",
                "items": [{
                    "type": "TextBlock",
                    "text": str(error_message),
                    "wrap": True,
                    "color": "attention",  # Highlight error message
                    "weight": "default"
                }]
            }
            adaptive_card_table["rows"].append({"type": "TableRow", "cells": [table_cell]})
            return adaptive_card_table

        # Add data rows
        for row in result_set:
            table_cells = []
            for cell in row:
                try:
                    formatted_cell = BotUtilities.format_cell_data(cell)
                except Exception as e:
                    logging.error(f"Error formatting cell data: {e}")
                    formatted_cell = str(cell)
                table_cells.append({
                    "type": "TableCell",
                    "items": [{
                        "type": "TextBlock",
                        "text": formatted_cell,
                        "wrap": True,
                        "color": "default",
                        "weight": "default"
                    }]
                })
            adaptive_card_table["rows"].append({"type": "TableRow", "cells": table_cells})

        return adaptive_card_table
    
    @staticmethod
    def format_result_for_adaptive_card_teams(initial_query, sql_query, result_set, download_url,headers):
        """
        Formats the result set into multiple adaptive card tables, splitting the columns if necessary, for better display in Teams.

        :param initial_query: The user's initial query.
        :param sql_query: The generated SQL query based on the user's input.
        :param result_set: The query results as a list of tuples.
        :param download_url: A URL to download the results as a CSV file.
        :param headers: A list of column headers.
        :return: A list of adaptive cards containing the formatted results.
        """
        logging.info(f"Formatting results for adaptive card for Teams...")
        # Split headers and result set if there are more than 3 columns
        num_columns_per_card = 5
        chunks = [headers[i:i + num_columns_per_card] for i in range(0, len(headers), num_columns_per_card)]
        result_chunks = [
            [[row[col_idx] for col_idx in range(start_idx, min(start_idx + num_columns_per_card, len(row)))]
            for row in result_set]
            for start_idx in range(0, len(headers), num_columns_per_card)
        ]

        adaptive_cards = []
        for i, (header_chunk, result_chunk) in enumerate(zip(chunks, result_chunks)):
            adaptive_card_table = {
                "type": "Table",
                "columns": [{"width": "stretch"} for _ in header_chunk],
                "rows": []
            }

            # Create header row
            header_row = {
                "type": "TableRow",
                "cells": []
            }
            for header in header_chunk:
                try:
                    formatted_header = BotUtilities.format_cell_data(header)
                except Exception as e:
                    logging.error(f"Error formatting header cell data: {e}")
                    formatted_header = str(header)
                header_row["cells"].append({
                    "type": "TableCell",
                    "items": [{
                        "type": "TextBlock",
                        "text": formatted_header,
                        "wrap": True,
                        "color": "default",
                        "weight": "Bolder"
                    }]
                })
            adaptive_card_table["rows"].append(header_row)

            # Add data rows
            for row in result_chunk:
                table_row = {
                    "type": "TableRow",
                    "cells": []
                }
                for cell in row:
                    try:
                        formatted_cell = BotUtilities.format_cell_data(cell)
                    except Exception as e:
                        logging.error(f"Error formatting cell data: {e}")
                        formatted_cell = str(cell)
                    table_row["cells"].append({
                        "type": "TableCell",
                        "items": [{
                            "type": "TextBlock",
                            "text": formatted_cell,
                            "wrap": True,
                            "color": "default",
                            "weight": "default"
                        }]
                    })
                adaptive_card_table["rows"].append(table_row)

            if i == 0:
                adaptive_card = BotUtilities.create_adaptive_card(initial_query, sql_query, adaptive_card_table, download_url if i == len(chunks) - 1 else None)
            else:
                adaptive_card = BotUtilities.create_adaptive_card(None, None,adaptive_card_table, download_url if i == len(chunks) - 1 else None)
            adaptive_cards.append(adaptive_card)

        return adaptive_cards
    
    @staticmethod
    def create_adaptive_card(
        initial_query: str = None,
        sql_query: str = None,
        formatted_results: dict = None,
        download_url: str = None
    ) -> Attachment:
        """
        Creates an adaptive card with the provided query, SQL, results, and download URL.

        :param initial_query: The user's initial query.
        :param sql_query: The generated SQL query.
        :param formatted_results: The formatted results for display.
        :param download_url: URL to download the results CSV.
        :return: An Attachment object representing the adaptive card.
        """
        logging.info("Creating adaptive card...")
        dir_path = os.path.dirname(os.path.realpath(__file__))  # Directory of the current script

        if initial_query and sql_query:
            file_path = os.path.join(dir_path, 'AdaptiveCard.json')  # Path to the initial query card
        else:
            file_path = os.path.join(dir_path, 'AdaptiveCardResults.json')  # Path to the results-only card

        try:
            with open(file_path, 'r') as file:
                loaded_card = json.load(file)
        except FileNotFoundError:
            logging.error(f"Adaptive card JSON file not found: {file_path}")
            raise

        # Replace placeholders with actual values
        if initial_query and sql_query:
            for item in loaded_card["body"]:
                if item['type'] == "TextBlock":
                    item["text"] = item["text"].replace("{query}", initial_query)
                    item["text"] = item["text"].replace("{sql_query}", sql_query)

        if formatted_results:
            loaded_card["body"].append(formatted_results)

        # Add download button if URL is provided
        if download_url:
            loaded_card["actions"].append({
                "type": "Action.OpenUrl",
                "title": "Download/View Results",
                "url": download_url,
                "style": "positive"
            })

        card = CardFactory.adaptive_card(loaded_card)
        return card
    
    @staticmethod
    async def send_adaptive_card_or_download_link(step: WaterfallStepContext, messages: List[Activity], download_url: str, initial_query: str, formatted_sql: str):
        """
        Sends an adaptive card or, if the result set is too large to display, provides a download link for the user to retrieve the results as a CSV.

        :param step: The WaterfallStepContext instance used to send the message.
        :param messages: A list of Activity objects representing the messages to send.
        :param download_url: A URL to download the query results as a CSV file.
        :param initial_query: The user's initial query.
        :param formatted_sql: The generated SQL query.
        :return: None.
        """
        logging.info("Sending adaptive card or download link...")
        await step.context.send_activity(Activity(type=ActivityTypes.typing))
        try:
            for message in messages:
                await step.context.send_activity(message)
        except Exception as e:
            logging.error(f"Error sending adaptive card: {e}")

            formatted_results = {
                "type": "TextBlock",
                "text": "The results are too large to display here. You can download the CSV file below to view the full results.",
                "wrap": True,
                "color": "attention",
                "size": "medium"
            }
            
            adaptive_card_payload = BotUtilities.create_adaptive_card(initial_query, formatted_sql, formatted_results, download_url)
            # Send the adaptive card with the download button
            await step.context.send_activity(Activity(
                
                type=ActivityTypes.message,
                attachments=[adaptive_card_payload]
            ))
    @staticmethod
    async def search_filter_value(filter_value, vector_dbs):
        """
        Searches for a filter value across all vector databases concurrently.

        :param filter_value: The filter value to search for.
        :param vector_dbs: Dictionary mapping vector_db_name to retriever.

        :return: Tuple of (filter_value, result_dict_entry).
        """
        # Define variables to store the results and matching vector dbs
        matching_vector_dbs = []
        search_results_dict = {}
        # Define an asynchronous function to search in each vector database concurrently
        async def search_in_db(vector_db_name, retriever):
            try:
                # Perform the search in a thread
                search_results = await asyncio.to_thread(retriever.invoke, filter_value)
                # Extract the content from the search results
                result_texts = [result.page_content for result in search_results]
                # Save the search results for this vector db
                search_results_dict[vector_db_name] = result_texts
                # Check for exact match (case-insensitive)
                if any(filter_value.lower() == text.lower() for text in result_texts):
                    matching_vector_dbs.append(vector_db_name)
            except Exception as e:
                logging.error(f"Error searching in vector database '{vector_db_name}': {e}")

        # Create tasks to search all vector dbs concurrently
        tasks = [
            asyncio.create_task(search_in_db(db_name, retriever))
            for db_name, retriever in vector_dbs.items()
        ]

        # Wait for all tasks to complete
        await asyncio.gather(*tasks)

        # Prepare the result for this filter_value
        if matching_vector_dbs:
            # Save search results from matching vector dbs
            filtered_search_results = {
                db_name: search_results_dict[db_name] for db_name in matching_vector_dbs
            }
            result_entry = {
                'matching_vector_dbs': matching_vector_dbs,
                'search_results': filtered_search_results
            }
        else:
            # Save search results from all vector dbs
            result_entry = {
                'matching_vector_dbs': [],
                'search_results': search_results_dict
            }

        return filter_value, result_entry
    

    # -------------------- Instance Utility Methods --------------------
    async def init_container(self):
        """
        Ensures that the Azure Blob Storage container exists. If it does not, the container is created.

        :return: None.
        """
        container_client = self.blob_service_client.get_container_client(self.container_name)
        try:
            await container_client.create_container()
        except Exception as e:
            logging.info(f"Container already exists or error: {e}")
    
    async def has_name_or_product(self, user_input: str):
        """
        Checks if the user profile has a name or location.

        :param user_input: The user's input message.
        :return: True if the user has a name or location thats ambiguous, False otherwise.
        """
        logging.info("Checking if user has name or product...")
        has_name_or_location_prompt = GPTPrompts.prompt_has_name_or_product.format(user_input=user_input)
        response = await self.gpt.ainvoke(has_name_or_location_prompt)
        result = ast.literal_eval(response.content.strip())
        return result
    
    async def check_filter_clarification(self, user_query: str, step_conversation_history: list):
        logging.info("Checking for filter clarification...")
        #Get the prompt from the GPTPrompts
        prompt_check_filter_clarification = GPTPrompts.prompt_check_filter_clarification
        #Set up the system_prompt and user_query messages for the GPT request
        messages = [{"role": "system", "content": prompt_check_filter_clarification},{"role": "user", "content": f"User Query: {user_query}"}]
        #Extend the conversation history with the new messages
        step_conversation_history.extend(messages)
        #Invoke the GPT model with the conversation history 
        gpt_response = await self.gpt.ainvoke(step_conversation_history)
        tuple_response = gpt_response.content
        #Append the result message to the conversation history
        step_conversation_history.append({"role": "assistant", "content": tuple_response})
        logging.info(f"Updated Conversation History In Ask For Clarification:\n\n {step_conversation_history}\n\n")
        #Return the message to the user and the updated step conversation history
        return (str(tuple_response),step_conversation_history)
    
    def get_search_results(self, response) -> list:
        """
        Retrieves search results from a list of vectors and returns a list of keyword lists.

        :param response: A list of corresponding database names and filter values.
        :return: A list of keyword lists.
        """

        logging.info("Getting search results...")
        search_results_df = pd.DataFrame()  # Initialize an empty DataFrame to store results
        current_dir = Path(__file__).resolve().parent
        parent_dir = current_dir.parent
        logging.info(f"Getting directory path")
        vector_stores_path = parent_dir / "Vector_Stores"
        logging.info(f"Search Filters: {response[0]}")
        for i in range(len(response[0])):
            vector_db_name = response[0][i]
            
            # Check if the vector database name is None
            if vector_db_name is None:
                logging.warning(f"Skipping index {i} because the vector database name is None.")
                continue
            
            try:
                keyword_list = []
                vector_db_path = vector_stores_path / vector_db_name
                logging.info(f"Loading vector database: {vector_db_path}")
                vector_db = FAISS.load_local(str(vector_db_path), self.embedder, allow_dangerous_deserialization=True)
                retriever = vector_db.as_retriever(search_kwargs={"k": 6})
                search_results = retriever.invoke(response[1][i])
                
                for result in search_results:
                    keyword_list.append(result.page_content)

                logging.info(f"Converting search results to DataFrame...")
                # Convert the keyword list to a DataFrame
                result_df = pd.DataFrame(keyword_list, columns=[response[1][i]])
                
                # Concatenate the results into the main DataFrame
                if search_results_df.empty:
                    search_results_df = result_df
                else:
                    search_results_df = pd.concat([search_results_df, result_df], axis=1)
                    
            except Exception as e:
                logging.error(f"An error occurred while processing index {i}: {e}")
                continue
        #Make all nan values into the string
        search_results_df = search_results_df.fillna('None')
        return search_results_df.values.tolist()
    
    async def find_matching_columns(self, filter_values):
        """
        
        Searches for exact matches of filter values across multiple vector databases concurrently.

        :param filter_values: List of strings to search for.
        :return: A dictionary mapping each filter value to a dictionary containing matching vector dbs and search results.
        """
        logging.info("Finding matching columns...")
        vector_stores_path = "Vector_Stores"

        # List of your vector database names
        vector_db_names = [
            "Column1_Name_faiss_index",        #In this example, the vector db names have the format "Column_Name_faiss_index"
            "Column2_Name_faiss_index",        #You can replace these with the actual column names in your database
            "Column3_Name_faiss_index",        #And names of the FAISS vector dbs in your system
            "Column4_Name_faiss_index",        #Vector dbs contain the unique values for the corresponding column
            "Column5_Name_faiss_index",
            "Column6_Name_faiss_index",
            "Column7_Name_faiss_index",
        ]

        # Load all vector databases
        vector_dbs = self.load_vector_databases(vector_db_names, vector_stores_path)

        result_dict = {}

        # Create tasks for each filter_value
        filter_tasks = [
            self.search_filter_value(filter_value, vector_dbs)
            for filter_value in filter_values
        ]

        # Run all filter tasks concurrently
        results = await asyncio.gather(*filter_tasks)

        # Collect results into result_dict
        for filter_value, result_entry in results:
            result_dict[filter_value] = result_entry

        return result_dict

    def load_vector_databases(self, vector_db_names, vector_stores_path) -> dict:
        """
        Loads vector databases and returns a dictionary mapping vector_db_name to retriever.


        :param vector_db_names: List of vector database names.
        :param vector_stores_path: Path to the directory containing vector databases.
        :return: Dictionary mapping vector_db_name to retriever.
        """
        # Initialize an empty dictionary to store vector databases
        vector_dbs = {}
        # Loot o load each vector database
        for vector_db_name in vector_db_names:
            try:
                # Build the path to the vector database
                vector_db_path = Path(vector_stores_path) / vector_db_name
                vector_db = FAISS.load_local(
                    str(vector_db_path), self.embedder, allow_dangerous_deserialization=True
                )
                # Create a retriever from the vector database with k=6
                retriever = vector_db.as_retriever(search_kwargs={"k": 6})
                # Save the retriever in the dictionary with the vector database name as the key
                vector_dbs[vector_db_name] = retriever
            except Exception as e:
                logging.error(f"Error loading vector database '{vector_db_name}': {e}")
                continue
        return vector_dbs
    async def save_csv_to_blob(self, results: List[Tuple], headers: List[str], filename: str) -> str:
        """
        Saves query results as a CSV file to Azure Blob Storage and returns a download URL.

        :param results: The query results as a list of tuples.
        :param headers: The list of header strings.
        :param filename: The desired filename for the CSV in blob storage.
        :return: The download URL for the uploaded CSV file.
        """
        logging.info("Saving CSV to blob...")
        csv_buffer = StringIO()
        csv_writer = csv.writer(csv_buffer)
        
        # Write headers
        csv_writer.writerow(headers)
        
        # Write data
        csv_writer.writerows(results)
        
        csv_buffer.seek(0)
        byte_data:bytes = BytesIO(csv_buffer.getvalue().encode('utf-8'))
        
        blob_client = self.blob_service_client.get_blob_client(container=self.container_name, blob=filename)
        
        try:
            await blob_client.upload_blob(byte_data, blob_type="BlockBlob", overwrite=True)            
            # Generate a SAS token
            sas_token = generate_blob_sas(
                account_name=blob_client.account_name,
                container_name=blob_client.container_name,
                blob_name=blob_client.blob_name,
                account_key=blob_client.credential.account_key,
                permission=BlobSasPermissions(read=True),
                expiry=datetime.utcnow() + timedelta(hours=1)  # Set expiration time as needed
            )
            download_url = f"{blob_client.url}?{sas_token}"
        except Exception as e:
            logging.error(f"Failed to save CSV to blob: {e}")
            download_url = None

        return download_url

    async def fetch_schema_info(self, query: str) -> dict:
        """
        Fetches schema information from the database based on the query.

        :param query: The user's query.
        :return: A dictionary containing schema information.
        """
        tables = await self.fetch_table_names(query)
        schemas = {}
        async with aioodbc.connect(dsn=DB_CONFIG.CONN_STR) as conn:
            async with conn.cursor() as cursor:
                for table in tables:
                    await cursor.execute( #IN this case our datbase has a table INFORMATION_SCHEMA.COLUMNS that contains the schema information
                        f"SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = '{table}'"
                    )
                    columns = await cursor.fetchall()
                    schemas[table] = [{'column_name': column[0], 'data_type': column[1]} for column in columns]
        return schemas

    async def fetch_table_names(self, query: str) -> List[str]:
        """
        Retrieves table names from the database that might be relevant to the user's question.

        :param query: The user's query.
        :return: A list of relevant table names.
        """
        table_names = []
        async with aioodbc.connect(dsn=DB_CONFIG.CONN_STR) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("""
                    SELECT TABLE_NAME
                    FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_TYPE = 'BASE TABLE';
                """)
                async for row in cursor:
                    table_names.append(row[0])  # Assuming TABLE_NAME is the first column

        if not table_names:
            logging.error("No table names extracted from the database.")
            return []

        system_prompt = GPTPrompts.prompt_select_relevant_tables.format(table_names=table_names)
        message_text = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query}
        ]

        response = await self.gpt.ainvoke(message_text)
        response = response.content.strip()
        logging.info(f"Response from OpenAI: {response}")
        # Convert the string response to a list
        try:
            response_table_list = ast.literal_eval(response)
            if not isinstance(response_table_list, list):
                raise ValueError("Response is not a list")
            return response_table_list
        except (ValueError, SyntaxError) as e:
            logging.error(f"Error parsing response to list: {e}")
            return []

    async def extract_headers(self, initial_query, sql_query, result_set,schema_info) -> list:
        """
        Extracts and formats headers for the result set using the database schema information and the initial query context.

        :param initial_query: The user's initial query.
        :param sql_query: The generated SQL query.
        :param result_set: The query results.
        :param schema_info: Schema information retrieved from the database.
        :return: A list of headers for the result set.
        """
        first_row = result_set[0] if result_set else result_set
        header_prompt = GPTPrompts.prompt_generate_headers.format(schema_info=schema_info)
        queries = f'''Initial Query: {initial_query}
                    SQL Query: {sql_query}
                    Result Set: {first_row}'''
        message_text = [
            {"role": "system", "content": header_prompt},
            {"role": "user", "content": queries}
        ]
        headers = await self.gpt.ainvoke(message_text)
        logging.info(f"Header response from openai: {headers}")
        headers = headers.content.strip()
        headers = ast.literal_eval(headers)
        logging.info(f"Headers from OpenAI: {headers}")
        return headers
    
    async def explain_results(self,conversation:list, schema_info) -> str:
        """
        Provides an explanation of the query results by using GPT to analyze the conversation context and schema information.

        :param conversation: A list of conversation history messages.
        :param schema_info: Schema information related to the query results.
        :return: A string containing GPT's explanation of the results.
        """
        response = await self.gpt.ainvoke(conversation + [{"role": "user", "content": GPTPrompts.prompt_explain_results.format(schema_info=schema_info, database_context = GPTPrompts.database_context)}])
        return response.content.strip()
    
    async def get_sql_query(self, message_text):
        """
        Generates a SQL query using GPT based on the user's input and conversation context.

        :param message_text: The conversation messages used to generate the SQL query.
        :return: The generated SQL query as a string.
        """
        response = await self.gpt.ainvoke(message_text)
        response = response.content.strip()
        return response

    async def validate_sql_query(self, query, sql_query, results, conversation_history:list, schema_info):
        """
        Validates the SQL query by checking the results, refining the query if necessary, and returning the validated SQL string.

        :param query: The user's input query.
        :param sql_query: The generated SQL query.
        :param results: The results of the SQL query.
        :param conversation_history: A list of previous conversation messages.
        :param schema_info: Schema information used for validation.
        :return: The validated SQL query as a string.
        """
        logging.info("Validating SQL query...")
        prompt = GPTPrompts.validate_sql_prompt.format(schema_info=schema_info)
        if len(results) > 50:
            results = results[:50]
        validation_message = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f'''Data for validation:
            - User Query: {query}
            - Generated SQL to Validate: {sql_query}
            - Results of current query: {results}'''}
        ]
        response = await self.gpt.ainvoke(validation_message)
        response = response.content.strip()
        val_sql_query = self.clean_sql_query(response)
        logging.info(f"\n\nValidated SQL Query:\n{val_sql_query}\n\n")
        conversation_history.append({"role": "assistant", "content": val_sql_query})
        val_sql_string = f"\n\n{val_sql_query}\n\n"
        return val_sql_query, val_sql_string
    
    async def save_conversation_details(self, session_id, user_query, sql_query, results, headers, user_profile:UserProfile):
        """
        Saves the details of the conversation, including the user's query, SQL query, and results, into Azure Blob Storage for later reference.

        :param session_id: The session ID to track the conversation.
        :param user_query: The user's natural language query.
        :param sql_query: The SQL query generated from the user's query.
        :param results: The results of the SQL query.
        :param headers: The headers for the result set.
        :param user_profile: The user's profile information.
        :return: None.
        """
        # Prepare the details to save
        details = {
            "name": user_profile.name,
            "timestamp": str(datetime.now()),
            "user_query": user_query,
            "sql_query": sql_query,
            "headers": headers,
            "results": results
        }

        # Name of the blob
        blob_name = "bot-conversation-log.json"

        # Get the BlobClient
        blob_client = self.blob_service_client.get_blob_client(container=self.container_name, blob=blob_name)

        try:
            # Initialize existing_data to handle the case when the blob does not exist
            existing_data = {"sessions": {}}

            # Check if the blob exists and download its contents
            try:
                download_stream = await blob_client.download_blob()
                blob_data = await download_stream.readall()
                existing_data = json.loads(blob_data)
            except Exception as e:
                logging.info(f"Blob not found or empty: {e}")

            # Ensure existing_data contains a "sessions" key
            if "sessions" not in existing_data:
                existing_data["sessions"] = {}

            # Ensure the session exists in the data
            if session_id not in existing_data["sessions"]:
                existing_data["sessions"][session_id] = {"queries": []}

            # Append the new details to the session's queries
            existing_data["sessions"][session_id]["queries"].append(details)

            # Convert updated data back to JSON string
            updated_data_json = json.dumps(existing_data, default=str, indent=4)
            
            # Upload the updated JSON string to the blob
            await blob_client.upload_blob(updated_data_json, blob_type="BlockBlob", overwrite=True)
            logging.info(f"Saved conversation details to blob: {blob_name}")
        except Exception as e:
            logging.error(f"Failed to save conversation details to blob: {e}")


    async def get_date() -> str: 
        logging.info("Getting the latest date from the database...")
        results = None
        async with aioodbc.connect(dsn=DB_CONFIG.CONN_STR) as conn:
            try:
                cursor: Cursor 
                async with conn.cursor() as cursor:
                    await cursor.execute('''SELECT DATENAME(Month,Latest_Date) as DATENAME,Year(Latest_Date) From (SELECT MAX(CAST(CONCAT(Year, '-', Month, '-01') AS DATE)) AS Latest_Date
FROM (SELECT Year, Month FROM CURRENT_BOOKINGS UNION SELECT Year, Month FROM CURRENT_SALES ) AS CombinedData) AS LatestDate''')
                    results = await cursor.fetchall()
            except pyodbc.Error as e:
                logging.error(f"Error running SQL query: {e}")
                results = f"Error running SQL query: {e}"
        #append the results in a string
        month = ""    
        for result in results:
            month += f"{result[0]} {result[1]}"
        return month

#Expose methods for external use as if they were package methods
clean_sql_query = BotUtilities.clean_sql_query
num_tokens_from_messages = BotUtilities.num_tokens_from_messages
format_sql_query = BotUtilities.format_sql_query
format_cell_data = BotUtilities.format_cell_data
format_result_for_adaptive_card = BotUtilities.format_result_for_adaptive_card
format_result_for_adaptive_card_teams = BotUtilities.format_result_for_adaptive_card_teams
create_adaptive_card = BotUtilities.create_adaptive_card
send_adaptive_card_or_download_link = BotUtilities.send_adaptive_card_or_download_link
compare_headers_to_results = BotUtilities.compare_headers_to_results
process_matched_columns = BotUtilities.process_matched_columns
get_date = BotUtilities.get_date
