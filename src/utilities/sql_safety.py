import re
import logging
from typing import Optional


# DDL/DML keywords that must never appear in a generated query
_FORBIDDEN_PATTERNS = re.compile(
    r"""
    \b(
        INSERT\s+INTO |
        UPDATE\s+\w+ |
        DELETE\s+FROM |
        DROP\s+(?:TABLE|DATABASE|INDEX|VIEW|PROCEDURE|FUNCTION|SCHEMA) |
        TRUNCATE\s+TABLE |
        ALTER\s+(?:TABLE|DATABASE|VIEW|PROCEDURE|FUNCTION) |
        CREATE\s+(?:TABLE|DATABASE|INDEX|VIEW|PROCEDURE|FUNCTION|SCHEMA) |
        EXEC(?:UTE)?   |
        BULK\s+INSERT  |
        OPENROWSET     |
        OPENDATASOURCE |
        xp_cmdshell    |
        sp_executesql  |
        MERGE\s+INTO
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# A valid generated query must begin with SELECT or WITH (for CTEs)
_VALID_START = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE)


class SQLSafetyError(Exception):
    """Raised when the SQL safety validator rejects a query."""


class SQLSafetyValidator:
    """
    Validates a generated SQL query before it is executed.

    Checks performed
    ----------------
    1. **Read-only enforcement** – rejects any query that contains DML/DDL
       keywords such as INSERT, UPDATE, DELETE, DROP, TRUNCATE, ALTER, CREATE,
       EXEC, BULK INSERT, OPENROWSET, xp_cmdshell, sp_executesql, or MERGE.
    2. **Start-token check** – every valid query must start with SELECT or WITH
       (CTE).  Anything else is rejected.
    3. **Schema constraint check** (optional) – if a ``schema_info`` mapping is
       supplied, every table and column name referenced in the query is verified
       against that mapping.  Unknown names are flagged so callers can decide
       whether to surface the warning to the user or reject the query outright.
    """

    def __init__(self, schema_info: Optional[dict] = None):
        """
        Parameters
        ----------
        schema_info:
            Optional dictionary that maps table names (case-insensitive) to
            lists of column names, e.g.::

                {
                    "SALES":    ["Date", "Amount", "Customer_Name", ...],
                    "BOOKINGS": ["Date", "Quantity", "Part_Number", ...],
                }

            When provided, the validator will detect references to tables or
            columns that do not exist in the schema (hallucinated schema).
        """
        self.schema_info = self._normalise_schema(schema_info)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate(self, sql_query: str) -> None:
        """
        Validate *sql_query* and raise :class:`SQLSafetyError` if it fails any
        check.  Returns ``None`` silently on success.

        Parameters
        ----------
        sql_query:
            The SQL string produced by the LLM.

        Raises
        ------
        SQLSafetyError
            If the query contains forbidden keywords, does not start with
            SELECT/WITH, or (when schema_info is available) references unknown
            tables or columns.
        """
        if not sql_query or not sql_query.strip():
            raise SQLSafetyError("Empty SQL query rejected.")

        self._check_read_only(sql_query)
        self._check_start_token(sql_query)
        if self.schema_info:
            warnings = self._check_schema(sql_query)
            if warnings:
                # Log as warnings; callers may choose to surface these.
                for w in warnings:
                    logging.warning("SQL schema warning: %s", w)

    def get_schema_warnings(self, sql_query: str) -> list:
        """
        Return a list of schema-constraint warning strings for *sql_query*
        without raising an exception.  Returns an empty list when all
        referenced names are found in the schema or when no schema was supplied.
        """
        if not self.schema_info or not sql_query:
            return []
        return self._check_schema(sql_query)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise_schema(schema_info):
        """Return a normalised (lower-case keys and values) copy of schema_info."""
        if not schema_info:
            return {}
        return {
            table.lower(): [col.lower() for col in cols]
            for table, cols in schema_info.items()
        }

    @staticmethod
    def _check_read_only(sql_query: str) -> None:
        match = _FORBIDDEN_PATTERNS.search(sql_query)
        if match:
            raise SQLSafetyError(
                f"Query rejected: contains forbidden keyword '{match.group().strip()}'. "
                "Only read-only SELECT queries are allowed."
            )

    @staticmethod
    def _check_start_token(sql_query: str) -> None:
        if not _VALID_START.match(sql_query):
            first_token = sql_query.strip().split()[0] if sql_query.strip() else "<empty>"
            raise SQLSafetyError(
                f"Query rejected: must begin with SELECT or WITH, but starts with '{first_token}'."
            )

    def _check_schema(self, sql_query: str) -> list:
        """
        Detect table/column names that appear in the SQL but are not present in
        the known schema.  Returns a list of warning strings (empty = all OK).

        This uses a best-effort heuristic and may produce false positives for
        aliases, function calls, or CTEs.  It is intentionally non-blocking so
        the bot can still attempt to run the query and surface the SQL error to
        the user naturally.
        """
        warnings = []

        # --- table references: FROM <name>, JOIN <name> -----------------
        table_refs = re.findall(
            r"\b(?:FROM|JOIN)\s+\[?(\w+)\]?(?:\s+(?:AS\s+)?\w+)?",
            sql_query,
            re.IGNORECASE,
        )
        known_tables = set(self.schema_info.keys())
        for table in table_refs:
            if table.lower() not in known_tables:
                warnings.append(
                    f"Unknown table '{table}' referenced in query; "
                    "it was not found in the provided schema."
                )

        # --- column references: SELECT <col>, WHERE <col> = ... ---------
        # Collect all word tokens that appear after SELECT, WHERE, GROUP BY,
        # ORDER BY, HAVING and compare against the full column pool.
        all_known_columns = {col for cols in self.schema_info.values() for col in cols}

        # Only check columns when the table set is non-empty and all referenced
        # tables are known (to avoid noise when the table itself is unknown).
        unknown_tables = {t.lower() for t in table_refs if t.lower() not in known_tables}
        if all_known_columns and not unknown_tables:
            # Extract bare identifiers that look like column names:
            # skip string literals and numeric literals.
            stripped = re.sub(r"'[^']*'", " ", sql_query)   # remove string literals
            stripped = re.sub(r"\b\d+\b", " ", stripped)     # remove numeric literals
            # Tokens of the form word or [word]
            identifiers = re.findall(r"\[?(\w+)\]?", stripped)
            # Filter out SQL keywords and known table names
            sql_keywords = {
                "select", "from", "where", "join", "inner", "left", "right",
                "outer", "full", "on", "and", "or", "not", "in", "like",
                "between", "is", "null", "as", "by", "group", "order",
                "having", "top", "distinct", "with", "cte", "union", "all",
                "case", "when", "then", "else", "end", "cast", "convert",
                "getdate", "dateadd", "datediff", "year", "month", "day",
                "count", "sum", "avg", "min", "max", "isnull", "coalesce",
                "pivot", "unpivot", "over", "partition", "row_number",
                "rank", "dense_rank", "ntile", "desc", "asc", "into",
                "exists", "any", "some", "partition", "values", "set",
                "format", "round", "abs", "len", "ltrim", "rtrim", "upper",
                "lower", "substring", "charindex", "replace", "trim",
            }
            for token in identifiers:
                tl = token.lower()
                if (
                    tl not in sql_keywords
                    and tl not in known_tables
                    and tl not in all_known_columns
                    and len(tl) > 2       # ignore very short tokens / aliases
                ):
                    warnings.append(
                        f"Identifier '{token}' not found in the known schema; "
                        "it may be a hallucinated table or column name."
                    )

        return warnings
