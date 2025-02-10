# SQLQueryBot

Author: [Jose Vera](https://github.com/joseosvaldo16/)

SQLQueryBot is a sophisticated Python-based bot application designed to interactively handle and generate MS SQL queries. It leverages the power of the Bot Framework SDK for Python, providing a rich and engaging user experience. The orignal bot was design to help query sales and booking data, but it can be easily adapted to other use cases.

Built on top of the aiohttp web server, SQLQueryBot is capable of efficiently handling HTTP requests, making it highly responsive and reliable. It's designed to understand and generate syntactically correct MS SQL queries based on user input, ensuring the integrity and security of your database.

Key Features:

- **Interactive Query Generation**: SQLQueryBot can generate necessary SQL queries based on user input, focusing on the required columns and tables.
- **Read-Only Commands**: To ensure the safety of your data, SQLQueryBot only uses read-only commands, avoiding any queries that could modify the database.
- **Current Date Handling**: SQLQueryBot uses 'CAST(GETDATE() as date)' to handle queries involving 'today'.
- **MSSQL Syntax**: SQLQueryBot returns queries in MSSQL syntax, without any additional explanations or text.
- **Security**: SQLQueryBot uses OAuthPrompt for handling authentication, ensuring secure access to the bot's functionality.

Whether you're running it locally or within a Docker container, SQLQueryBot provides a flexible and portable solution for handling MS SQL queries.

## Project Structure

## Project Structure

- [`app.py`](app.py): This is the main file for the bot. It contains the main bot message handler, the main function, and the on error handler.
- [`config.py`](config.py): This file contains necessary configuration for the bot application, database, and Azure API.
- [`src/bots/SalesBookingBot.py`](src/bots/SalesBookingBot.py): This file contains the SalesBookingBot class, which is the main bot class for the bot application.
- [`src/dialogs/SalesBookingDialog.py`](src/dialogs/SalesBookingDialog.py): This file contains the SalesBookingDialog class, which is a Dialog Component that manages the conversation logic and flow.
- [`src/utilities/BotUtilities.py`](src/utilities/BotUtilities.py): This file contains utility functions used throughout the bot application that do not use or interact with the bot framework.
- [`src/utilities/AdaptiveCard.json`](src/utilities/AdaptiveCard.json): This file contains the template for the adaptive card used to present the original query, the SQL query, and the results of the SQL query to the user.
- [`src/utilities/AdaptiveCardResults.json`](src/utilities/AdaptiveCardResults.json): This file contains the template for the adaptive card used to present query results to the user.
- [`src/utilities/dialog_helper.py`](src/utilities/dialog_helper.py): This file contains the DialogHelper class, which is a utility class that helps manage dialog states.
- [`src/models/UserProfile.py`](src/models/UserProfile.py): This file contains the UserProfile class, which is used to store user information.
- [`webfiles/index.html`](webfiles/index.html): This file contains the HTML code for the web chat interface.
- [`webfiles/style-v1.css`](webfiles/style-v1.css): This file contains the CSS code for the web chat interface.
- [`Vector_Stores`](Vector_Stores): This directory contains the vector stores used by the bot for matching column names.
- [`Dockerfile`](Dockerfile): This file is used to build a Docker image for the application.
- [`requirements.txt`](requirements.txt): This file lists all Python dependencies, which can be installed using pip.

### **1. Overview of the Frameworks and APIs**

#### **1.1 Microsoft Bot Framework**
The **Microsoft Bot Framework** is a comprehensive framework for building bots that can interact with users in various channels like Teams, Web Chat, and others. It enables message handling, session management, and supports OAuth for authentication.

**Key Concepts:**
- **Activity:** The fundamental unit of communication between the bot and the user.
- **TurnContext:** Provides context for the current conversation turn.
- **Dialogs:** Help manage complex conversational flows, like managing state, multiple steps, etc.
- **Adapter:** Manages the communication between the bot and channels.

#### **1.2 Azure Services**
The SalesBot integrates heavily with **Azure Services**:
- **Azure Blob Storage:** Used for storing conversation history, query results, and downloadable CSV files.
- **Azure OpenAI:** Used to enhance the bot's responses using GPT-4 for natural language processing.

#### **1.3 Azure Open AU**
The **GPT-4o** model from Azure OpenAI is used for interpreting user queries, generating SQL queries, and providing clarifications when necessary. The **LangChain** library is used to create and mange FAISS (a vector-based search engine).

---

### **2. Structure of the SalesBot Application**

The application is divided into several files, each with specific roles. Below is a breakdown of key components:

#### **2.1 Main Bot Structure (app.py)**
This file acts as the entry point for the bot and sets up essential configurations like app server, routing, middleware, and error handling.

- **Key Classes and Functions:**
  - **`on_error`:** Centralized error handler for the bot, which sends messages to the user when an error occurs.
  - **`messages`:** Main route for processing messages received from the user.
  - **`get_direct_line_secret`:** Route to retrieve the bot's Direct Line secret, stored in environment variables.

The bot is initialized by creating an instance of **SQLQueryBot**, which handles the actual conversation flow using various dialogs like **SalesBookingDialog**.

#### **2.2 Conversation Handling (SQLQueryBot.py)**
The **SQLQueryBot** class is responsible for processing messages from users and directing them through the correct dialogs.

- **Key Methods:**
  - **`on_message_activity`:** Handles new user messages and initiates or continues the dialogs based on the state.
  - **`on_token_response_event`:** Processes OAuth token responses when users sign in.
  - **`on_teams_signin_verify_state`:** Used for verifying user authentication within Teams.
  - **`on_members_added_activity`:** Responds to new members joining the conversation.
  - **`on_turn`:** Dispatches incoming activities to the appropriate handler based on the activity type.

#### **2.3 Dialog Management (SalesBookingDialog.py)**
This file contains the **SalesBookingDialog** class, which manages the conversation logic for handling sales and booking queries.

- **Key Dialogs:**
  - **`prompt_for_login_step` & `handle_login_step`:** Handles user authentication via OAuth.
  - **`handle_message_step`:** Processes user input and uses GPT-4 to interpret queries.
  - **`run_query_step`:** Generates and runs SQL queries, then formats results for the user.
  - **`prompt_for_clarification_step`:** Asks clarifying questions when the query is ambiguous.
  - **`process_results_step`:** Saves the query results to Azure Blob Storage and presents the results via an adaptive card.

#### **2.4 Utility Functions (BotUtilities.py)**
This class provides several utility methods used throughout the bot for tasks like saving files, processing query results, and managing conversation state.

- **Key Methods:**
  - **`save_csv_to_blob`:** Saves query results as a CSV file in Azure Blob Storage and returns a download URL.
  - **`has_name_or_product`:** Determines if the user query contains ambiguous names or products.
  - **`find_matching_columns`:** Uses FAISS vector databases to find matching column names.
  - **`format_result_for_adaptive_card`:** Formats SQL query results to be displayed in an adaptive card.
  - **`get_sql_query`:** Calls GPT-4 to generate SQL queries from user input.

#### **2.5 Adaptive Cards (AdaptiveCard.json, AdaptiveCardResults.json)**
These JSON files define the templates for adaptive cards used to present results to users in both Teams and Web Chat.

- **`AdaptiveCard.json`:** Contains placeholders for the user's query and SQL query, which are replaced dynamically when results are displayed.

#### **2.6 Dialog Helper (dialog_helper.py)**
The **DialogHelper** class is a utility class that helps manage dialog states, such as resetting or clearing the conversation when requested.

- **Key Method:**
  - **`run_dialog`:** Handles starting and managing active dialogs based on the current conversation state.

---

### **3. Bot Logic Workflow**

Here is a simplified workflow that explains how the bot processes user queries:

1. **User Interaction:**
   - A user sends a message via a channel like Teams or Web Chat.
   - The message is received by the **app.py** file, which routes it to the **SQLQueryBot** class.
   - The message is sent to the **on_message_activity** method by the **on_turn** method in **SQLQueryBot** where it saves the user input and initiates or continues the SalesBookingDialog. The SalesBookingDialog initiates at the **prompt_for_login_step** in the **AuthDialog** which uses **OAuthPrompt** sub dialog provided by the framework to check if the user is authenticated, or prompt the user to sign in. After the user is authenticated, the bot extracts the name of the user and saves it in the conversation state in the **handle_login_step** method.
2. **Query Interpretation:**
   - The input is then passed to **handle_message_step** in the **SalesBookingDialog** for processing. This will determine if the message is a query to be processed or a conversational input to be responded to by the bot (ChatGPT). If the message is a query, the bot will proceed to the **handle_query** method, otherwise, it will respond to the user's input using ChatGPT in the **chat_with_gpt** method then end the **SalesBookingDialog** waterfall dialog.
   - The **handle_query** method checks if the query contains proper nouns or values that may belong to a column with high cardinality using the **has_name_or_product** method in the **BotUtilities** class. If such values are found, the bot will attempt to find matching values in columns using the **find_matching_columns** method in the **BotUtilities** class. If the value matches one column, it is assumed to be the correct column. If the value matches multiple or no columns, the bot will ask the user to choose which column they want to apply their filter value to using the **PromptClarificationDialog**. The **PromptClarificationDialog** will ask the user to choose the value they meant to look for by presenting the top 5 ranking unique values in the chosen column. If the query is still ambiguous, the bot will ask more questions. If the query is clear, the bot will update the natural language query, enhancing it with context. The **PromptClarificationDialog** ends, and the **SalesBookingDialog** resumes by calling the **run_query_step** method.
    
3. **Running SQL Queries:**
   - The **run_query_step** generates the SQL query using GPT-4o. The SQL query is then executed using the **run_query** method in the **SalesBookingDialog** class. The results are returned and used to validate the query using the **validate_sql_query** method in the **BotUtilities** class. If the query is invalid, the GPT will attempt to fix it.

4. **Displaying and Saving Results:**
   The results are then formatted into an adaptive card using the **format_result_for_adaptive_card_teams** method in the **BotUtilities** class and sent to the user.
   - If the results are too large to display in an adaptive card, they are saved as a CSV file in Azure Blob Storage using the **save_csv_to_blob** method in the **BotUtilities** class. The user receives a download link to access the results.
   - The conversation is saved to Azure Blob Storage using the **save_conversation_details** method in the **BotUtilities** class.
   - GPT-4o is used to explain the results to the user in a conversational manner using the **explain_results** method in the **BotUtilities** class. If the explanation indicates that an error was encountered, or contains a SQL query that has been presumably corrected, then the bot will run the **handle_query** method again to process the corrected query. It will pass the explanation as input to the **handle_query** method. The **handle_query** method will reconstruct the query from the explanation, adding any corrections made by GPT-4o. The process continues as before, with the bot attempting to self-correct up to 3 times before stopping the auto-correct loop.

---

### **4. APIs and Services Involved**

- **Microsoft Bot Framework**: Manages bot activities, dialogs, and OAuth login flows.
- **Azure OpenAI**: Uses GPT-4 for query understanding, SQL generation, and conversation management.
- **Azure Blob Storage**: Stores conversation logs and query results, which can be downloaded as CSV files.
- **FAISS (via LangChain)**: Performs vector-based searches to match user inputs with database column names.

---

### **5. Required Libraries (requirements.txt)**

Here is a list of key Python packages used in the bot application:
- **botbuilder-core**: Core SDK for building bots.
- **azure-identity** & **azure-storage-blob**: Used for Azure authentication and blob storage management.
- **pyodbc** & **aioodbc**: Handle SQL queries and database connections.
- **Azure Open AI**: Manages interaction with the GPT model.
- **faiss-cpu**: For vector-based searches.
- **tiktoken**: Handles token management for GPT queries.

---



The **SalesBot** is a powerful tool built using the **Microsoft Bot Framework**, **Azure Services**, and **OpenAI GPT-4**. It provides a conversational interface for users to query complex sales and booking data. By leveraging the modular dialog structure, adaptive cards, and Azure Blob Storage, the bot ensures seamless user interactions and data handling.

## Bot Functionality

SQLQueryBot is a Python-based bot application that leverages the Bot Framework SDK for Python and aiohttp web server to handle MS SQL queries. It is designed to generate syntactically correct MS SQL queries based on user input, adhering to a set of guidelines to ensure the integrity and security of the database.

The bot's functionality includes:

- Querying only the necessary columns, never selecting all columns from a table.
- Using only existing column names from the specified tables.
- Avoiding any queries that modify the database such as update, create Table, etc; only read-only commands are allowed.
- Using 'CAST(GETDATE() as date)' to get the current date for questions involving 'today'.
- Focusing on the table and column information provided.
- Using the 'TOP' clause instead of 'LIMIT'.
- Returning only the MSSQL query in MSSQL syntax, without any additional explanations or text.
- Ensuring that no matter the input, none of the rules above are broken.

The bot is designed to be run either locally or within a Docker container, making it flexible and portable across different environments. It also includes OAuthPrompt for handling authentication, ensuring secure access to the bot's functionality.

## Frameworks and Libraries

- [Bot Framework SDK for Python](https://github.com/microsoft/botbuilder-python)
- [aiohttp](https://docs.aiohttp.org/en/stable/)
- [pyodbc](https://github.com/mkleehammer/pyodbc)
- [aioodbc](https://aioodbc.readthedocs.io/en/latest/)
- [LangChain](https://github.com/example/langchain)
- [Azure Open AI API](https://azure.microsoft.com/en-us/services/cognitive-services/openai/)
- [Azure Blob Storage](https://azure.microsoft.com/en-us/services/storage/blobs/)


