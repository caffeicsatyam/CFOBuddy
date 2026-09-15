from tools.chart import generate_chart, prepare_chart_data  
from tools.search import search_financial_docs
from tools.lookup import exact_lookup, list_available_files
from tools.web_search import web_search
from tools.finance import get_financial_data
from tools.sql import sql_query, list_tables, get_sql_examples
from tools.reranker import rerank_docs
from langgraph.prebuilt import ToolNode  

all_tools = [
    search_financial_docs, 
    exact_lookup, 
    list_available_files, 
    web_search, 
    get_financial_data, 
    sql_query, 
    list_tables, 
    get_sql_examples,
    generate_chart,
    prepare_chart_data
]

# ==========================
# SPECIALIZED TOOL SETS
# ==========================

# Web search tools
web_search_tools = [web_search]
web_search_tool_node = ToolNode(web_search_tools)


basic_tools = [
    search_financial_docs, 
    exact_lookup, 
    list_available_files, 
    list_tables,
    get_sql_examples,
    generate_chart, 
    prepare_chart_data,
    sql_query,
    get_financial_data,
    web_search,
]
internal_tool_node = ToolNode(basic_tools)

sql_tools_list = [
    sql_query,
    list_tables,
    get_sql_examples,
    generate_chart,
    prepare_chart_data,
]
sql_tool_node = ToolNode(sql_tools_list)

# Finance tools (market data + visualization)
finance_tools = [
    get_financial_data, 
    generate_chart, 
    prepare_chart_data,
    sql_query
]
finance_tool_node = ToolNode(finance_tools)

# Export for use in graph.py
__all__ = [
    # Individual tools
    'search_financial_docs',
    'exact_lookup',
    'list_available_files',
    'web_search',
    'get_financial_data',
    'sql_query',
    'list_tables',
    'get_sql_examples',
    'generate_chart',
    'prepare_chart_data',
    # 'list_charts' removed
    
    # Tool collections
    'all_tools',
    'web_search_tools',
    'basic_tools',
    'sql_tools_list',
    'finance_tools',
    
    # Tool nodes
    'web_search_tool_node',
    'internal_tool_node',
    'sql_tool_node',
    'finance_tool_node'
    ,
    'rerank_docs'
]
