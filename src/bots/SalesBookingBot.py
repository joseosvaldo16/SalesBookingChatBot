import os
from botbuilder.core import ConversationState, TurnContext, UserState
from botbuilder.core.teams import TeamsActivityHandler
from botbuilder.schema import ChannelAccount
from botbuilder.schema.teams import TeamsChannelData
from botframework.connector import Channels
from botframework.connector.auth import UserTokenClient
from ..dialogs import SalesBookingDialog
from ..utilities.dialog_helper import DialogHelper
from ..models.UserProfile import UserProfile
from botframework.connector.token_api.models import TokenResponse
from azure.storage.blob import BlobServiceClient
from ..utilities import BotUtilities, DialogHelper
from ..utilities.BotUtilities import get_date
from typing import List
import logging
import jwt


'''This file contains the SalesBookingBot class, which is the main bot class for the bot application.
 It contains the main bot message handler, the main function, and the on error handler.'''
class SalesBookingBot(TeamsActivityHandler):

    def __init__(self, conversation_state: ConversationState, user_state: UserState , dialog):
        super(SalesBookingBot, self).__init__()
        self.conversation_state = conversation_state
        self.user_state = user_state
        self.dialog:SalesBookingDialog = dialog
        self.oauth_settings = self.dialog.oauth_settings
        self.container_created = False
        self.blob_service_client = BlobServiceClient.from_connection_string(os.getenv('AZURE_STORAGE_CONNECTION_STRING'))
        self.container_name = "salesbotai-conversion-histories"  # Your container name
        self.BotUtils = BotUtilities(blob_service_client=self.blob_service_client, container_name=self.container_name,gpt = None,embedder=None)
    
    async def on_message_activity(self, turn_context: TurnContext):
        logging.info("Running on_message_activity...")
        #Process the current user message
        user_input = turn_context.activity.text
        user_state = await self.dialog.user_state_accessor.get(turn_context) or {'authenticated': False}
        logging .info(f"\n\nUser State in on_message_activity: \n\n{user_state}\n\n")
        if user_input and user_state.get("authenticated"):
            await self.dialog.user_query_accessor.set(turn_context, user_input)
        await DialogHelper.run_dialog(self.dialog, turn_context, self.conversation_state.create_property("DialogState"))
            
            
    async def on_token_response_event(self, turn_context: TurnContext):
        #get teh token from the token response event and set it to the turn state
        logging.info("Running on_token_response_event...")
        if turn_context.activity.value and 'token' in turn_context.activity.value:
            await turn_context.send_activity("You are now signed in.")
            logging.info(f"Token in on_toke_response_event: {turn_context.activity.value['token']}")
            turn_context.turn_state['token'] = turn_context.activity.value['token']
            user_state = {}
            user_state["authenticated"] = True
            decoded_token:dict = jwt.decode(turn_context.activity.value['token'], options={"verify_signature": False})
            user_name:str = decoded_token.get('name')
            logging.info(f"Decoded token Keys: {decoded_token.keys()}\n\nDecoded Token Values: {decoded_token.values()}\n\n")
            logging.info(f"Authenticated user: {user_name}")
            await self.dialog.user_profile_accessor.set(turn_context, UserProfile(user_name))
            await self.dialog.user_state_accessor.set(turn_context, user_state)
            await self.user_state.save_changes(turn_context, True)
        else:
            logging.info("Token not found in on_token_response_event.")
        await DialogHelper.run_dialog(
            dialog=self.dialog,
            turn_context = turn_context,
            accessor= self.conversation_state.create_property("DialogState")
        )

    #Create a function the removes all non alphanumeric characters from a string
    async def on_teams_signin_verify_state(self, turn_context: TurnContext):
        logging.info("Running on_teams_signin_verify_state...")
        # Retrieve the UserTokenClient from turn_context.turn_state
        user_token_client:UserTokenClient = turn_context.turn_state.get("UserTokenClient")

        if not user_token_client:
            logging.error("UserTokenClient not found in turn_state.")
            await turn_context.send_activity("Could not retrieve token client.")
            return

        # Fetch the channel_id from the turn context
        channel_id = turn_context.activity.channel_id
        user_id = turn_context.activity.from_property.id
        # Try to fetch the magic code from the activity (sometimes passed by Teams)
        magic_code = turn_context.activity.value.get('state') if turn_context.activity.value else None

        # Explicitly fetch the token using UserTokenClient with the correct arguments
        token_response:TokenResponse = await user_token_client.get_user_token(user_id, self.oauth_settings.connection_name, channel_id, magic_code)
                
        if token_response and token_response.token:
            await turn_context.send_activity("You are now signed in.")
            logging.info(f"Token in on_teams_signin_verify_state: {token_response.token}")
            turn_context.turn_state['token'] = token_response.token

            # Get or create user state
            user_state = await self.dialog.user_state_accessor.get(turn_context) or {}
            user_state["authenticated"] = True
            await self.dialog.user_state_accessor.set(turn_context, user_state)

            # Decode the token to extract user information
            decoded_token:dict = jwt.decode(token_response.token, options={"verify_signature": False})
            logging.info(f"Decoded token Keys: {decoded_token.keys()}\n\nDecoded Token Values: {decoded_token.values()}\n\n")
            user_name = decoded_token.get('name')
            logging.info(f"Authenticated user: {user_name}")
            # Save user profile
            await self.dialog.user_profile_accessor.set(turn_context, UserProfile(user_name))
            await self.dialog.user_state.save_changes(turn_context, True)
        else:
            logging.info("Token not found in on_teams_signin_verify_state.")
            # Continue or begin dialog based on the current state
        await DialogHelper.run_dialog(
            dialog = self.dialog,
            turn_context = turn_context,
            accessor= self.conversation_state.create_property("DialogState")
        )

    async def on_turn(self, turn_context: TurnContext) -> None:
        logging.info(f'''-On turn triggered- \nActivity Type: {turn_context.activity.type} \nActivityName: {turn_context.activity.name}, Activity TurnState Values: {turn_context.turn_state.values()}''')
        #Check if container is initialized, if not, initialize it
        if not self.container_created:
            self.container_created = await self.BotUtils.init_container()
            if not self.container_created:
                logging.error("Container not created successfully.")
        logging.info(f"Turn value in on_turn: {turn_context.activity.value}")
        await super().on_turn(turn_context)
        await self.conversation_state.save_changes(turn_context, False)
        await self.user_state.save_changes(turn_context, False)


    #Implement other activity handlers as needed
    async def on_members_added_activity(
        self, members_added: List[ChannelAccount], turn_context: TurnContext):
        logging.info(f"on_members_added_activity triggered")
        for new_member in members_added:
            if new_member.id != turn_context.activity.recipient.id:  # Skip the bot itself
                date = await get_date()
                # Send a welcome message to the new user
                await turn_context.send_activity(f'''Welcome! Please enter a question related to Sales and Bookings to get started. If I make any mistakes or if you'd like me to change 
                                                     how I format certain results, please let me know and I will do my best to accommodate your request if possible.The more context you provide in your question, the better I can assist you''')
        
        if turn_context.activity.channel_id == Channels.ms_teams:
            channel_data = TeamsChannelData().deserialize(
                turn_context.activity.channel_data
            )
            logging.info(f"Channel Data: {channel_data}")

