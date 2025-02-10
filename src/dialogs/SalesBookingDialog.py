import os
from botbuilder.dialogs import WaterfallStepContext, DialogTurnResult, ComponentDialog, OAuthPrompt, OAuthPromptSettings, WaterfallDialog
from botbuilder.core import UserState,ConversationState, StatePropertyAccessor, MessageFactory
from botbuilder.schema import Activity, ActivityTypes
from botbuilder.dialogs.prompts import TextPrompt, PromptOptions
from botframework.connector.auth import UserTokenClient
from azure.storage.blob.aio import BlobServiceClient
from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings
from langchain.agents.agent_types import AgentType
from config import DatabaseConfig as DB_CONFIG
from ..utilities.gpt_prompts import GPTPrompts
from ..models.UserProfile import UserProfile
from pyodbc import Cursor
from ..utilities.BotUtilities import (
    BotUtilities,
    send_adaptive_card_or_download_link,
    format_result_for_adaptive_card,
    format_result_for_adaptive_card_teams,
    create_adaptive_card,
    num_tokens_from_messages,
    clean_sql_query,
    format_sql_query,
    compare_headers_to_results,
    process_matched_columns
)
import logging
import aioodbc
import pyodbc
import datetime
import jwt
import ast

'''
This class is a component dialog, which is a collection of related dialogs(like a root dialog and its child or sub-dialogs).
The SalesBookingDialog class is used to handle the main conversation flow of the bot. It contains the dialogs for handling authentication, and post-authentication interaction.
The sub-dialogs or child dialogs include the OAuthPrompt, TextPrompt, and WaterfallDialogs MainDialog, PromptForClarification, and UserInputDialog.

Dialog Prompts: Dialog prompts provided by the Bot Framework SDK which can perform various tasks such as prompting the user for input, handling authentication, and more.

- OauthPrompt: This is used to handle the authentication process. It prompts the user to sign in and handles the sign-in process.
- TextPrompt: This is used to prompt the user for text input.

Waterfall Dialogs: Dialogs that are composed of a series of steps. Each step in the dialog is represented by a function that is called in sequence.
The output of one step is passed as input to the next step. The WaterfallStepContext object is used to pass information between steps.

    - MainDialog: This is the main dialog, which contains the steps for handling post-authentication interaction such as processing queries, or responding to conversational inputs.
    - PromptForClarification: This asks the user for clarification if the query needs more information or context to be processed.
    - UserInputDialog: This dialog is used to prompt the user for input and handle the user's response. It uses the TextPrompt dialog to get the user's input, and processes the user's response in the next step.
    - SignOutDialog: This dialog is used to handle the sign-out process by clearing the user's OAuth token and resetting session data

'''

class SalesBookingDialog(ComponentDialog):
    def __init__(self, user_state:UserState, conversation_state:ConversationState, connection_name:str, system_prompt:str, schema_info:str):
        super(SalesBookingDialog, self).__init__(SalesBookingDialog.__name__)
        self.initial_dialog_id = "AuthDialog"
        self.user_state = user_state
        self.conversation_state = conversation_state
        self.connection_name = connection_name
        self.system_prompt = system_prompt
        self.schema_info = schema_info
        self.system_prompt = system_prompt
        self.schema_info = schema_info
        self.blob_service_client = BlobServiceClient.from_connection_string(os.getenv('AZURE_STORAGE_CONNECTION_STRING'))
        self.container_name = "salesbotai-conversion-histories"  # Your container name

        self.handle_query_prompt = GPTPrompts.handle_query_prompt
        
        self.gpt = AzureChatOpenAI(
            openai_api_version="2024-05-01-preview",
            azure_deployment="mdxgpt4o",
            temperature=0,
            model = "gpt-4o"
        )
        self.embedder = AzureOpenAIEmbeddings(
            openai_api_version="2024-03-01-preview",
            azure_deployment="large_text_model",
            openai_api_type= AgentType.OPENAI_FUNCTIONS
        )
        self.BotUtils = BotUtilities(self.blob_service_client, self.container_name, self.gpt, self.embedder)
        self.conversation_state:ConversationState = conversation_state
        self.user_state:UserState = user_state
        self.user_profile_accessor = user_state.create_property("UserProfile")
        self.user_state_accessor:StatePropertyAccessor = user_state.create_property("UserState")
        self.user_query_accessor:StatePropertyAccessor = conversation_state.create_property("UserQuery")
        self.conversation_data_accessor:StatePropertyAccessor = conversation_state.create_property("ConversationData")

         # Configure OAuthPrompt with connection settings
        self.oauth_settings = OAuthPromptSettings(
            connection_name=connection_name,
            text="Please sign in",
            title="Sign in",
            timeout=300000,  # Adjust as needed
            end_on_invalid_message=False

        )
        self.add_dialog(OAuthPrompt(OAuthPrompt.__name__, self.oauth_settings))
        self.add_dialog(TextPrompt(TextPrompt.__name__))

        # WaterfallDialog for handling authentication
        self.add_dialog(WaterfallDialog("AuthDialog", [
            self.prompt_for_login_step,
            self.handle_login_step,
        ]))

        # Main dialog for handling post-authentication interaction
        self.add_dialog(WaterfallDialog("MainDialog", [
            self.handle_message_step,
            self.run_query_step,
            self.process_results_step
        ]))

        self.add_dialog(WaterfallDialog("PromptForClarificationDialog", [ 
            self.prompt_for_clarification_step,
            self.process_confirmation_step,
            self.update_filter_values_step
        ]))

        self.add_dialog(WaterfallDialog("UserInputDialog", [
            self.prompt_for_input_step,
            self.handle_user_input_step
        ]))

        # WaterfallDialog for handling sign-out
        self.add_dialog(WaterfallDialog("SignOutDialog", [
            self.handle_signout_step,
        ]))
    async def prompt_for_login_step(self, step: WaterfallStepContext):
        logging.info("Running prompt_for_login...")
        logging.info(step.context.activity.channel_id)
        user_query = step.context.activity.text
        await self.user_query_accessor.set(step.context, user_query)
        await self.conversation_state.save_changes(step.context)
        try:
            return await step.begin_dialog("OAuthPrompt")
        except Exception as e:
            logging.error(f"Error prompting for login: {e}")
            await step.context.send_activity("An error occurred while prompting for login.")
            return await step.end_dialog()
        #This is called after the user has signed in or after the OAuthPrompt has been skipped 
    async def handle_login_step(self, step: WaterfallStepContext):
        '''
        This function is called after the user has signed in or after the OAuthPrompt has been skipped. It checks if the user has been authenticated
        and if so, it sets the user state to authenticated and proceeds to the MainDialog. If the user is not authenticated, it prompts the user to sign in again.

        params:
        step: WaterfallStepContext

        returns: DialogTurnResult (replace_dialog, or begin_dialog)
        '''

        logging.info("Running handle_login...")
        logging.info(f"Token Response: {step.result}")
        token_response = step.result
        token = None

        if isinstance(token_response, dict):
            token = token_response.get('token')
        else:
            token = token_response.token if token_response else None
        
        if token:
            step.context.turn_state['token'] = token
            user_state = await self.user_state_accessor.get(step.context, {})
            user_state = user_state or {}
            user_state["authenticated"] = True
            await self.user_state_accessor.set(step.context, user_state)
            # Decode the token to extract user information
            decoded_token = jwt.decode(token, options={"verify_signature": False})
            user_name = decoded_token.get('name')
            logging.info(f"Authenticated user: {user_name}")
            await self.user_profile_accessor.set(step.context, UserProfile(user_name))
            await self.user_state.save_changes(step.context, False)

            # Proceed to MainDialog or specific post-authentication step
            return await step.replace_dialog("MainDialog", {'retries': 0})

        await step.context.send_activity("You are not authenticated. Please sign in first.")
        return await step.begin_dialog('AuthDialog',{})

    async def handle_signout_step(self, step: WaterfallStepContext) -> DialogTurnResult:
        """
        Handles the sign-out process by clearing the user's OAuth token and resetting session data.
        """
        # Use UserTokenClient to sign out the user
        user_token_client: UserTokenClient = step.context.turn_state.get(UserTokenClient.__name__, None)

        await user_token_client.sign_out_user(step.context.activity.from_property.id, self.oauth_settings.connection_name,
                    step.context.activity.channel_id)

        # Clear user and conversation state
        await self.conversation_state.clear_state(step.context)
        await self.user_state.clear_state(step.context)
        
        # Notify the user
        await step.context.send_activity("You have been signed out.")
        
        await step.cancel_all_dialogs()
        return await step.end_dialog()
    
    async def handle_message_step(self, step: WaterfallStepContext) -> None:

        logging.info("Running handle_message...")
        user_input = await self.user_query_accessor.get(step.context, step.context.activity.text)
        if user_input and user_input in ("logout", "log out", "sign out", "signout", "logoff", "log off", "signout"):
            return await step.begin_dialog("SignOutDialog")
        await step.context.send_activity(Activity(type=ActivityTypes.typing))
        conversationID = step.context.activity.conversation.id
        logging.info(f"Conversation ID: {conversationID}")
        logging.info(f"User Input from user_query_accessor: {user_input}")
        self.schema_info = await self.BotUtils.fetch_schema_info(user_input)
        sys_prompt = self.system_prompt.format(schema_info=self.schema_info)
        conversation = await self.conversation_data_accessor.get(step.context) or []
        last_messages = conversation[-3:] if  len(conversation) > 5 else conversation
        update_user_input = await self.gpt.ainvoke([{"role": "system", "content": GPTPrompts.prompt_retrieve_input_from_followup.format(conversation_history = last_messages)}, {"role": "user", "content": f'User Input: {user_input}'}])
        user_input = update_user_input.content.strip()
        #Get the schema info for the user input
        self.handle_query_prompt.format(schema_info=self.schema_info, system_prompt=sys_prompt, last_message=str(last_messages))
        
        conversation.append({"role": "system", "content": self.handle_query_prompt})
        conversation.append({"role": "user", "content": user_input})

        result = await self.gpt.ainvoke(conversation)
        gpt_response = result.content.strip()

        await self.conversation_data_accessor.set(step.context, conversation)
        await self.conversation_state.save_changes(step.context)
        step.options['conversationID'] = conversationID
        step.options['initial_query'] = user_input
        if gpt_response.lower() in ("handle_query"):
            return await self.handle_query(step, user_input)
        else:
            return await self.chat_with_gpt(step,user_input)
    
    ## Function to handle the user query
    async def handle_query(self, step: WaterfallStepContext, initial_query) -> None:
        logging.info("Running handle_query...")
        await step.context.send_activity(Activity(type=ActivityTypes.typing)) 
        logging.info(f"Initial Query: {initial_query}")
        #Set the initial query and conversation id in the main dialog step options
        step.options['initial_query'] = initial_query
        step.options['conversationID'] = step.context.activity.conversation.id

        has_name_or_product,filters = await self.BotUtils.has_name_or_product(initial_query)
        logging.info(f"Has Name or Product: {has_name_or_product}")
        step.options['conversation_history'] = await self.conversation_data_accessor.get(step.context) or []

        try:
            await step.context.send_activity("Processing your request...")
            if has_name_or_product:
                result_dict = await self.BotUtils.find_matching_columns(filters)
                initial_WContext, sentences = await process_matched_columns(result_dict, initial_query)
                if initial_WContext:
                    initial_query = initial_WContext
                    step.options['initial_query'] = initial_query
                logging.info(f"Result Dict: {result_dict}")
                if sentences:
                    return await step.begin_dialog("PromptForClarificationDialog", {'user_query': initial_query, 'sentences':sentences})
                else: 
                    return await step.begin_dialog(("PromptForClarificationDialog", {'user_query': initial_query}))
            else:
                #Move to the step after the next 
                return await step.next(initial_query)
        except Exception as e:
            logging.error(f"Error handling query: {e}")
            await step.context.send_activity(f"Sorry, there was an error processing your request: {e}")
            return await step.end_dialog()
        

    async def prompt_for_clarification_step(self, step: WaterfallStepContext):
        logging.info("Running prompt_for_clarification...")
        #If its the first time the user is being prompted for clarification, then the clarification step conversation history is empty 
        step_conversation_history = step.options['step_conversation_history'] if 'step_conversation_history' in step.options else []
        logging.info(f"Running prompt_for_clarification with user query: {step.options['user_query']}")
        all_filters_clarified = [False,""]
        #Call the check_filter_clarification function to check if all filters have been clarified
        check_clarification_response, step_conversation_history = await self.BotUtils.check_filter_clarification(step.options['user_query'], step_conversation_history)
        #Evaluate response as a python tuple
        all_filters_clarified = ast.literal_eval(check_clarification_response)
        #If the user has already been prompted for clarification, then the step options will contain the sentences for the user
        if 'sentences' in step.options: 
            #Get the name product response from the step options
            name_product_response = step.options['sentences']   
            logging.info(f"\n\nName Product Response: {name_product_response}\n\n")
            logging.info(f"\n\nAll Filters Clarified: {all_filters_clarified[1]}\n\n") 
            #Combine the name product response with the all filters clarified response        
            messages = [{"role":"system","content": GPTPrompts.prompt_combine_messages}, {"role":"user","content":f"Input Message 1: {name_product_response}-----Input Message 2: {all_filters_clarified[1]}"}]
            response = await self.gpt.ainvoke(messages)
            combined = response.content
            #use string matching to detect if the combined message contains 'clarify', 'please','?', or 'does' in it, if so set clarification_needed to True 
            clarification_needed = any(x in combined.lower().strip() for x in ['clarify', 'please','?','does'])
            logging.info(f"Clarification Needed: {clarification_needed}\n\nAll Filters Clarified: {not clarification_needed}\n\n")
            #if clarification is needed then all filters clarified is false, else it is true (compliment of clarification needed)
            all_filters_clarified = (not clarification_needed,f"{combined}")

        logging.info(f"Clarification Messages: {check_clarification_response}")
        #Response is string representation of a tuple. Fist element is a boolean indicating if all filters have been clarified, and the second element is the message to the user
        #Use ast.literal_eval to convert the string to a tuple
        #Save the tuple to the step options
        step.options['all_filters_clarified'] = all_filters_clarified #The message inside the tuple will eventually contain all the context needed to update the query
        #If all filters have been clarified, then send the message from gpt to the user and move to the next step
        if all_filters_clarified[0]:
            logging.info(f"Clarification Complete: {all_filters_clarified[1]}")
            await step.context.send_activity(all_filters_clarified[1])
            return await step.next(all_filters_clarified[1])
        else:
            #If not all filters have been clarified, then send the message from gpt to the user and prompt the user for input
            logging.info(f"Requesting Clarification: {all_filters_clarified[1]}")
            return await step.begin_dialog("UserInputDialog",{'text': all_filters_clarified[1], 'step_conversation_history': step_conversation_history})
    
    async def process_confirmation_step(self,step: WaterfallStepContext):
        logging.info("Running process_confirmation...")
        logging.info(f"\n\nStep result: {step.result}\n\n")
        logging.info(f"\n\nStep info: {step.options}\n\n")
        logging.info(f"\n\nClarify Filter Boolean: {step.options['all_filters_clarified'][0]}\n\n")
        ##get the question that was presented to the user
        if step.options['all_filters_clarified'][0] == False:
            _, step_conversation_history = step.result
            return await step.replace_dialog("PromptForClarificationDialog", {'user_query': step.options['user_query'], 'step_conversation_history': step_conversation_history})
        initial_query = step.options['user_query']
        logging.info(f"Initial Query: {initial_query}")
        #Since the tuples has a True value, the string is now the context for our query
        step.options['query_context'] = context = step.options['all_filters_clarified'][1]  #Get context from second element of the tuple and store in var context. Then store context in step options
        #Into the prompt_update_query
        prompt_select_vectordb = GPTPrompts.prompt_select_vectordb.format(user_query=initial_query,vector_db_names = GPTPrompts.vector_db_names, context = context)
        vectordb_response = await self.gpt.ainvoke(prompt_select_vectordb)
        step.options['vectordb_selection'] = vectordb_response = ast.literal_eval(vectordb_response.content)
        logging.info(f"\n\nVector Database Selection: {vectordb_response}\n\n")
        keywords = self.BotUtils.get_search_results(vectordb_response)
        step.options['headers']= headers =  vectordb_response[1]
        logging.info(f"\n\nKeywords:\n{keywords}\n\n")
        logging.info(f"\n\nHeaders: {headers}\n\n")
        #Compare the headers to the keywords to see if they match first results. If they do not, then return a prompt to the user to select the correct value
        result =  compare_headers_to_results(headers, keywords)
        logging.info(f"\n\nCompare headers result: {result}\n\n")
        step.options['select_values_message'] = result[1]
        #If the result is true, then begin the UserInputDialog dialog with the generated prompt for the user to select the correct value
        if result[0]:
            return await step.begin_dialog("UserInputDialog",{'text': result[1], 'step_conversation_history':[]})
        else:
            #If the result is false, then no selection is needed. Just send user info about matched keywords and headers
            await step.context.send_activity(result[1])
            return await step.next((result[1],None))          
            
    async def update_filter_values_step(self, step: WaterfallStepContext):
        logging.info("\nRunning update_filter_values...\n")
        selection,_ = step.result
        select_values_message = step.options['select_values_message']
        headers = step.options['headers']
        user_query = step.options['user_query']       
        #Inject the user query, filter values, and messages into the prompt_update_filters
        prompt_update_filters = GPTPrompts.prompt_update_filters.format(user_query=user_query, filter_values = headers, messages = select_values_message, user_selection=selection,query_context=step.options['query_context'])
        #Invoke the GPT model with the prompt_update_filters. This will generate an updated query with the new filter values
        updated_query = await self.gpt.ainvoke(prompt_update_filters)
        logging.info(f"\n\nUpdated Query: {updated_query.content}\n\n")
        return await step.end_dialog(updated_query.content)

    async def run_query_step(self, step: WaterfallStepContext) -> DialogTurnResult:
        '''
        Gets the updated query from the previous step or the initial query from the step
        options if no filter values wer updated. It the passes the query to the run_query function to execute the query.
        which creates the SQL query, executes it, and validates it. The results are then processed and displayed to the user.

        params:
        step: WaterfallStepContext

        returns: DialogTurnResult (next step)
        '''
        logging.info("Running run_query_step...")
        await step.context.send_activity("Running query...")
        # Get the user input from the previous step if the result is not -1 else get the initial query from the step options
        initial_query = step.result if step.result != -1 else step.options['initial_query']
        sql_query, results = await self.run_query(step, initial_query, self.system_prompt)
        return await step.next((sql_query, results, initial_query))
    
    async def process_results_step(self, step: WaterfallStepContext) -> DialogTurnResult:
        '''
        Processes the results of the SQL query. It formats the results for display and saves the results to a CSV file in Azure Blob Storage.
        It also saves the conversation details to the conversation state and sends the results to the user.

        params:
        step: WaterfallStepContext

        returns: DialogTurnResult (end_dialog)      
        '''
        logging.info("Processing and saving results...")
        await step.context.send_activity("Saving Results...")
        # Get the results from the previous step which is a tuple of the SQL query, the results, and the initial query
        sql_query, results, query_to_process = step.result
        #Format the SQL query for display
        formatted_sql = format_sql_query(sql_query)
        # Extract the headers from the results using the BotUtils class method (ChatGPT)
        headers = await self.BotUtils.extract_headers(query_to_process, sql_query, results, self.schema_info)
        conversationID = step.options['conversationID']
        #Use the conversation id and current time to create a unique filename for the CSV file
        csv_filename  = f"Salesbot-Results-{conversationID[-6:]}-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.csv"
        download_url = await self.BotUtils.save_csv_to_blob(results, headers, csv_filename)
        try:
            #Get the client channel id to determine if the adaptive card should be formatted for Teams or webchat
            client = step.context.activity.channel_id
            if client == 'msteams':
                adaptive_cards = format_result_for_adaptive_card_teams(query_to_process, sql_query, results, download_url,headers)
            else:
                formatted_results = format_result_for_adaptive_card(results, headers)
                user_profile = await self.user_profile_accessor.get(step.context)
                await self.BotUtils.save_conversation_details(conversationID, query_to_process, sql_query, results, headers, user_profile)
                adaptive_card_payload = create_adaptive_card(query_to_process, formatted_sql, formatted_results, download_url)
                adaptive_cards = [adaptive_card_payload]
        except Exception as e:
            logging.error(f"Error formatting results for adaptive card: {e}")
            await step.context.send_activity("Sorry, there was an error formatting the results for display.")
            return await step.end_dialog()
        messages = [Activity(
            type=ActivityTypes.message,
            attachments=[card]
        ) for card in adaptive_cards]

        conversation = await self.conversation_data_accessor.get(step.context) or []
        await send_adaptive_card_or_download_link(step, messages, download_url, query_to_process, formatted_sql)
        await step.context.send_activity(Activity(type=ActivityTypes.typing))
        #Get an explanation of the results
        explanation = await self.BotUtils.explain_results(conversation,self.schema_info)
        sql_run_requirement = await self.gpt.ainvoke([{"role":"system", "content":GPTPrompts.prompt_check_sql_query_needed},{"role":"user", "content":f"Input Message: {explanation}"}])
        sql_run_flag = ast.literal_eval(sql_run_requirement.content)
        logging.info(f"\n\nSQL Run Flag: {sql_run_flag}\n\n")
        #If the explanation indicates that the sql query was wrong and the user needs to run another query, then re-run the MainDialog
        if (sql_run_flag and (step.options['retries'] < 2)):
            logging.info(f"\n\nSQL Query Wrong: Rerunning with retry{step.options['retries']}\n\n")
            step.options['retries'] += 1
            await step.context.send_activity("Oops, looks like I've ran into an error. Let me try that again")
            #set the user query to the original user query with the added explanation about the user query result
            await self.user_query_accessor.set(step.context, f"Original User Query:{query_to_process}. Explanation of results: {explanation}")
            await self.conversation_state.save_changes(step.context)
            #return to the MainDialog replacing the current dialog
            return await step.replace_dialog("MainDialog", {'retries':  step.options['retries']})
        else:
            #If the explanation does not indicate that the sql query was wrong, then send the explanation to the user and end the dialog
            await step.context.send_activity(f"{explanation}")
            #end of MainDialog
            return await step.end_dialog()

        
    async def chat_with_gpt(self,step: WaterfallStepContext, user_input: str) -> DialogTurnResult:
        '''
        This function is used to chat with the GPT model. It appends the user input and system prompt that
        asks gpt to give a conversational response. If the response includes or indicates that an SQL query
        is need to be run, the the handle_query function is called. Otherwise, the response is appended to the user
        
        params:
        step: WaterfallStepContext
        user_input: str

        returns: DialogTurnResult (end_dialog, or handle_query)
        
        '''
        logging.info("Running chat_with_gpt...")
        await step.context.send_activity(Activity(type=ActivityTypes.typing))
        conversation:list = await self.conversation_data_accessor.get(step.context)
        message = []
        #Append the system prompt to the message 
        message.append({"role": "system", "content": GPTPrompts.chat_with_gpt_prompt.format(schema_info=self.schema_info, database_context = GPTPrompts.database_context)})
        #Append the user input to the message
        message.append({"role": "user", "content": user_input})
        #Append the conversation history to the message
        message = conversation + message
        #Invoke the GPT model with the message + conversation history
        response = await self.gpt.ainvoke(message)
        gpt_response = response.content.strip()
        #Check if the user needs to run an SQL query using the GPT model
        sql_run_requirement = await self.gpt.ainvoke([{"role":"system", "content":GPTPrompts.prompt_check_sql_query_needed},{"role":"user", "content":f"Input Message: {gpt_response}"}])
        sql_run_flag = ast.literal_eval(sql_run_requirement.content)
        #If the response indicates that the user needs to run an SQL query, then run the handle_query function
        if sql_run_flag:
            return await self.handle_query(step, user_input)
        # Else, append the response to the conversation history and send the response to the user then end the dialog
        conversation.append({"role": "assistant", "content": gpt_response})
        #Set the conversation history to the updated conversation
        await self.conversation_data_accessor.set(step.context, conversation)
        # Save the conversation details to conversation state
        await self.conversation_state.save_changes(step.context)
        #Send the response to the user
        await step.context.send_activity(gpt_response)
        return await step.end_dialog()
    
    async def run_query(self, step: WaterfallStepContext, initial_query, sys_prompt:str):
        '''
        This function is used to run the SQL query. It first validates the query and then re-executes the query if necessary.
        It also saves the conversation history to the conversation state.

        params:
        step: WaterfallStepContext
        initial_query: str
        sys_prompt: str

        returns: Tuple (str, List[pyodbc.Row])

        '''
        logging.info(f"Running query")
        query = initial_query
        logging.info(f"Initial Query: {query}")
        sys_prompt = sys_prompt.format(schema_info=self.schema_info)
        max_response_tokens = 500
        token_limit = 50000
        conversation:list = await self.conversation_data_accessor.get(step.context)
        conversation.append({"role": "system", "content": sys_prompt})
        conversation.append({"role": "user", "content": query})
        conv_history_tokens = num_tokens_from_messages(conversation)

        while conv_history_tokens + max_response_tokens >= token_limit:
            del conversation[0]
            conv_history_tokens = num_tokens_from_messages(conversation)

        while len(conversation) > 16:
            del conversation[0]

        response = await self.BotUtils.get_sql_query(message_text=conversation)
        sql_query = clean_sql_query(response)

        logging.info(f"\n\nSQL Query:\n{sql_query}\n\n")
        sql_string = f"\n\n{sql_query}\n\n"

        # Establish a persistent database connection
        async with aioodbc.connect(dsn=DB_CONFIG.CONN_STR) as conn:
            results = None
            try:
                cursor: Cursor 
                async with conn.cursor() as cursor:
                    await cursor.execute(sql_query)
                    results = await cursor.fetchall()
            except pyodbc.Error as e:
                logging.error(f"Error running SQL query: {e}")
                results = f"Error running SQL query: {e}"

            # Validate the SQL query regardless of the initial execution outcome
            await step.context.send_activity("Validating...")

            val_sql_query, val_sql_string = await self.BotUtils.validate_sql_query(query, sql_query, results, conversation_history=conversation, schema_info=self.schema_info)

            # Re-execute the validated query if it's different from the original
            final_results = None
            action_taken = "Validation only"
            final_sql_string = val_sql_string
            if val_sql_query != sql_query:
                try:
                    async with conn.cursor() as cursor:
                        await cursor.execute(val_sql_query)
                        final_results = await cursor.fetchall()
                    action_taken = "Re-executed with validated SQL"
                except pyodbc.Error as e:
                    logging.error(f"Error running validated SQL query: {e}")
                    final_results = f"Error running validated SQL query: {e}"
            else:
                final_results = results
                final_sql_string = sql_string
            if len(final_results) > 50 and type(final_results[0]) == pyodbc.Row:
                conversation.append({"role": "system", "content": f"Result of SQL Query: {final_results[:50]}"})
            else:
                conversation.append({"role": "system", "content": f"Result of SQL Query: {final_results}"})
            logging.info(f"{action_taken}: {final_sql_string}")
             # Save the conversation details to a file
            await self.conversation_data_accessor.set(step.context, conversation)
            await self.conversation_state.save_changes(step.context)
            return final_sql_string, final_results



    async def prompt_for_input_step(self, step: WaterfallStepContext) -> DialogTurnResult:
        '''
        Prompts the user for input. This is used when the user needs to provide additional information to complete a query.

        params:
        step: WaterfallStepContext

        returns: DialogTurnResult (prompt)
        '''
        logging.info("Prompt for input dialog step triggered...")
        prompt_message = MessageFactory.text(step.options['text'])
        return await step.prompt(TextPrompt.__name__, PromptOptions(prompt=prompt_message))
        
    async def handle_user_input_step(self, step: WaterfallStepContext)-> DialogTurnResult:
        '''
        Handles the user input. This is used when the user needs to provide additional information to complete a query.

        params:
        step: WaterfallStepContext

        returns: DialogTurnResult (end_dialog)
        '''
        logging.info(f"Running handle_user_input...{step.result}")
        #get the user input from the previous step (prompt_for_input) which has the user input 
        user_input = step.result
        #Get conversation history from step options and append the user input. This also modifies the original conversation history object not just the new identifier
        conversation_history:list = step.options['step_conversation_history']
        conversation_history.append({"role": "assistant", "content": step.options['text']})
        conversation_history.append({"role": "user", "content": user_input})
        return await step.end_dialog((user_input, conversation_history))
