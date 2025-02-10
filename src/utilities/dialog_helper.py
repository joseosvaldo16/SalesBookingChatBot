from botbuilder.core import TurnContext, StatePropertyAccessor
from botbuilder.dialogs import DialogSet, DialogTurnStatus,DialogContext, Dialog
import logging
class DialogHelper:
    '''
    Helper class to run a dialog
    '''
    @staticmethod
    async def run_dialog(
        dialog: Dialog, turn_context: TurnContext, accessor:StatePropertyAccessor
    ):
        '''
        Run a dialog with the given dialog set
        :param dialog: The dialog to run
        :param turn_context: The turn context
        :param accessor: The state property accessor
        
        '''
        dialog_set = DialogSet(accessor)
        dialog_set.add(dialog)

        dialog_context:DialogContext = await dialog_set.create_context(turn_context)
        if turn_context.activity.text and turn_context.activity.text.lower() in ("stop", "cancel", "exit", "quit"):
            await turn_context.send_activity("Dialog cancelled.")
            #cancel all dialogs except for the parent dialog
            await dialog_context.cancel_all_dialogs()
            return await dialog_context.end_dialog()
        
        if turn_context.activity.text and turn_context.activity.text.lower() in ("reset", "restart"):
            await dialog.conversation_state.clear_state(turn_context)
            await dialog.conversation_data_accessor.set(turn_context, {})
            await turn_context.send_activity("Conversation cleared")
            await dialog_context.cancel_all_dialogs()
            return await dialog_context.end_dialog()
        
        results = await dialog_context.continue_dialog()
        if results.status == DialogTurnStatus.Empty:
            # Check if there is an active dialog to continue
            logging.info("No active dialog. Starting a dialog: Dialogs available: {}".format(dialog_context.dialogs))
            logging.info(f"Starting a new dialog...{dialog.id}")
            await dialog_context.begin_dialog(dialog.id)
        
