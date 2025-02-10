
class GPTPrompts:

    vector_db_names = [
                       "Customer_Name_faiss_index","SalesRep_Name_1_faiss_index" ,
                       "Ship_To_Country_faiss_index",
                       "Ship_To_Sales_Rep_faiss_index" ,"Ship_To_State_faiss_index",
                       "PG_faiss_index","PG_2_faiss_index","Part_Number_faiss_index"
                       "Dealer_Distributor_faiss_index", "Customer_Region_faiss_index"]
    prompt_retrieve_input_from_followup =  '''  

        You are provided with a conversation history if it exists. Sometimes the user is asking the bot a follow up query, wants to modify a previous query,
        is providing additional information or corrections, or the user is letting the bot know that the previous query ran was wrong. You may be provided with an
        original user query, and an explanation of the results of that query, or the sql query that was built from the user query.

        Typically the followup query or command would be set as the 'initial query' however from context of the conversation you can tell that the user referring to a previous sql query. 
        Your job is to retrieve the actual intended query form the conversation history. Return the actual intended query. If you are provided explicitly with the original query, and an explanation,
        then this typically means the original query failed to run and needs some corrections. IN that case reconstruct the original natural language query with the context attached as well, but also implement any
        corrections that are needed or that are explained or indicated in the explanation. Explanation might include a corrected SQL query. Reconstruct the intended natural language query
        and include the original (Context: ), and add new context that might be needed based on suggested corrections. 

        Example: 
        Assume the conversation history has:
            User asks: "How many PRODUCT_X did we sell last year"
            Then later: "Can you do this just for January"
        You would return: "How many PRODUCT_X did we sell in January of last year?"

        The conversation history might be bit more complex and might involve multiple follow-up questions and responses. Make sure to get the actual intended query from the conversation history depending on context.
        The updated query should be in natural language if reconstructed and not sql. Make sure to include any changes user requested to the reconstructed query. If user is asking to add or show extra info such a column,
        change formatting of the output, add or change a filter value to a previous query, or any other changes to the query, make sure to include those changes in the reconstructed query.
        If based on conversation history the most recent user input sounds like its most likely a standalone query, then include 'New Query: ' at the beginning of the reconstructed query. If the user is letting the bot 
        know that the previous query ran was wrong include that information the reconstructed query.  

        
        Do not change the input if its not a sql query, command to change query, or a follow-up question, but instead the user is trying to have a conversation with the bot. Since the input is meant to be conversation to the bot and 
        is not intended to be interpreted as a sql query, then return the input as it was given. If question is indeed a follow up make sure to include the context from the previous most recent query which will be in (i) at the end of the previous natural language query.
        The context doesn't always have to be included if the user is asking for a standalone query, or if the user is asking for a new query that is not related to the previous query. Unless the query is similar and the only difference is a filter value or a date range, then dont include the context.
        Context is always formatted as ('filter': 'column', ...) and should not be natural language sentences.So if the new query doesnt share the same filer values as the previous query, then dont include the context. You can include parts of it if the new quey includes some of the same filter values as the previous query.
        Add any new context that might be needed based on suggested corrections, or based on the user input that is asking for a change to the query. Context may not change if the user does not provide a context (column) for a new filter value. Or if its not obvious from 
        what the filter value is referring to. Column names are not filter values, and should only be in the context if its tied to a filter value. Context may not be a column name but can describe or has a description of which column the filter value is tied to.
        conversation_history: {conversation_history}
        '''


    database_context = (
        '''     
            Table.ColumnName1: Descriptino of what the column contains what is used for, and how users might refer to it, or any keywords the refer to the column.
            Table.ColumnName2: Descriptino of what the column contains what is used for, and how users might refer to it, or any keywords the refer to the column.
            Table1.ColumnName1: Descriptino of what the column contains what is used for, and how users might refer to it, or any keywords the refer to the column.
            Table1.ColumnName2: Descriptino of what the column contains what is used for, and how users might refer to it, or any keywords the refer to the column.

            ...
                '''
    )
    handle_query_prompt = (
            '''Use context clues to determine whether a user input is a question related to the sales and bookings dataset either
            directly or due to it being a followup question or input to a previous query or message that was related to sales and bookings data. If the question sounds like something that might be an sql query, a clarification
            to a previous query that can could be parsed into sql, or a command or question in general that could be related to sales and bookings data, then return handle_query. If the user is asking a data query but its not related to sales and bookings data, then return chat_with_gpt.
            The user might be be clarifying a previous question from chat gpt. Therefore pay attention to the conversation history and context of the past 2-3 messages as well as the schema provided. 
            Default to handle query unless its very obvious that the user is not asking to retrieve data or modify a previous query. 

            Schema: {schema_info}

            Also use the other system prompt that will be used later to determine if the user input is meant to be converted to sql or not. Here is the other system prompt: "{system_prompt}"
            .If unsure, or if the input or question sounds too general or too conversational to be converted to sql then return chat_with_gpt. If an input could be converted to a valid sql query given 
            the schema info and other system prompt info then return handle_query. Look at the last message sent by the assistant. If it looks like the user is responding to you the assistant
            by clarifying, or responding to a question you assistant asked the user in the very last message, your response should be handle_query. This is the last message if it exists
            {last_message}. Use it as context to determine if the user is asking a followup question or is responding to a question you asked. If the user is asking a followup question or is responding to a question you asked,
            pay attention to the context of the last message and the schema info and other system prompt info to determine if you should return handle_query (so a sql query gets constructed and ran) or chat_with_gpt(because the chatbot needs to
            talk to the user, or give a more conversational response because its impossible to build a SQL query given the schema that will give the correct response to their input)
            If the user says 'run it' then always return handle_query.IF the user asks to update or modify the database, then return chat_with_gpt. You will almost always return handle_query unless the user input is just conversational such as 'hi', 'hello', 'thank you',
            'whats your name', 'are you working', 'explain this', 'explain the results', etx. These are only some examples, there are endless possibilities of the conversational response, 
            so determine based on if the user is asking to retrieve some data from the database, or modify a previous query or response. Basically only return chat gpt, if based on conversation history,
            it is impossible to construct a valid SQL query given the user input, either because its gibberish, or input is unrelated to a query. Remember to never allow database modifications, or updates to the database, so 
            if the user is asking to update or modify the database, then return chat_with_gpt. 
            ''')
    
    prompt_has_name_or_product = (
        #This can be changed to check for other types of values or entities as well. This use case checks for names,prouct groups, and platforms
        '''
        You are given a user query. Your task is to check if the query contains any names or acronyms of people, cities, countries, states, companies, dealerships, car models, or values that resemble part numbers, Product Groups, or Platforms . If any of these are present, return a Tuple with first index as True
        and second index with all the filter values that are potentially names, products, or product identifiers. If none are present, return a tuple with False and and empty list in the second index.

        Use the following list of unique values to help identify Product Groups and Platforms: If the user input contains any of the following values, then return True.
        - (Product Group): [...]
        - (Platform): [...]

        The following are examples of names and locations that you should identify. These examples are not exhaustive:
        - People names: Any string that looks like a person's name (e.g., "John Doe", "Jane Smith")
        - Cities, countries, states: (e.g., "Chicago", "United States", "California", "Georgia")
        - Companies and dealerships: (e.g., "ACME", "Tyrell", "Umbrella")
        - ID_Numbers: (e.g., "ID-1236", "ID-345")  #Assumeing par numbers have standardized recognizable format
        - Part numbers: Any string that seems like a part number (e.g., "XKB12", "123A")
    

        Special Cases:
        - If sometimes two words or values are adjacent to each other, and may be partially a company name and partially a location or a person name, then consider them as a single name. For example, "JLR Dallas" should be considered as a single name.
        - Return True if any of the above names or values are present in the query. Return false if the user query has no filter values that are names of people, companies, cities, states, countries, pg, pg_2, or part numbers.

        Exception: If the query is asking to filter on all values containing a specific name, country, state, customer name, dealership, or part number, then do not consider it as a filter value. Return False in this case if its the only filter value in the query.
        Exception: Column names are not filter values, and should not be included in your response. Column names are Column1, Column2, Column3, etc... - Add your own column names here.
        Exception: If the filter value doesn't sound like it could be the name or acronym of a person, state, country or company, then do not include it in the response.

        Example User Input: "Get the total sales for ABR-23 in California"
        Example Response: (True,['ABR-23','California'])

        Example User Input: "How many different Product Goups does ACME have?"
        Example Response: (True,['ACME'])

        Example User Input: "Show the total monthly sales for last year"
        Example Response: (False,[])

        Example User Input: "Get the total sales for all clients that have 'Arasak' in their name"
        Example Response: (False,[])

        Example User Input: "Get the total sales for all clients that have the word 'America' in their name"
        Example Response: (False,[])

        Remember to only return a tuple with a boolean and as list of filter values found if any. Do not include any extraneous text or punctuation outside of the tuple. 
        Make sure you dont forget to include both sets of parentheses. Your response will be directly evaluated using ast.literal_eval(response) to parse it, so make sure it is formatted correctly, and you dont have any missing or extra commas, parentheses, or quotes, or any extra text outside of the parentheses.
        It is important you eventually return True in the boolean 
        User Input: {user_input}
        '''
    )

    prompt_check_filter_clarification = (
            '''You are given a user query or command, along with conversation history. The user query sometimes contains filter values for which the user wants to filter SQL data on. 
               Your task is to check if the user provided context for each filter value in the query (context should indicate which column the filter value belongs to), and lets the user know that a column will be used to filter data on the filter value.
               Filter values are typically names of people, companies, locations, serial numbers, part numbers, product groups, platforms. Column names themselves are not filter values, and should not be included in the response. Return a tuple with a boolean and a string.
               The boolean is True if all the filter values in the user query have been clarified (have context as to what column they belong to), and False if at least one filter value still needs clarification. 
                
                -If the user input sounds more like a region (americas, europe, asia, etc) ask if the values is meant to be one of the Regions which are AMERICAS, ASIA PACIFIC, EUROPE.
                -If user only says 'america' ask if they mean AMERICAS region, or 'United States'
                -If the user has provided context for that filter already, or the filter matches exactly on one of the values in PG or PG  2 and are able to match the filter value to the correct column, then set the boolean to False, and in the message let the user know that a Column Name will be used to filter data on the filter value. Make the column name user friendly and bold both the column name and the filter value in the message. Do this only for each filter value that matches exactly on one of the values in PG or PG  2 or if the user has provided context for that filter already 
                 which indicates which column the filter value belongs to.
                -To perform a match based on the values listed below, the filter value must match exactly, disregarding dashes. Do not match filter values that are similar but not exactly the same. For example, if the filter value  'AC-1000' is in ColumnA, do not match 'AC-1000 C' to 'AC-1000' in ColumnA. Instead, consider if it matches any other columns most likely Part Number.
                -If the filter value does not match any values in Product_Group_Column exactly, and it is not a name or location, assume it is a Part_Number. A value might look like it matches but might have a letter or number at the end that is not in the list of values for Product_Group_Columns 
                -YTD or year to date sales are summed sales from the beginning of the year to the present day. Include sales quantity count as well as total USD sales.
                -The user may have provided clarification for a filters in a previous message. 

                Format Requirements:
                - Your response should be a tuple, with first element being a boolean and second element being a string. The boolean is False if clarification is needed, and True if not. The string contains the message to the user with matches made.
                - If asking to clarify a filter, format the filter to be Bold in the question. Do not make the context bold, only the filter value(s) that need clarification.
                - Do not ask to clarify obvious terms such as 'last month', 'today', 'monthly', 'client wise', etc.
                - Make sure to always include in the message to the user, even if its a questions, any matches made, and ask for clarification if needed.
                - Do not include any extraneous text or punctuation outside of the tuple or parentheses. Also make sure you dont forget to include both sets of parentheses.
                - Your response will be directly evaluated using ast.literal_eval(response) to parse it, so make sure it is formatted correctly, and you dont have any missing or extra commas, parentheses, or quotes, or any extra text outside of the parentheses.
                - If the user query already provides context or column for which to filter a value on such as 'Column1', 'Column2', 'Column3' etc, then do not ask for clarification on that value. ##REplace with actual column names
                - If a company name and location are adjacent to each other, consider them as a single value. For example, "ACME Dallas" should be considered as a single value.
                - **Multi-Word Values**: If a filter value consists of multiple words (e.g., "Valley ACME", 'ACME America') and one of the individual words in the filter value is a location, do not infer its context. Always ask the user to clarify whether the value refers to a single entity or if it should be split into separate values.
                If the responds by giving the filter value as a single entity, then consider it as a single value, and do not ask for clarification on the individual words. Example: "ACME America" should be considered as a single value, and you should not ask if America is a region or country.
                - Do not match the filters to the columns unless the user has already indicated that the filter value belongs to a specific column. 
                - If all filter values have been clarified in the user query, or in the context
                Below are the columns that you can ask the user to clarify on, and that you can match the filter values to, based on provided user context.
                Column Details:
                            Use the following generic column details:
                - Name: Name of the recipient.
                - State: State information.
                - Country: Country information.
                - Product_ID: Product identifier.
                - Region: Client region (e.g. AMERICAS, EUROPE, ASIA).
                - Group_A: Primary product group.
                - Replace and add your own column names here.

            Examples:
            - User Input: "Get the total PLATFORM_X sales for Company_Y for January"
                Response: (False, "Group_B (Platform) will be used to filter on 'PLATFORM_X'.")
            - User Input: "Get the total monthly sales by Sales Rep John Doe this year for STATE_Y"
                Response: (False, "Sales_Rep will be used to filter on 'John Doe'.")
            - User Input: "When is the last time client Company_Z made a purchase for product ID 'PROD_001'?"
                Response: (True, "Product_ID will be used for 'PROD_001' and Client_Name will be used for 'Company_Z'.")
            - User Input: "How many PLATFORM_Y did we ship to Company_X last year?"
                Response: (False, "Group_B (Platform) will be used to filter on 'PLATFORM_Y'.")
             '''
    )

    prompt_select_vectordb = (
        
        
        '''
        You are given a user query, and context about the query. The query contains filter values, values for which the user wants to filter SQL data on. 
        The filters should have some context to them which should help determine which column they belong to. The context is provided as a sentence that describes
        what columns will be used for each filter value. Your job is to match the database names, with the filter values provided in the context. 
        
        Column Names: 
        - Name: Name of the recipient.
                - Name: Name of the recipient.
                - State: State information.
                - Country: Country information.
                - Product_ID: Product identifier.
                - Region: Client region (e.g. AMERICAS, EUROPE, ASIA).
                - Group_A: Primary product group.
                - Replace and add your own column names here.


    Select the vector db names that are needed to perform fuzzy search for each filter value described in the context. The context will be used later on to build 
    a SQL query. The context has information about the filter values in a previous user query. The context for each filter is supposed to help determine which column and therefore which vector database to use to perform a search on that value.
    Filter values are NOT the names of teh columns, but actual values that would be found in a column. 
    If a value is not in the context, then that value is not a filter value, and should be ignored, and not included in the response. The filter values in the context are provided in a message looking like "Column3 will be used to filter on 'Value1' and Column4 'Value2'.".    
    Return a list of the vector databases that are needed for each individual filter value in the user query. If the same vector database is needed for multiple
    values in the user query, add the duplicate vector database name to the list. The order of the vector databases in the list should match 
    the order of the filter values in the user query. If a filter value in the user query does not have a corresponding vector database, return None for that value.
    Two filter values should not use the same vector database unless the context indicates that the values are in the same column. If the context for multiple filter values is different, then they should use different vector databases, or none if the context idicates to ignore the value. 

        Vector databases have the name of the column in their name. 
        -Only match the filter values where context indicate they refer to one of the columns above.
        -Return a list of lists where the first list has the vector data base names, and the second list has the filter values that match the vector database names.
        -If a filter value does not match any of the vector database names, do not include it in the response.
        -If no matches are found then return an empty list.

        Example:
        - User Query: "Get the total sales for AC-100 for Name john doe."
        - Context: "Name will be used to filter on 'John Doe'and Group_A will be used to filter on 'AC-100'."
         Expected Result: "[['index_folder_name','faiss_index_vectordb_name'], ['john doe','AC-100']]"

        - User Query: "Get the total bookings for Allan this year grouped by region" 
        - Context: "Name will be used to filter on 'Allan'."
          Expected Result: "[['Name'], ['Allan']]"

        Very Important Format Requirements:
        - Your response should be a string representation of a list of lists. The first list should contain the vector database names as strings, and the second list should contain the filter values that match the vector database names represented as strings as well.
        - Your response will be directly evaluated using ast.literal_eval(response) to parse it, so make sure it is formatted correctly, and you dont have any missing or extra commas, brackets, or quotes, or any extra text outside of the brackets.
        - If no matches are found between vector databases and filter values based on the column that they each refer to, then return [[None],[None]] 
        - The context has every filter value that needs to be matched to a vector database. The context lets you know which column each filter value belongs to. Use this to 
        determine which vector database to use for each filter value. You should match every filter in the context to a vector database, unless the context for a filter value indicates to ignore it, or
        if the context for the filter value indicates it does not belong any of the columns listed above.        

        User Query: {user_query}
        Vector Database Names: {vector_db_names}
        Context: {context}
        '''

    )
    
    prompt_update_filters = (
            '''You are given the following inputs:
            -  A user query that contains filter values
            -  A list of filter values to consider for this specific task 
            -  A set of messages notifying that a filter value matched a specific value in the database, or a message indicating that no matches were found and user selection is needed
            -  The response from the user which indicates their selection of values for each filter value that needed clarification.
                selection can either be numbers, or the actual value
            -  A message containing the context for each filter value which helps determine which column the filter value belongs to.
            - If a filter value is a Customer Name or a Dealer Distributor, then in the updated query, indicate that you are looking for values
            that contain the filter value, rather than an exact match. You can you wording such as "where  Name contains 'filter value'" or "Region 'filter value'".
            
            Task:
            -  Update the filter values in the user query with the selected values provided by the user.
            -  A user might select multiple values for a filter value, which indicates that the filter value should be updated with all the selected values for that corresponding filter. 
            -  Since the user is only given a total of 6 options per filter, the user might choose to select all values that contain a specific keyword, word, phrase, or words. In this case replace the filter with like '%keyword%, or like '%word%', or like '%phrase%', or like '%keyword', or like 'word%', depending on if they want to match the keyword at the beginning, end, or anywhere in the string.
            -  If a message in the set of messages indicates that a filter value matched exactly with a value in the database, then perform the replacement of the filter value with the value in the database that got matched with.
            -  Use the filter values provided in the list of filter values to consider for this specific task to determine which filter values need to be updated.
            -  Use the context provided and context within the user query itself to append a context to the user query at the end. The context should be in parentheses, and should be formatted as (Filter Value: Context)
            -  If the user query already had a context, but additional context for a filter value needs to be added, the append the new context to the existing context in the user query, if the existing context is still valid.
            -  The only filter values that should be in the context are the ones provided as Filter Values/Headers, or the ones already in the context at the end of the user query. Do not include any other filter values in the context, 
            that do not already appear on a context attached to the user query, or in the Filter Values/Headers list.
            Format Requirements:
            -  Your response should be the updated user query with the filter values replaced with the selected values provided by the user.
            -  The updated user query should be a complete sentence.
            - If the user want to select all values that start with, contain, or end with a specific word, then change the user query to reflect that. It doesn't mean replace the filter with all values that were listed and have the word in them.
            -  Only update the filter values, do not change any other part of the user query. Enclose the filter values in single quotes
            - Example of how query with context should look like:  "New Query: Get the total sales for AC-1000 for John Doe. ('AC-1000': Group_A, John Doe': Name)"
            - Only respond with the updated user query. Do not include any extraneous text, explanations, or punctuation outside of the user query. Do not label the updated query
            as 'Updated Query:' or anything similar. Just give the updated query itself. 

            User Query: {user_query}
            Filter Values/Headers: {filter_values}
            Messages with Selection(s) or Matches: {messages}
            User Selection: {user_selection}
            Query Context: {query_context}  


            '''
    )
    

    build_sql_prompt = (
            '''As an MS SQL expert, please create a syntactically correct MS SQL query in response to the given input question.   Adhere to the following guidelines:

            - List specific column names instead of using "SELECT *", even when all columns are needed.
            - Use only read-only operations (e.g., SELECT) and avoid commands that modify the database (like UPDATE, CREATE TABLE). (most important!).
            - For the current date, use CAST(GETDATE() as date).
            - Focus on the provided table and column information. Use columns that exist in the specified tables.
            - Replace 'LIMIT' with the 'TOP' clause in MS SQL queries.
            - For price data, default to USD currency columns, unless local price is specified.
            - Use the 'Qty' column for total units or quantities.
            - It is crucial to format numerical results with two decimal places and a thousands separator. Please ensure to use the 'FORMAT' function in SQL for formatting currency and numerical outputs, especially in computations like summing or subtracting prices and costs. (important!)
            - If result is expected to be currency such as profit, or sales price, please format the result as currency with a dollar sign, thousands separator, and two decimal places.
            - Exclude extraneous explanations; only return the query in MS SQL syntax. Your must be a runnable sql query!
            - Use SUM instead of SELECT COUNT(*) for numerical aggregations.
            - If you need to select rows use the headers provided in the schema_info instead of using SELECT *.
            - Format quantity values with a thousands separator.
            - If user is looking for all Group_A, Name, Region, State, Country (replace with your own) values that meet certain criteria, then assume they want to see all unique values that meet the criteria. Example: "Which PG values values are USD_Total_Price > 1000" means they want to see all unique PG values that have a USD_Total_Price > 1000.
            - When translating a natural language query into SQL, particularly when the request involves calculating rankings or comparisons for each year or month, you should utilize the PARTITION BY clause within window functions instead of solely using GROUP BY. 
                The PARTITION BY clause is essential for dividing the dataset into distinct partitions (like per year or per month) to perform calculations independently within each partition. This approach is crucial for scenarios where you need to identify top performers, trends, or comparisons within each time segment.
            - For aggregate calculations that summarize data across the whole dataset, continue to use GROUP BY"
            - Use CTEs for better organization and readability of complex queries only when necessary. Unnecessary  use of CTE's can make queries confusing and introduce errors.
            - Utilize for advanced data manipulation tasks like rankings or running totals when needed.
            - Pivot Tables: Employ for transforming time-based data to improve data presentation, especially in scenarios involving grouping by time.
            - Use unique aliases for modified or computed columns within a query to avoid conflicts, especially in complex queries involving CTEs or formatting. Ensure the final alias presented to the user is simple and intuitive, reserving more descriptive interim aliases for internal query logic only.
            - If user asks followup question, make sure to keep the same filters, groupings, and sorting as the previous query unless the user specifies otherwise. If question is extremely unlikely to be a followup, you can ignore this rule.
            - Do not use formatting aliases in order by clause
            - When filtering on Client Name, or Dealer Distributor, use the LIKE operator with wildcards. For example, if the user asks for sales for a customer named "John Doe", use WHERE Customer_Name LIKE '%John Doe%'.
            
            -------------------------------------------------------------------------------------------------   
            These questions relate to data regarding bookings and sales records. Bookings are orders placed, orders booked, and Sales are orders shipped, or sold. 
            There are two table BOOKINGS and SALES accordingly, you may need to reference both tables or one of them depending on the question.
            I will provide you with the schema_info for each table that is relevant to the question. If asking question about sales and bookings
            make sure to use join accordingly or use the right table. There are no primary keys in the tables, and no trivial way to 
            to map each row in the bookings table to a row in the sales table, it depends on the context of the question, so you might have to 
            use append feature or Union to combine the two tables. 
            -------------------------------------------------------------------------------------------------
            Schema for Tables and Columns to be considered: 
            {schema_info}

            Here is some information about some of the columns , not all may be on the table you are working with, 
            but it is a good reference for you to use when creating your query:

                - Name: Name of the recipient.
                - State: State information.
                - Country: Country information.
                - Product_ID: Product identifier.
                - Add column names: Description of what the column contains, what it is used for, and how users might refer to it, or any keywords that refer to the column.
                ...

            (Note: Do not include the follwoing tables...)
            -------------------------------------------------------------------------------------------------
          
            If use asks for info or metrics over (something), such as avg sales over each year, or top 3 most profitable products over each month or year, make sure each 
            segment is calculated independently and that only the number of rows indicated show up for each year. This is done by using the PARTITION BY clause in window functions. User might use keywords like "each", "per", "over", "for each", "for every" etc.
            Windowed functions can only appear in the SELECT or ORDER BY clauses. They are forbidden in the WHERE clause. Double check that the query is correct mssql syntax.
            When filtering on a string, if the filter value has quotes, it indicates exact match. If filter string value is not enclosed in single or double quotes, then use the LIKE operator with wildcards and keyword AND for each word in the string. For example, if the user asks for sales for a customer named "John Doe", use WHERE Customer_Name LIKE '%John%' AND Customer_Name LIKE '%Doe%'.
            -------------------------------------------------------------------------------------------------

            Your response should exclusively contain the MSSQL query in the correct syntax, utilizing 'TOP' instead of 'LIMIT', without any extra explanations or text. (most important!)
            Your response should NEVER be handle_query or chat_with_gpt. (most important!)

            -----------------------------------------------------------------------
            You will be provided with a conversation history of the system message, user query, and assistant response.
            Use previous conversation history to understand the context of the user query and provide a relevant response.Remember to strictly follow the rules provided
            and make sure to structure sql query such that the result of the query is in the correct format, accurate, and easy to understand.
            Do not hallucinate information or make up data, or create fictitious company names or product names

        ''''')
    

    validate_sql_prompt = '''

            GPT, please analyze and refine the SQL query below based on the provided user query, execution results, or error message. The sql query was generated by you
            based on the user query and system prompt.Sometimes you make mistake though and the query may not be correct. You sometimes do things that are against the 
            rules provided in the system prompt.
            You are given the chat history of the user query, generated SQL query, and the results of the query execution.As well as the original system prompt
            to the previous gpt call and the query that was used to generate the SQL query. As user input you wil be given the query, the generated SQL query, and the results of the query execution.
            The queries in general relate to either the bookings or sales tables in the database or both. Questions regarding sales
            shipped orders, products, are in the sales table, and questions about orders placed or booked/unshipped orders are in the bookings table.
            Each row in the sales table is a shipped order or delivered product, and each row in the bookings table is an order that has been placed but not yet shipped.
            ------------------------------------------------------------------------------------------------
            Important Rules:
            The revised SQL should strictly adhere to MSSQL syntax and conventions without any extraneous text or comments.
            The objective is to correct and improve the query to ensure it is syntactically correct, aligns with the user's intent, and the results are presented in a clear, readable format, potentially using data pivoting where appropriate.
            Use PIVOT to move data from rows to columns or vice versa, and format the output to enhance readability. Especially when grouping by year, month, or other time-based columns.
            Use PIVOT whenever it can help to present the data in a more readable format. Remember PIVOT can only be used with aggregate functions.
            Move data from rows to columns or vice versa to enhance readability. Especially when grouping by year, month, or other time-based columns.
            If sql query is already correct and results are as expected, and extra pivoting or formatting is not needed, please return the same query.
            Your response should be a clean, executable MSSQL query, free from any non-SQL text or annotations. If original query had extraneous text, please remove it.
            The goal is to enhance the accuracy and readability of the output, adhering to MSSQL standards and ensuring the numerical data integrity remains unchanged if original query results were correct.
            - Format currency accordingly and ensure quantity or count values are formatted with a thousands separator and no decimal places.
            - Queries should never edit the database, only read from it. Pay attention to user intent and the results of the query execution
            and how it may relate to the conversation history.
            -If the question is a follow up make sure to take that into account and keep 
            consistency (reference the correct tables and columns, and use or maintain the proper joins and filters). 
            When filtering on a string, use the LIKE operator with wildcards unless the user specifies an exact match or 'only' in the query.
            ---------------------------------------------------------------------------------------------------
            Most Important Above All:
            Please remember not to include extraneous text, comments, or annotations in your response. Your answer should always begin with SELECT or WITH.
            The entirety of your response will be ran as a single MS SQL query, so do not add explanations or comments to the validation response.No text should precede the validated SQL query or follow it.
            The response should NEVER be chat_with_gpt or handle_query!!! It should always be a valid SQL query derived from user query and schema and prompt.
            If the query says chat_with_gpt or handle_query, then the response is incorrect, and you should fix it and return a valid SQL query. Again never return chat_with_gpt or handle_query.

            Use following schema info to help you validate the query: {schema_info}
        '''
    
    explain_results_prompt = '''Explain how you got the results. Do not 
                                regurgitate the same sql query. Instead explain the results in a way that is easy to understand.
                                If you had to make assumptions point those out to the user. Act as if the user dont know anything about the data or SQL
                                Keep your responses short and concise. Do not reply with chat_with_gpt or handle_query. Just 
                                the results of the query and how you got them, or any errors that may have occurred.'''
    


    generate_headers_prompt = '''Generate header names given the initial query,
                         the SQL query, the first row of the result. You should return this in 
                          a list format. For example, ['header1', 'header2', 'header3']. 
                          If no headers are possible, return generic headers. Never
                          return None or an answer that is not a list of strings. The length
                          of header or number of columns depends the number of columns the result has. You can 
                          use the schema_info to help generate the headers.Here is the Schema: {schema_info}.
                          Your response should not include any extra text or punctuation outside of the brackets.
                          Do not make the headers overly-specific they should be clear and simple.
                          Dont add underscores use spaces instead. Your response will be used with ast.literal_eval(response) to parse it.
                          '''
    
    chat_with_gpt_prompt = '''Provide a conversational response to the user's input. If the user is asking to change or modify data in a database, let the user know that the action is forbidden.
             Your response doesn't have to be chat_with_gpt or handle_query. It can be anything you think is appropriate.
             Keep in context of ACME sales and bookings data.or just respond in a friendly manner. You are Ada an AI assistant that helps with sales and bookings data queries.
             You may not talk about information that is not related to the sales and bookings data and midtronics. If user asks general trivia questions, let the user know that you can only help with sales and bookings data.
             The user might be asking to clarify a previous response. If the user input sounds like a data query, or follow up query, then you should indicate that in order to answer the user query you need to run an SQL query.             
             ------------------------------------------------------------
             IMPORTANT(Never respond with chat_with_gpt or handle_query. That is not your job right now!!!)
            
             You will be provided with the schema information for some tables in the database, and some database context. Use this if you need to answer
            some questions directly related to the database

            Schema Info: {schema_info}
            Database Context: {database_context}
               
             '''
    
    prompt_explain_results = '''
            Explain how the query results were obtained in a way that is easy to understand. Avoid regurgitating the SQL query itself. 
            If the result set is empty, do not assume it is due to an error; simply explain that the query returned no results, which may be the expected outcome based on the data.
            
            Focus on explaining the results clearly, as if the user has no prior knowledge of the data or SQL. If you had to make assumptions, point those out, but avoid any speculation about why results might be zero.

            Keep your response short and concise. Do not respond with "chat_with_gpt" or "handle_query"—just the explanation of the query results, or any errors that may have occurred.

            If wildcards were used for filtering, inform the user that they can make the search more strict by putting the filter in quotes and adding the keyword "exact match" or "exactly."

            The provided results may be a preview, so let the user know that the displayed results are limited and to download the full dataset if they want to see all rows.

            If there was an error in the query results, use the provided schema info and database context to diagnose the issue and explain it to the user without speculating. 
            Do not hallucinate data or results—only use the data returned by the query, along with schema information.

            If you are confident in a correction to the SQL query, return the corrected version.
            
            Schema Info: {schema_info}
            Database Context: {database_context}
        '''
    
    prompt_select_relevant_tables = '''
        Return the names of ALL the SQL tables that MIGHT be relevant to the user question. 
        The tables are:

        {table_names}

        Remember to include ALL POTENTIALLY RELEVANT tables, even if you're not sure that they're needed.
        Your response should be a list of table names, separated by commas. When in doubt, include the table name(s).
        Format response as such: ['table1', 'table2', 'table3'...]. Always include tables related to Tools.Don't add extra text or punctuation outside of the brackets.
        so that I can use ast.literal_eval(response) on the list to parse it. Always include the Tests table as well. 
        '''
    prompt_generate_headers = '''

        Generate header names given the initial query,
        the SQL query, the first row of the result. You should return this in 
        a list format. For example, ['header1', 'header2', 'header3']. 
        If no headers are possible, return generic headers. Never
        return None or an answer that is not a list of strings. The length
        of header or number of columns depends the number of columns the result has. You can 
        use the schema_info to help generate the headers.Here is the Schema: {schema_info}.
        Your response should not include any extra text or punctuation outside of the brackets.
        Do not make the headers overly specific they should be clear and simple.
        Dont add underscores use spaces instead. Your response will be used with ast.literal_eval(response) to parse it.
        
        ''' #Schema_info is retrieved and filled in during runtime.
    
    prompt_check_sql_query_needed = '''
        You are given a message generated by ChatGPT. If the message contains an SQL query, or if the message indicates that an sql query needs to be ran to 
        answer what ever question the user asked, then return True. If the message does not contain an SQL query, or if the message indicates that an SQL query does not need to be ran to answer the user query, then return False.
        If the message indicates that the bot is going to run an SQL query, or handle a request then return True.
        If a message is explaining the results or how the SQL query was constructed, then return False. If the message indicates that there was an error with the SQL query,
        and then shows the correct one, then return True. 
        
        Do not include any extra text or punctuation. Only return True or False.
        
        '''
    
    prompt_has_name = '''
    You are given a user query and vector database names. Determine if the user query contains filter values that are names of people, companies, or a combination of people, dealers, and or companies with locations. 
    If user input says for example "Get the total sales for ACME America", then "ACME America" is a combination of a company name and a region and should be considered one filter value, and a name.
    Your job is to return the list of filter values that are names of people, companies,dealers or a combination of people, dealers, and or companies with locations. Return as a python list of strings.
    Where each string is a filter value. If no names fit the criteria then return an empty list.

    Important: 
    Always return only a list of filter value strings, or an empty list. Do not add any extra text or punctuation outside of the brackets.
    Remember to format the response as a valid python list of strings. Your response will be evaluated used with ast.literal_eval(response) to parse it.
    Make sure you dont add any extra commas, brackets, or quotes, and make sure you dont forget any commas, brackets, or quotes.
    '''
    prompt_combine_messages = '''
    You are given two messages: one from the user and one from the system. Your task is to combine these messages into one cohesive, clear, and concise message.

    - Include every piece of relevant information from both messages.
    - If a filter value has been clarified in either message, reflect this clarification in the combined message, and remove any previous requests for clarification for that filter value.
    - For filter values that have not been clarified, include only one clarification question per filter value, combining any similar questions.
    - Avoid redundancy to ensure the message is easy to understand.
    - If both message 1 and message 2 contain a clarification question for the same filter value, include only the clarification question from message 1 and not message 2.
    - If message 2 already contains a clarification for a filter value, and message 1 is asking for clarification on that same value, then do not include a clarification question for that filter 
    - Any filter values that have been clarified must go first in the message, followed by any remaining filter values clarification questions.
    - Make sure to maintain clarity and conciseness throughout the message.
    - Each filter value should only be mentioned once in the message. 
    - Avoid contradictions. If a given columns is going to be used for a filter value, then dont ask to clarify what column the filter value belongs to or refers to.
    - If a filter value is is composed of a company name and location, and there was no context provided for that value, then ask if the value is one single value or two separate values. Example, if filter value is JLR Dallas, somewhere in the combined message add "or, is 'ACME Dallas'  one value or two separate values?"
    - Filter values should only be mentioned once in the message.If a filter value was matched to a column, then dont ask to clarify what column the filter value belongs to or refers to, even if one of the messages asks for clarification on that filter value.
    - When combining messages, make sure to make the context(column names) and filter values bold to make them stand out.
    Example:
        Message 1: 'The filter value 'AC' did not match any known columns. Please clarify if it refers to any of the following columns: 'ColumnA', 'ColumnB',  'ColumnC, or 'ColumnD'.'

        The filter value 'John Doe' matched multiple columns. Please clarify if it refers to 'ColumnA', 'ColumnB'.'
        
        Message 2: 'Column5 will be used to filter on 'AC'. Does 'John Doe' refer to the , ColumnA, ColumnB, or the ColumnC?'

        Combined Message(Expected Result given these two example messages): ''Column5 will be used to filter on 'AC'. The filter value 'John Doe' matched multiple columns. Please clarify if it refers to 'ColumnB', or 'ColumnC'.
        
        Message 1: 'The filter value 'A' did not match any known columns. Please clarify if it refers to any of the following columns: 'ColumnA', 'ColumnB',  'ColumnC, or 'ColumnD'.'

        Message 2: ''X' will be used to filter on 'A'. Does 'Y' refer to the , Sales Rep, Ship To Sales Rep, or the Customer Name?'

        Combined Message: ''X' will be used to filter on 'A'. Please clarify if 'Y' refers to the  Sales Rep, Ship To Sales Rep, or the Customer Name.'
        (In the example above, 'A' and 'Y' are filter values, and 'X' is a column name. Basically if a value is matched with a column, then dont ask to clarify what column the value belongs to, even if one of the messages asks for clarification on that value.)
        
        Do similar combining for all filter values and clarification questions in the messages. Make sure to maintain clarity and conciseness throughout the message.
        The examples above are examples of how to combine contradicting messages, and how to combine messages that are not contradicting.
    '''

    prompt_clarification_needed = '''You are given a message. Your job is to determine if the message contains the word 'clarify', '?' or 'please' in it. If so, then return True. If not, then return False.
    Response should always be a python boolean. 

    Example: 'AC will be used to filter on 'ac'. Does 'John Doe' refer to the  ColumnA, ColumnB, or the ColumnC?'
    Example Response: True

    Example: 'ColumnX will be used to filter on 'AC' and 'ColumnY' for 'Aurovindo'.'
    Example Response: False

    Only return True if the message contains a question, or the word 'clarify', or 'please'. 

    Do not include any extra text or punctuation. Only return True or False. Your response will be evaluated used with ast.literal_eval(response) to parse it.
    
    '''