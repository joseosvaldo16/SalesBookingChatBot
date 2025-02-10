import os
import logging
from aiohttp import web
from datetime import datetime
from botbuilder.core import TurnContext, ConversationState, MemoryStorage, UserState
from botbuilder.core.integration import aiohttp_error_middleware
from botbuilder.integration.aiohttp import CloudAdapter, ConfigurationBotFrameworkAuthentication
from botbuilder.schema import Activity, ActivityTypes
from config import DefaultConfig as CONFIG
from config import AzureConfig as AZURE_CONFIG
from src.utilities import GPTPrompts as gpt_prompts
from src.dialogs.SalesBookingDialog import SalesBookingDialog
from src.bots.SalesBookingBot import SalesBookingBot

AZURE_CONFIG.set_environment_variables()

'''
This is the main file for the bot. It contains the main bot message handler, the main function, and the on error handler. 
This sets up the server and routes for the bot, and initializes the bot with the necessary components such as the adapter, bot, and dialog instances.

'''

'''This is the main file for the bot. It contains the main bot message handler, the main function, and the on error handler.'''

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')


# On error handler
async def on_error(context: TurnContext, error: Exception):
    """Centralized error handling."""
    logging.error(f"on_turn_error: {error}")
    await context.send_activity("The bot encountered an error or bug.")
    await context.send_activity("To continue to run this bot, please fix the bot source code.")
    if context.activity.channel_id == "emulator":
        trace_activity = Activity(
            label="TurnError",
            name="on_turn_error Trace",
            timestamp=datetime.astimezone(datetime.now()),
            type=ActivityTypes.trace,
            value=str(error),
            value_type="https://www.botframework.com/schemas/error",
        )
        await context.send_activity(trace_activity)

async def get_direct_line_secret(_: web.Request) -> web.Response:
    secret = os.getenv('DirectLineSecret')  # Retrieve from environment variables
    if not secret:
        return web.json_response({'error': 'Direct Line Secret not found'}, status=500)
    return web.json_response({'secret': secret})

# Main bot message handler
async def messages(req: web.Request) -> web.Response:
    logging.info(f"Processing message...{req}")
    return await ADAPTER.process(req, BOT)

async def index(_):
    return web.FileResponse('webfiles/index.html')
# Create the ADAPTER and BOT identifiers 
global ADAPTER, BOT
# Instantiate the CloudAdapter using ConfigurationBotFrameworkAuthentication and CONFIG 
ADAPTER = CloudAdapter(ConfigurationBotFrameworkAuthentication(CONFIG))
# Override the on_turn_error handler in the adapter to use the on_error function we defined
ADAPTER.on_turn_error = on_error
# Create the MemoryStorage, ConversationState, UserState, and Dialog instances
MEMORY = MemoryStorage()
conversation_state = ConversationState(MEMORY)
user_state = UserState(MEMORY)
system_prompt = gpt_prompts.build_sql_prompt
# Create the SalesBookingDialog instance which has all the sub-dialogs for the bot
DIALOG = SalesBookingDialog(user_state, conversation_state,CONFIG.CONNECTION_NAME, system_prompt,schema_info = None)
# Create the SQLQueryBot instance using the conversation_state, user_state, and DIALOG
BOT = SalesBookingBot(conversation_state, user_state, DIALOG)
# Create the web app using the aiohttp.web module and add the error middleware used by the adapter for the purpose of error handling
app = web.Application(middlewares=[aiohttp_error_middleware])
# Add routes to the web app
app.router.add_post("/api/messages", messages)
# Add route for the index page
app.router.add_get('/', index)
# Add route to get the Direct Line secret
app.router.add_get('/api/get_direct_line_secret', get_direct_line_secret)

# Setup static route for serving static files (CSS, images, JS, etc.)
app.router.add_static('/', '.', name='static')

if __name__ == "__main__":
    port = int(os.getenv('PORT', 3978))
    try: 
        web.run_app(app, host="0.0.0.0", port=port)
    except Exception as e:
        logging.error(f"Error running the app: {e}")
        raise e