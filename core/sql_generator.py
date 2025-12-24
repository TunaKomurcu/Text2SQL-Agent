"""
SQL Generator - Interactive SQL generation with conversation history
"""

import time
import re
import sqlparse
from typing import Dict, List, Optional, Set, Tuple

from config import settings
from search import hybrid_search_with_separate_results, select_top_tables_balanced
from schema import (
    load_fk_graph, 
    build_compact_schema_pool, 
    format_compact_schema_prompt_with_keywords,
    score_columns_by_relevance_separate,
    find_minimal_connecting_paths,
    extract_all_tables_from_paths
)
from schema.builder import normalize_table_name
from sql import (
    extract_sql_from_response, 
    auto_fix_sql_identifiers, 
    clean_meaningless_where_clauses,
    run_sql,
    unqualify_table
)
from core import (
    get_llm_instance,
    generate_strict_prompt_dynamic_only,
    SQLErrorAnalyzer,
    STATIC_PROMPT
)
from schema.path_finder import _filter_maximal_paths

# Constants
MAX_PATH_HOPS = settings.MAX_PATH_HOPS
MAX_INITIAL_RESULTS = settings.MAX_INITIAL_RESULTS
TOP_COLUMNS_IN_CONTEXT = 7  # Default value


class InteractiveSQLGenerator:
    """Class for interactive SQL generation and error correction."""
    
    def __init__(self):
        self.error_analyzer = SQLErrorAnalyzer()
        self.max_retries = 3
        self.conversation_history = []
        self.current_schema_pool = {}  # store schema pool
        self.llm = get_llm_instance()  # get LLM instance from global cache
        self.last_successful_query = None  # Remember successful queries
        self.conversation_context_window = 3  # window of last N conversations
        self.fk_relationships = {}  # store FK-PK relationships
        self.similarity_threshold = 0.6  # similarity threshold
        self.query_similarity_cache = {}  # cache for query similarities
        self.previous_conversation_fk_cache = {}  # cache of previous conversation FK-PK paths
        self.dynamic_prompt_fk_cache = {}  # cache for FK paths in dynamic prompts

    def _make_fk_cache_keys(self, user_query: str, sql_content: Optional[str] = None) -> Tuple[str, Optional[str]]:
        """
        Create consistent cache keys:
        - simple_key: hash of user_query (backward-compatible)
        - combo_key: hash of user_query + sql_content (more specific)
        """
        try:
            simple_key = f"fk_simple_{hash(user_query)}"
            combo_key = f"fk_combo_{hash(user_query)}_{hash(sql_content)}" if sql_content is not None else None
            return simple_key, combo_key
        except Exception as e:
            print(f"🔍 [_make_fk_cache_keys] Key oluşturma hatası: {e}")
            return f"fk_simple_{hash(user_query)}", None

    def _cache_current_fk_paths(self, natural_query: str, paths: Dict, sql_content: Optional[str] = None):
        """Cache the FK paths for the current query (store under both simple and combo keys)."""
        try:
            if not hasattr(self, 'dynamic_prompt_fk_cache'):
                self.dynamic_prompt_fk_cache = {}

            fk_paths = self._format_fk_paths_like_previous_dynamic(paths)
            if not fk_paths:
                # still write empty string under simple key (for future fallback)
                simple_key, combo_key = self._make_fk_cache_keys(natural_query, sql_content or "")
                self.dynamic_prompt_fk_cache[simple_key] = ""
                if combo_key:
                    self.dynamic_prompt_fk_cache[combo_key] = ""
                print(f"🔍 [_cache_current_fk_paths] FK paths empty, cached empty string.")
                return

            simple_key, combo_key = self._make_fk_cache_keys(natural_query, sql_content or fk_paths)

            # store
            self.dynamic_prompt_fk_cache[simple_key] = fk_paths
            if combo_key:
                self.dynamic_prompt_fk_cache[combo_key] = fk_paths

            print(f"🔍 [_cache_current_fk_paths] Current query FK paths cached (len={len(fk_paths)})")
        except Exception as e:
            print(f"⚠️ [_cache_current_fk_paths] Cache yazma hatası: {e}")

    def _format_fk_paths_like_previous_dynamic(self, paths: Dict[str, List[Dict]]) -> str:
        """Format FK paths like previous dynamic prompt"""
        if not paths:
            return ""

        # Filter: take only maximal chains
        filtered_paths = _filter_maximal_paths(paths)

        relationship_lines = []

        for path_key, hops in sorted(filtered_paths.items()):
            if not hops:
                continue

            parts = []

            for hop in hops:
                fk_table = hop.get("fk_table") or hop.get("from")
                fk_col = hop.get("fk_column") or ""
                pk_table = hop.get("pk_table") or hop.get("to")
                pk_col = hop.get("pk_column") or hop.get("ref_column") or ""

                if fk_table and fk_col and pk_table and pk_col:
                    parts.append(f"{fk_table}.{fk_col}(FK) --> {pk_table}.{pk_col}(PK)")

            if parts:
                chain = " ---- ".join(parts)
                relationship_lines.append(f"• {chain}")

        if not relationship_lines:
            return ""

        return "\n".join(relationship_lines)

    def _add_to_conversation_history(self, role: str, content: any, query_type: str = "general"):
        """Append a new message to the conversation history."""
        # Add logic to clean up previous cache
        if role == "user" and query_type == "user_query":
            # When a new user query arrives, trim the previous conversation cache a bit
            if hasattr(self, 'previous_conversation_fk_cache'):
                cache_size = len(self.previous_conversation_fk_cache)
                if cache_size > 10:  # If cache has grown too large
                    # Remove the oldest 5 entries
                    keys_to_remove = list(self.previous_conversation_fk_cache.keys())[:5]
                    for key in keys_to_remove:
                        del self.previous_conversation_fk_cache[key]
                    print(f"🔍 [CACHE_CLEANUP] {len(keys_to_remove)} old cache entries cleaned")
        
        self.conversation_history.append({
            "role": role,
            "content": content,
            "timestamp": time.time(),
            "type": query_type
        })
        
        # Keep the last 20 messages (for performance)
        if len(self.conversation_history) > 20:
            self.conversation_history = self.conversation_history[-20:]

    def _get_extended_conversation_context(self) -> str:
        """Get extended conversation context including FK-PK relationships."""
        if not self.conversation_history:
            return ""
        
        # Get last 3 user-assistant pairs
        pairs = self._get_previous_pairs_from_history(limit_pairs=3)
        
        # ✅ If no conversation pairs, return empty string (don't add headers)
        if not pairs:
            return ""
        
        context_parts = []
        context_parts.append("=== ÖNCEKİ KONUŞMALAR (FK-PK İLİŞKİLERİ İLE) ===\n")
        
        for user_msg, assistant_msg in pairs:
            user_query = user_msg.get("content", "")
            sql_content = assistant_msg.get("content", "")
            
            # Add user query
            context_parts.append(f"KULLANICI SORUSU: {user_query}")
            
            # Add FK-PK relationships (if applicable)
            fk_context = self._get_previous_conversation_fk_context_correct(user_msg, assistant_msg)
            if fk_context:
                context_parts.append("FK-PK İLİŞKİLERİ:")
                context_parts.append(fk_context)
            
            # Add SQL
            context_parts.append(f"SQL: {sql_content}\n")
        
        context_parts.append("=== YUKARIDAKİ KONUŞMALARI DİKKATE AL ===\n")
        
        return "\n".join(context_parts)

    def _get_previous_pairs_from_history(self, limit_pairs: int = 3) -> List[Tuple[Dict, Dict]]:
        """Return up to `limit_pairs` most recent user->assistant(successful_sql) pairs."""
        pairs: List[Tuple[Dict, Dict]] = []
        try:
            history = list(self.conversation_history)  # copy
            i = len(history) - 1
            # scan backwards to find user->assistant pairs
            while i >= 0 and len(pairs) < limit_pairs:
                item = history[i]
                if item.get("type") == "successful_sql":
                    # assistant SQL found; search backwards for the preceding user_query
                    j = i - 1
                    while j >= 0:
                        prev_item = history[j]
                        if prev_item.get("type") == "user_query":
                            # found user query
                            pairs.insert(0, (prev_item, item))
                            break
                        j -= 1
                i -= 1
        except Exception as e:
            print(f"⚠️ _get_previous_pairs_from_history hatası: {e}")
        
        return pairs

    def _get_previous_conversation_fk_context_correct(self, user_msg: Dict, assistant_msg: Dict) -> str:
        """Retrieve the original FK-PK relationships referenced in the previous conversation."""
        try:
            sql_content = assistant_msg.get('content', '')
            user_query = user_msg.get('content', '')
            
            print(f"🔍 [PREVIOUS_FK_CORRECT] Önceki konuşma analizi: '{user_query[:50]}...'")
            
            # Create the unique ID for the previous conversation
            conversation_id = f"prev_{hash(user_query)}_{hash(sql_content)}"
            
            # Check if it exists in the cache
            if hasattr(self, 'previous_conversation_fk_cache'):
                cached_result = self.previous_conversation_fk_cache.get(conversation_id)
                if cached_result is not None:
                    print(f"🔍 [PREVIOUS_FK_CORRECT] Retrieved previous conversation FK relationships from cache")
                    return cached_result
            
            # Extract tables from the SQL
            tables = self._extract_used_tables_from_sql(sql_content)
            
            if not tables or len(tables) <= 1:
                print(f"🔍 [PREVIOUS_FK_CORRECT] Önceki konuşmada yeterli tablo yok: {tables}")
                if not hasattr(self, 'previous_conversation_fk_cache'):
                    self.previous_conversation_fk_cache = {}
                self.previous_conversation_fk_cache[conversation_id] = ""
                return ""
            
            print(f"🔍 [PREVIOUS_FK_CORRECT] Önceki konuşmadan çıkarılan tablolar: {tables}")
            
            # Load the FK graph
            fk_graph = load_fk_graph()
            
            # Find FK-PK relationships for the tables in the previous conversation
            paths = find_minimal_connecting_paths(fk_graph, tables, MAX_PATH_HOPS)
            
            print(f"🔍 [PREVIOUS_FK_CORRECT] Bulunan paths sayısı: {len(paths)}")
            
            # Format the relationships
            fk_context = self._format_previous_conversation_fk_context(paths, tables)
            
            if not fk_context:
                print(f"🔍 [PREVIOUS_FK_CORRECT] Önceki konuşma için FK ilişkisi bulunamadı")
                if not hasattr(self, 'previous_conversation_fk_cache'):
                    self.previous_conversation_fk_cache = {}
                self.previous_conversation_fk_cache[conversation_id] = ""
                return ""
            
            # Cache'e kaydet
            if not hasattr(self, 'previous_conversation_fk_cache'):
                self.previous_conversation_fk_cache = {}
            self.previous_conversation_fk_cache[conversation_id] = fk_context
            
            print(f"🔍 [PREVIOUS_FK_CORRECT] Önceki konuşma FK context oluşturuldu: {len(fk_context)} karakter")
            
            return fk_context
            
        except Exception as e:
            print(f"⚠️ Önceki konuşma FK context hatası: {e}")
            return ""

    def _extract_used_tables_from_sql(self, sql: str) -> Set[str]:
        """Extract ONLY the tables actually used in the SQL."""
        tables = set()
        
        try:
            # Only take table names from the FROM and JOIN clauses
            from_pattern = r'\bFROM\s+([a-zA-Z_][a-zA-Z0-9_.]*)'
            join_pattern = r'\bJOIN\s+([a-zA-Z_][a-zA-Z0-9_.]*)'
            
            from_matches = re.findall(from_pattern, sql, re.IGNORECASE)
            join_matches = re.findall(join_pattern, sql, re.IGNORECASE)
            
            for table_name in from_matches + join_matches:
                # If not schema-qualified, add the schema
                table = table_name if '.' in table_name else f"{settings.DB_SCHEMA}.{table_name}"
                tables.add(table)
            
            print(f"🔍 [EXTRACT_USED_TABLES] Tables extracted FROM the SQL: {tables}")
            
        except Exception as e:
            print(f"⚠️ SQL'den tablo çıkarma hatası: {e}")
        
        return tables

    def _format_previous_conversation_fk_context(self, paths: Dict[str, List[Dict]], original_tables: Set[str]) -> str:
        """Format FK-PK relationships in the style used by previous-conversation dynamic prompts."""
        if not paths:
            return ""
        
        filtered_paths = _filter_maximal_paths(paths)
        
        relationship_lines = []
        printed_chains = set()
        
        for path_key, hops in sorted(filtered_paths.items()):
            if not hops:
                continue
                
            parts = []
            for hop in hops:
                fk_table = hop.get('fk_table') or hop.get('from')
                fk_col = hop.get('fk_column') or ''
                pk_table = hop.get('pk_table') or hop.get('to')
                pk_col = hop.get('pk_column') or hop.get('ref_column') or ''
                
                if fk_table and fk_col and pk_table and pk_col:
                    parts.append(f"{fk_table}.{fk_col}(FK) --> {pk_table}.{pk_col}(PK)")
            
            if parts:
                chain = " ---- ".join(parts)
                if chain not in printed_chains:
                    printed_chains.add(chain)
                    relationship_lines.append(f"• {chain}")
        
        if not relationship_lines:
            return ""
        
        # Show at most 3 relationships (to avoid too many)
        if len(relationship_lines) > 3:
            relationship_lines = relationship_lines[:3]
            relationship_lines.append("• ... (other relationships)")
        
        return "\n".join(relationship_lines)

    def _enhance_natural_query_with_context(self, natural_query: str) -> str:
        """Enrich the natural language query with context"""
        enhanced_query = natural_query
        
        # Check for reference words
        reference_words = ["bu", "şu", "önceki", "yukarıdaki", "aşağıdaki", "bunu", "şunu"]
        
        if any(word in natural_query.lower() for word in reference_words):
            # Get table info from the last successful query
            last_tables = self._get_last_used_tables()
            if last_tables:
                enhanced_query += f" [REFERANS: Önceki sorguda kullanılan tablolar: {', '.join(last_tables)}]"
        
        return enhanced_query

    def _get_last_used_tables(self) -> List[str]:
        """Return tables from the last successful queries"""
        tables = set()
        for msg in reversed(self.conversation_history):
            if msg.get("role") == "assistant" and msg.get("type") == "successful_sql":
                tables.update(self._extract_tables_from_sql(msg['content']))
            if len(tables) >= 3:  # At most 3 tables
                break
        return list(tables)

    def _extract_tables_from_sql(self, sql: str) -> List[str]:
        """Extract table names from SQL"""
        tables = []
        # Find table names from FROM and JOIN clauses
        from_matches = re.findall(r'\bFROM\s+(\w+)', sql, re.IGNORECASE)
        join_matches = re.findall(r'\bJOIN\s+(\w+)', sql, re.IGNORECASE)
        tables.extend(from_matches)
        tables.extend(join_matches)
        return [t for t in tables if t]

    def _parse_llm_response(self, response) -> str:
        """Parse LLM response - EXACT COPY FROM ORIGINAL"""
        text = ""
        try:
            if hasattr(response, '__dict__'):
                response_dict = response.__dict__
                if 'choices' in response_dict and response_dict['choices']:
                    choice = response_dict['choices'][0]
                    if hasattr(choice, '__dict__'):
                        choice_dict = choice.__dict__
                        if 'text' in choice_dict:
                            text = choice_dict['text']
                        elif 'message' in choice_dict and hasattr(choice_dict['message'], '__dict__'):
                            message_dict = choice_dict['message'].__dict__
                            if 'content' in message_dict:
                                text = message_dict['content']
                    else:
                        # ✅ FIX: Handle dict choice (from original)
                        if isinstance(choice, dict):
                            if 'text' in choice:
                                text = choice['text']
                            elif 'message' in choice and isinstance(choice['message'], dict) and 'content' in choice['message']:
                                text = choice['message']['content']
            else:
                if isinstance(response, str):
                    text = response
                elif isinstance(response, dict):
                    for key in ['text', 'content', 'generated_text']:
                        if key in response:
                            text = response[key]
                            break
                    # ✅ FIX: Added from original - handle dict with choices
                    if not text and 'choices' in response and response['choices']:
                        choice = response['choices'][0]
                        if isinstance(choice, dict):
                            if 'text' in choice:
                                text = choice['text']
                            elif 'message' in choice and isinstance(choice['message'], dict) and 'content' in choice['message']:
                                text = choice['message']['content']
        except Exception as parse_error:
            print(f"⚠️ Response parsing failed: {parse_error}")
            text = str(response)
        
        return text.strip() if text else "SELECT 1"

    def _generate_smart_sql_direct(self, natural_query: str, error_context: str = "", 
                        hybrid_results: Optional[Dict] = None) -> str:
        """Generate SQL directly using conversation history and cached static prompt."""
        start_time = time.time()

        # 1. Gerekli verilerin toplanması (Hız için özet geçilmiştir)
        fk_graph = load_fk_graph()
        if hybrid_results is None:
            hybrid_results = hybrid_search_with_separate_results(natural_query)
        
        semantic_results = {
            "selected_tables": hybrid_results["selected_tables"],
            "all_semantic": hybrid_results["all_semantic"],
            "all_lexical": hybrid_results["all_lexical"],
            "keywords": hybrid_results.get("all_keywords", []),
            "values": hybrid_results.get("all_data_values", [])
        }
        
        top_columns = score_columns_by_relevance_separate(semantic_results, {}, top_n=TOP_COLUMNS_IN_CONTEXT)
        selected_tables = set(semantic_results["selected_tables"])
        schema_pool, paths, value_context = build_compact_schema_pool(
            semantic_results, selected_tables, fk_graph, top_columns=top_columns
        )
        
        self._cache_current_fk_paths(natural_query, paths)
        conversation_context = self._get_extended_conversation_context()
        
        schema_text = format_compact_schema_prompt_with_keywords(
            schema_pool, paths, fk_graph, top_columns, natural_query
        )
        
        # 2. Dinamik promptun oluşturulması
        dynamic_prompt = generate_strict_prompt_dynamic_only(
            natural_query, schema_text, schema_pool, value_context,
            extended_context=conversation_context
        )

        # 3. LLM ÇAĞRISI (Statik + Dinamik)
        # Model, STATIC_PROMPT kısmını hafızasından (KV Cache) tanıyacak ve baştan işlemeyecektir.
        full_prompt = f"{STATIC_PROMPT}\n\n{dynamic_prompt}"
        
        llm_start = time.time()
        try:
            response = self.llm(
                full_prompt,
                max_tokens=500,
                temperature=0,
                top_p=0.9,
                stop=[";", "Kullanıcı", "Açıklama", "```\n\n"],
                stream=False
            )
            text = self._parse_llm_response(response)
            print(f"⏱️ LLM call (Cached): {time.time() - llm_start:.2f}s")
            
        except Exception as e:
            print(f"❌ LLM call failed: {e}")
            text = "SELECT 1"

        # 4. SQL Temizleme ve Auto-fix (Mevcut kodun devamı)
        sql_text = extract_sql_from_response(text)
        sql_text, _ = clean_meaningless_where_clauses(sql_text)
        fixed_sql, _, _ = auto_fix_sql_identifiers(sql_text, schema_pool, value_context)
        
        return fixed_sql

        # 5. Build compact schema pool
        schema_start = time.time()
        schema_pool, paths, value_context = build_compact_schema_pool(
            semantic_results, selected_tables, fk_graph, top_columns=top_columns
        )
        
        # Cache this query's FK paths
        self._cache_current_fk_paths(natural_query, paths)
        
        # 6. Get conversation history and FK relationships
        conversation_context = self._get_extended_conversation_context()
        
        # 7. Schema formatting
        prompt_start = time.time()
        schema_text = format_compact_schema_prompt_with_keywords(
            schema_pool, paths, fk_graph, top_columns, natural_query
        )
        
        # 8. Build dynamic prompt - MATCHING ORIGINAL EXACTLY
        # extended_context is passed separately to the function now
        dynamic_prompt = generate_strict_prompt_dynamic_only(
            natural_query, schema_text, schema_pool, value_context,
            extended_context=conversation_context  # ✅ Pass as separate parameter like original
        )

        print(f"⏱️  [3] Prompt generation: {time.time() - prompt_start:.2f}s")
        print(f"📝 Context uzunluğu: Konuşma: {len(conversation_context)}")
        
        # Print dynamic prompt content
        print(f"\n{'='*100}")
        print(f"🎯 DİNAMİK PROMPT İÇERİĞİ:")
        print(f"{'='*100}")
        print(dynamic_prompt)
        print(f"{'='*100}")
        print(f"🎯 DİNAMİK PROMPT UZUNLUĞU: {len(dynamic_prompt)} karakter")
        print(f"🎯 STATIC_PROMPT UZUNLUĞU: {len(STATIC_PROMPT)} karakter")
        print(f"{'='*100}\n")

        # 9. LLM call
        llm_start = time.time()
        try:
            # CRITICAL: Combine STATIC_PROMPT + dynamic_prompt
            # KV cache doesn't work automatically - must send full prompt each time!
            full_prompt = STATIC_PROMPT + "\n\n" + dynamic_prompt
            
            print(f"🎯 FULL PROMPT UZUNLUĞU: {len(full_prompt)} karakter (STATIC + dynamic)")
            print(f"{'='*100}\n")
            
            response = self.llm(
                full_prompt,
                max_tokens=500,
                temperature=0,
                top_p=0.9,
                stop=[";", "Kullanıcı", "Açıklama", "AÇIKLAMA", "**AÇIKLAMA**", "ÖRNEK", "```\n\n", "<|end"],
                stream=False,
                echo=False
            )
            
            # Response parsing
            text = self._parse_llm_response(response)
            
            print(f"⏱️  [4] LLM call: {time.time() - llm_start:.2f}s")
            print(f"🤖 LLM Response:\n{text}\n")
            
        except Exception as e:
            print(f"❌ LLM call failed: {e}")
            text = "SELECT 1"

        # 10. Extract SQL
        extraction_start = time.time()
        sql_text = extract_sql_from_response(text)
        print(f"⏱️  [5] SQL extraction: {time.time() - extraction_start:.2f}s")
        
        # 11. Clean meaningless WHERE clauses
        sql_text, where_changes = clean_meaningless_where_clauses(sql_text)
        if where_changes:
            print(f"🧹 Cleaned WHERE clauses:")
            for c in where_changes:
                print(f"  - {c}")
        
        # 12. Auto-fix
        autofix_start = time.time()
        try:
            print("🔧 Auto-fix running...")
            fixed_sql, changes, issues = auto_fix_sql_identifiers(
                sql_text, schema_pool, value_context
            )
            if changes:
                print(f"🔁 Auto-fix applied. Changes ({len(changes)}):")
                for c in changes[:5]:
                    print("  -", c)
                sql_to_format = fixed_sql
            else:
                print("🔎 Auto-fix found no changes.")
                sql_to_format = sql_text
            
            if issues:
                print("⚠️ Auto-fix issues:")
                for it in issues[:3]:
                    print("  -", it)
                    
        except Exception as e:
            print(f"❌ Auto-fix failed: {e}")
            sql_to_format = sql_text
        
        print(f"⏱️  [6] Auto-fix: {time.time() - autofix_start:.2f}s")
        
        # 13. Format SQL
        format_start = time.time()
        try:
            parsed = sqlparse.parse(sql_to_format)
            if not parsed:
                raise ValueError("❌ SQL parse edilemedi")
            final_sql = sqlparse.format(str(parsed[0]), reindent=True, keyword_case='upper')
        except Exception as e:
            print(f"❌ SQL formatting failed: {e}")
            final_sql = sql_to_format
        
        print(f"⏱️  [7] SQL formatting: {time.time() - format_start:.2f}s")
        
        total_time = time.time() - start_time
        print(f"\n{'#'*80}")
        print(f"# ✅ COMPLETED - {total_time:.2f}s")
        print(f"# FINAL SQL:")
        print(f"{'#'*80}")
        print(final_sql)
        print(f"{'#'*80}\n")
        
        return final_sql

    def _get_current_schema_pool(self, natural_query: str = "schema discovery") -> Dict:
        """Get current schema pool."""
        try:
            # If schema pool doesn't exist, construct via hybrid search
            if not self.current_schema_pool:
                print("🔍 Schema pool bulunamadı, yeniden oluşturuluyor...")
                fk_graph = load_fk_graph()
                
                # Do hybrid search
                hybrid_results = hybrid_search_with_separate_results(natural_query, top_k=MAX_INITIAL_RESULTS)
                
                # Prepare semantic results in correct format
                semantic_results = {
                    "selected_tables": hybrid_results["selected_tables"],
                    "all_semantic": hybrid_results["all_semantic"],
                    "all_lexical": hybrid_results["all_lexical"],
                    "keywords": hybrid_results.get("all_keywords", []),
                    "values": hybrid_results.get("all_data_values", [])
                }
                
                # Perform column scoring
                top_columns = score_columns_by_relevance_separate(semantic_results, {}, top_n=20)
                
                # Use balanced table selection
                selected_tables = select_top_tables_balanced(semantic_results, top_columns, target_count=15)
                
                # Build schema pool
                schema_pool, _, _ = build_compact_schema_pool(
                    semantic_results, selected_tables, fk_graph, top_columns=top_columns
                )
                
                self.current_schema_pool = schema_pool

                print(f"✅ Schema pool created: {len(schema_pool)} tables")
            
            return self.current_schema_pool
        
        except Exception as e:
            print(f"❌ Schema pool creation error: {e}")
            return {}

    def _handle_error_interactively(self, error_message: str, sql_query: str, 
                              natural_query: str, attempt: int) -> Optional[Dict]:
        """Ask the user about the error interactively."""
        try:
            # Get current schema pool
            schema_pool = self._get_current_schema_pool()
            
            # Analyze the error
            error_analysis = self.error_analyzer.analyze_error(
                error_message, sql_query, schema_pool
            )
            
            # Add the error to conversation history
            self._add_to_conversation_history("error", error_analysis)
            
            print(f"🔍 Hata analizi tamamlandı: {error_analysis['error_type']}")
            
            # Does user interaction required?
            if error_analysis["needs_clarification"] and attempt < self.max_retries:
                question = self._format_clarification_question(error_analysis)
                return {
                    "success": False,
                    "sql": sql_query,
                    "error": error_analysis["message"],
                    "needs_clarification": True,
                    "clarification_question": question,
                    "natural_query": natural_query,
                    "error_type": error_analysis["error_type"],
                    "attempts": attempt
                }
                
        except Exception as e:
            print(f"⚠️ Hata işleme sırasında exception: {e}")
            import traceback
            traceback.print_exc()
        
        return None

    def _format_clarification_question(self, error_analysis: Dict) -> str:
        """Format the question to ask the user."""
        if error_analysis["error_type"] == "timestamp_format_error":
            invalid_value = error_analysis["problematic_parts"][0] if error_analysis["problematic_parts"] else "bilinmeyen"
            suggestions = error_analysis["suggestions"]
            
            question = f"⚠️  '{invalid_value}' geçersiz tarih/zaman formatı.\n\n"
            question += "Lütfen bir seçenek belirleyin:\n"
            
            for i, suggestion in enumerate(suggestions, 1):
                display_text = suggestion.get('description', str(suggestion)) if isinstance(suggestion, dict) else str(suggestion)
                question += f"{i}. {display_text}\n"
            
            question += "\nLütfen bir numara seçin veya kendi tarih değerinizi yazın:"
            return question
            
        elif error_analysis["error_type"] == "missing_table":
            table_name = error_analysis["problematic_parts"][0] if error_analysis["problematic_parts"] else "bilinmeyen"
            suggestions = error_analysis["suggestions"][:3]
            
            question = f"⚠️  '{table_name}' tablosu bulunamadı.\n\n"
            question += "Şunlardan birini mi kastettiniz?\n"
            
            for i, suggestion in enumerate(suggestions, 1):
                if isinstance(suggestion, dict):
                    table_name_display = suggestion.get('suggested', '')
                    confidence = suggestion.get('confidence', 0)
                    simple_name = unqualify_table(table_name_display)
                    question += f"{i}. {simple_name} ({confidence}% eşleşme)\n"
                else:
                    question += f"{i}. {suggestion}\n"
            
            question += "\nLütfen bir numara seçin veya doğru tablo adını yazın:"
            return question
        
        elif error_analysis["error_type"] == "missing_column":
            column_name = error_analysis["problematic_parts"][0] if error_analysis["problematic_parts"] else "bilinmeyen"
            suggestions = error_analysis["suggestions"][:3]
            
            question = f"⚠️  '{column_name}' sütunu bulunamadı.\n\n"
            question += "Şunlardan birini mi kastettiniz?\n"
            
            for i, suggestion in enumerate(suggestions, 1):
                if isinstance(suggestion, dict):
                    column_suggested = suggestion.get('suggested', '')
                    table_name = suggestion.get('table', '')
                    confidence = suggestion.get('confidence', 0)
                    table_simple = unqualify_table(table_name)
                    question += f"{i}. {column_suggested} ({confidence}% eşleşme, tablo: {table_simple})\n"
                else:
                    question += f"{i}. {suggestion}\n"
            
            question += "\nLütfen bir numara seçin veya doğru sütun adını yazın:"
            return question
            
        else:
            question = f"⚠️  SQL hatası: {error_analysis['message']}\n\nBu hatayı nasıl düzeltmek istersiniz?"
            return question

    def generate_with_feedback(self, natural_query: str, user_feedback: Optional[Dict] = None) -> Dict:
        """Generate interactive SQL."""
        attempts = 0
        last_error = None
        current_sql = ""
        
        # Add user feedback to conversation history
        if user_feedback:
            self._add_to_conversation_history("user_feedback", user_feedback)
            print(f"🔄 Kullanıcı geri bildirimi alındı: {user_feedback}")
        
        # Check skip_similarity_check flag
        skip_similarity_for_this_query = False
        if user_feedback and user_feedback.get('skip_similarity_check'):
            print("🚀 Skipping similarity check (skip_similarity_check=True)")
            skip_similarity_for_this_query = True
        
        # Enrich the natural query with context
        enhanced_query = self._enhance_natural_query_with_context(natural_query)
        print(f"🎯 Geliştirilmiş sorgu: {enhanced_query}")
        
        # Add the enriched query to conversation history
        self._add_to_conversation_history("user", enhanced_query, "user_query")
        
        while attempts < self.max_retries:
            attempts += 1
            print(f"\n🔄 SQL Generation Attempt {attempts}/{self.max_retries}")
            
            try:
                # Perform hybrid search and similarity check
                print("🔍 Hybrid search yapılıyor...")
                hybrid_results = hybrid_search_with_separate_results(natural_query, top_k=MAX_INITIAL_RESULTS)
                
                # Similarity check
                above_threshold_count = hybrid_results.get("above_threshold_count", 0)
                similar_tables = hybrid_results.get("similar_tables", [])
                
                print(f"📊 Eşik üstü tablo sayısı: {above_threshold_count}")
                
                # If no above-threshold tables and similar tables exist, show interactive table
                if above_threshold_count == 0 and similar_tables and not skip_similarity_for_this_query:
                    print(f"🎯 INTERAKTİF TABLO GÖSTERİLİYOR")
                    
                    suggestions = []
                    for table, score in similar_tables[:8]:
                        percent = int(score * 100)
                        suggestions.append({
                            "display": f"{table} (benzerlik: %{percent})",
                            "suggested": table,
                            "score": score,
                            "score_percent": percent,
                            "type": "interactive_table"
                        })
                    
                    max_similarity = max([score for table, score in similar_tables]) if similar_tables else 0
                    
                    return {
                        "success": False,
                        "needs_clarification": True,
                        "clarification_question": f"Sorgunuzla eşleşen tablolar aşağıda listelenmiştir. Hangisini kastettiniz?",
                        "suggestions": suggestions,
                        "error": f"Yüksek benzerlikli tablo bulunamadı. En iyi eşleşme: %{int(max_similarity*100)}",
                        "error_type": "low_similarity",
                        "similar_tables": similar_tables,
                        "attempts": attempts
                    }
                
                # Generate SQL (no error context on first attempt)
                current_sql = self._generate_smart_sql_direct(enhanced_query, error_context="", hybrid_results=hybrid_results)
                
                # Try running the SQL
                print("🔍 Running SQL...")
                columns, rows = run_sql(current_sql)
                
                # Remember successful queries
                self._add_to_conversation_history("assistant", current_sql, "successful_sql")
                self.last_successful_query = {
                    "sql": current_sql,
                    "natural_query": natural_query,
                    "timestamp": time.time()
                }
                
                # Successful
                return {
                    "success": True,
                    "sql": current_sql,
                    "columns": columns,
                    "rows": rows,
                    "needs_clarification": False,
                    "attempts": attempts
                }
                
            except Exception as e:
                last_error = str(e)
                print(f"❌ Attempt {attempts} failed: {last_error}")
                
                # Handle the error interactively
                interactive_result = self._handle_error_interactively(
                    last_error, current_sql, natural_query, attempts
                )
                
                if interactive_result:
                    return interactive_result
                
                if attempts == self.max_retries:
                    return {
                        "success": False,
                        "sql": current_sql,
                        "error": last_error,
                        "needs_clarification": False,
                        "attempts": attempts
                    }
        
        return {
            "success": False,
            "sql": current_sql,
            "error": last_error or "Max retries exceeded",
            "needs_clarification": False,
            "attempts": attempts
        }
