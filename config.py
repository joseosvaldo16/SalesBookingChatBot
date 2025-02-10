import os

'''This files contains necessary configuration for the bot application, database and Azure API.
   Do not share this configuration file with anyone.'''
class DefaultConfig:
    """ Bot Configuration """
    APP_ID = os.environ.get("MicrosoftAppId")
    APP_PASSWORD = os.environ.get("MicrosoftAppPassword")
    APP_TYPE = os.environ.get("MicrosoftAppType", "SingleTenant") # SingleTenant or MultiTenant
    APP_TENANTID = os.environ.get("MicrosoftAppTenantId")
    CONNECTION_NAME = os.environ.get("ConnectionName", "Microsoft")

class DatabaseConfig:
    '''Database Configuration'''
    SERVER = '*SERVER*' # Replace with your server 
    DATABASE = '*DATABASE_NAME*' # Replace with your database name
    USERNAME = os.environ.get("DB_USERNAME")
    PASSWORD = os.environ.get("DB_PASSWORD")
    DRIVER = '{ODBC Driver 18 for SQL Server}'
    CONN_STR = f'DRIVER={DRIVER};SERVER={SERVER};PORT=1433;DATABASE={DATABASE};UID={USERNAME};PWD={PASSWORD}'

class AzureConfig:
    '''Azure Configuration''' 
    @classmethod
    def set_environment_variables(cls):
        os.environ["OPENAI_API_TYPE"] = "azure_ad"
        os.environ["AZURE_OPENAI_ENDPOINT"] = "https://{azure-openai-resource-name}.openai.azure.com/" # Replace with your Azure OpenAI endpoint

#Can be modified to use regular OpenAI API