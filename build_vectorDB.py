"""
build_embeddings.py

This script builds semantic and lexical embeddings for a Postgres schema and stores
them in Qdrant. It has been refactored to:
 - Use settings from `config.py` (reads .env via pydantic-settings)
 - Load `SCHEMA_KEYWORDS` from an external file the user can edit (schema_keywords.py/json/yaml)
 - All inline comments and printed messages are in English

Usage:
  - Put your schema keywords in one of the supported files in the working directory:
      * schema_keywords.py  (must define variable SCHEMA_KEYWORDS)
      * schema_keywords.json
      * schema_keywords.yaml  (requires PyYAML installed)
  - Ensure config.py and .env are configured and in the same project
  - Run: python build_embeddings.py

"""

import os
import json
import importlib.util
from typing import List, Dict, Any, Optional

import numpy as np
import psycopg2
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.models import PointStruct
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Import shared settings and helper functions from config.py
try:
    from config import settings, create_qdrant_client, get_db_conn_kwargs
except Exception as e:
    raise ImportError("Couldn't import config.py. Make sure config.py is in the PYTHONPATH and valid. Error: %s" % e)


# ==================== GPU DETECTION ====================
def detect_gpu():
    """GPU tespiti - Torch varsa ve CUDA kullanılabilirse True döner"""
    try:
        import torch
        if torch.cuda.is_available():
            print(f"🎮 GPU tespit edildi: {torch.cuda.get_device_name(0)}")
            return 'cuda'
        else:
            print("💻 GPU bulunamadı, CPU kullanılacak")
            return 'cpu'
    except ImportError:
        print("💻 PyTorch yüklü değil, CPU kullanılacak")
        return 'cpu'
    except Exception as e:
        print(f"⚠️ GPU tespiti hatası: {e}, CPU kullanılacak")
        return 'cpu'

DEVICE = detect_gpu() if (settings.USE_GPU is None or settings.USE_GPU) else 'cpu'
if settings.USE_GPU is False:
    print("⚙️ Ayarlardan dolayı CPU zorlandı")
    DEVICE = 'cpu'
print(f"🔧 build_vectorDB {DEVICE.upper()} üzerinde çalışacak")
# ==================== GPU DETECTION END ====================

# ------------------ Runtime configuration derived from config.py ------------------
DB_CONN_KW = get_db_conn_kwargs()
QDRANT_CLIENT: QdrantClient = create_qdrant_client()
EMBEDDING_MODEL_NAME = settings.EMBEDDING_MODEL_NAME
TFIDF_VECTORIZER_PATH = settings.TFIDF_VECTORIZER_PATH
LEXICAL_FASTTEXT_PATH = settings.LEXICAL_FASTTEXT_PATH
BATCH_SIZE = getattr(settings, "MAX_INITIAL_RESULTS", 128) or 128

# Initialize embedding model - GPU desteğiyle
EMBEDDING_MODEL = SentenceTransformer(EMBEDDING_MODEL_NAME, device=DEVICE)
VECTOR_SIZE = EMBEDDING_MODEL.get_sentence_embedding_dimension()
LEXICAL_VECTOR_SIZE_DEFAULT = 1000

# Schema name used for information_schema queries. Read from settings.DB_SCHEMA
SCHEMA_NAME = settings.DB_SCHEMA

# ------------------ Utility / I/O ------------------

def get_source_conn():
    """Return a new psycopg2 connection using config.py settings."""
    return psycopg2.connect(**DB_CONN_KW)


def get_qdrant_client() -> QdrantClient:
    """Return Qdrant client created from config.py helper."""
    return QDRANT_CLIENT


# ------------------ Schema keywords loader (external file) ------------------

def load_schema_keywords() -> Optional[Dict[str, Any]]:
    """Try to load SCHEMA_KEYWORDS from one of the supported files in the cwd.

    Supported files (checked in order):
      - schema_keywords.py  (must expose SCHEMA_KEYWORDS variable)
      - schema_keywords.json
      - schema_keywords.yaml (requires PyYAML)

    If none are found, returns None.
    """
    cwd = os.getcwd()
    py_path = os.path.join(cwd, "schema_keywords.py")
    json_path = os.path.join(cwd, "schema_keywords.json")
    yaml_path = os.path.join(cwd, "schema_keywords.yaml")

    if os.path.exists(py_path):
        spec = importlib.util.spec_from_file_location("schema_keywords_module", py_path)
        if spec is None or spec.loader is None:
            raise ImportError("Cannot load schema_keywords.py: spec or loader is None")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        if hasattr(module, "SCHEMA_KEYWORDS"):
            return getattr(module, "SCHEMA_KEYWORDS")
        else:
            raise RuntimeError("schema_keywords.py found but does not define SCHEMA_KEYWORDS")


    if os.path.exists(json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)

    if os.path.exists(yaml_path):
        try:
            import yaml  # type: ignore
        except Exception:
            raise RuntimeError("schema_keywords.yaml found but PyYAML is not installed. Install with `pip install pyyaml`")
        with open(yaml_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    return None


# ------------------ Basic tokenizer for lexical processing ------------------

def tokenize(text: str) -> List[str]:
    """Simple tokenizer used for lexical similarity. Converts underscores to spaces
    and splits on whitespace; filters out single-character tokens.
    """
    t = text.lower().replace("_", " ")
    return [w for w in t.split() if len(w) > 1]


# ------------------ Qdrant collections setup ------------------

def create_qdrant_collections(client: QdrantClient, lexical_vector_size: int = LEXICAL_VECTOR_SIZE_DEFAULT):
    """Recreate the collections used by the pipeline.

    Collections created:
      - schema_embeddings          (semantic schema vectors)
      - schema_keywords            (semantic keyword vectors)
      - data_samples               (semantic value vectors)
      - lexical_embeddings         (TF-IDF / n-gram lexical vectors)
    """

    # Prefer an explicit EMBEDDING_DIM from settings when provided (for overrides),
    # otherwise use the module-level computed VECTOR_SIZE from the loaded embedding model.
    embedding_dim = getattr(settings, "EMBEDDING_DIM", VECTOR_SIZE)

    # semantic collections using embedding dimension
    try:
        client.recreate_collection(
            collection_name=settings.QDRANT_SCHEMA_COLLECTION,
            vectors_config=models.VectorParams(size=embedding_dim, distance=models.Distance.COSINE),
        )
        client.recreate_collection(
            collection_name=settings.QDRANT_KEYWORDS_COLLECTION,
            vectors_config=models.VectorParams(size=embedding_dim, distance=models.Distance.COSINE),
        )
        client.recreate_collection(
            collection_name=settings.QDRANT_DATA_SAMPLES_COLLECTION,
            vectors_config=models.VectorParams(size=embedding_dim, distance=models.Distance.COSINE),
        )
    except TypeError:
        # fallback for older qdrant-client versions
        client.recreate_collection(settings.QDRANT_SCHEMA_COLLECTION, vectors_config=models.VectorParams(size=embedding_dim, distance=models.Distance.COSINE))
        client.recreate_collection(settings.QDRANT_KEYWORDS_COLLECTION, vectors_config=models.VectorParams(size=embedding_dim, distance=models.Distance.COSINE))
        client.recreate_collection(settings.QDRANT_DATA_SAMPLES_COLLECTION, vectors_config=models.VectorParams(size=embedding_dim, distance=models.Distance.COSINE))

    # lexical collection (size determined by TF-IDF vectorizer max_features)
    client.recreate_collection(
        collection_name=settings.QDRANT_LEXICAL_COLLECTION,
        vectors_config=models.VectorParams(size=lexical_vector_size, distance=models.Distance.COSINE),
    )

    print(f"Collections recreated: schema_embeddings(schema dim={embedding_dim}), schema_keywords(schema dim={embedding_dim}), data_samples(schema dim={embedding_dim}), lexical_embeddings(size={lexical_vector_size})")


# ------------------ Lexical embeddings using TF-IDF (char n-gram) ------------------

def build_lexical_embeddings(client: QdrantClient, batch_size: int = BATCH_SIZE):
    """Builds TF-IDF (character n-gram) vectors for <table, column> pairs and uploads to Qdrant.
    The TF-IDF vectorizer is saved to the path defined in config.
    """
    print("Building lexical embeddings (TF-IDF + char n-grams)")

    src = get_source_conn()
    cur = src.cursor()

    try:
        cur.execute("""
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema = %s
            ORDER BY table_name, ordinal_position
        """, (SCHEMA_NAME,))
        table_columns = cur.fetchall()

        documents: List[str] = []
        column_info: List[tuple] = []

        for table, column in table_columns:
            table_clean = str(table).replace("_", " ").lower()
            column_clean = str(column).replace("_", " ").lower()
            combined_text = f"{table_clean} {column_clean}"
            documents.append(combined_text)
            column_info.append((table, column, combined_text))

        print(f"Found {len(documents)} table-column combinations")

        if len(documents) == 0:
            print("No table-column documents found; skipping lexical embeddings.")
            return

        vectorizer = TfidfVectorizer(
            analyzer='char_wb',
            ngram_range=(2, 4),
            min_df=2,
            max_features=LEXICAL_VECTOR_SIZE_DEFAULT,
        )

        tfidf_matrix = vectorizer.fit_transform(documents)
        lexical_vector_size = min(LEXICAL_VECTOR_SIZE_DEFAULT, tfidf_matrix.shape[1])

        # Ensure only the lexical collection is recreated/updated with the correct size.
        # Recreating all collections here would erase previously uploaded semantic vectors.
        client_local = get_qdrant_client()
        try:
            client_local.recreate_collection(
                collection_name="lexical_embeddings",
                vectors_config=models.VectorParams(size=lexical_vector_size, distance=models.Distance.COSINE),
            )
        except TypeError:
            # fallback for older qdrant-client versions
            client_local.recreate_collection("lexical_embeddings", vectors_config=models.VectorParams(size=lexical_vector_size, distance=models.Distance.COSINE))

        # Upload points in batches
        points: List[PointStruct] = []
        for i, (table, column, combined_text) in enumerate(column_info):
            try:
                row = tfidf_matrix.getrow(i)
                dense_vector = row.toarray().ravel()
                norm = np.linalg.norm(dense_vector)
                if norm > 0:
                    dense_vector = dense_vector / norm

                payload = {
                    "table_name": table,
                    "column_name": column,
                    "combined_text": combined_text,
                    "embedding_type": "tfidf_ngram",
                }

                points.append(PointStruct(id=i + 1, vector=dense_vector.tolist(), payload=payload))

                if len(points) >= batch_size:
                    client.upsert(collection_name=settings.QDRANT_LEXICAL_COLLECTION, points=points)
                    print(f"Uploaded {len(points)} lexical points")
                    points = []

            except Exception as e:
                print(f"Warning: {table}.{column} error: {e}")
                continue

        if points:
            client.upsert(collection_name="lexical_embeddings", points=points)
            print(f"Uploaded {len(points)} lexical points (final)")

        # Save the TF-IDF vectorizer
        import joblib
        joblib.dump(vectorizer, TFIDF_VECTORIZER_PATH)
        print(f"Saved TF-IDF vectorizer to {TFIDF_VECTORIZER_PATH}")

        # Small test of the model
        test_queries = ["a ilce", "a_ilce", "a ilce bilgilerini getir", "a_ilce bilgilerini getir"]
        for query in test_queries:
            q_clean = query.replace('_', ' ').lower()
            q_vec = vectorizer.transform([q_clean])
            sims = cosine_similarity(q_vec, tfidf_matrix)
            top_indices = sims[0].argsort()[-3:][::-1]
            print(f"Query: '{query}'")
            for idx in top_indices:
                if sims[0][idx] > 0:
                    print(f"  - {documents[idx]} (score: {sims[0][idx]:.4f})")

    finally:
        cur.close()
        src.close()


# ------------------ Schema keywords (semantic) ------------------

def build_schema_keywords(client: QdrantClient, schema_keywords: Dict[str, Any], batch_size: int = BATCH_SIZE):
    """Create semantic keyword embeddings from the user-supplied schema keywords mapping.

    schema_keywords should be a dict mapping table_name -> { table_keywords: [...], column_keywords: {...} }
    """
    if not schema_keywords:
        print("No schema keywords provided; skipping schema keywords build.")
        return

    print("Building schema keywords (semantic)")
    points: List[PointStruct] = []
    id_counter = 1

    for table_name, config in schema_keywords.items():
        # Handle both formats: ["keyword1", "keyword2"] or [("keyword1", "type"), ...]
        table_kws = config.get("table_keywords", [])
        for item in table_kws:
            if isinstance(item, tuple):
                keyword, kw_type = item
            else:
                # If it's a string, use "synonym" as default type
                keyword = item
                kw_type = "synonym"
            
            text = f"{keyword} table (alternative name for {table_name})"
            emb = EMBEDDING_MODEL.encode([text])[0]
            payload = {
                "table_name": table_name,
                "column_name": None,
                "keyword": keyword,
                "keyword_type": kw_type,
                "embedding_type": "semantic_keyword",
            }
            points.append(PointStruct(id=id_counter, vector=emb.tolist(), payload=payload))
            id_counter += 1

            if len(points) >= batch_size:
                client.upsert(collection_name="schema_keywords", points=points)
                print(f"Uploaded {len(points)} keyword points")
                points = []

        for col_name, keywords in config.get("column_keywords", {}).items():
            for item in keywords:
                if isinstance(item, tuple):
                    keyword, kw_type = item
                else:
                    keyword = item
                    kw_type = "synonym"
                
                text = f"{keyword} column (alternative name for {table_name}.{col_name})"
                emb = EMBEDDING_MODEL.encode([text])[0]
                payload = {
                    "table_name": table_name,
                    "column_name": col_name,
                    "keyword": keyword,
                    "keyword_type": kw_type,
                    "embedding_type": "semantic_keyword",
                }
                points.append(PointStruct(id=id_counter, vector=emb.tolist(), payload=payload))
                id_counter += 1

                if len(points) >= batch_size:
                    client.upsert(collection_name=settings.QDRANT_KEYWORDS_COLLECTION, points=points)
                    print(f"Uploaded {len(points)} keyword points")
                    points = []

    if points:
        client.upsert(collection_name="schema_keywords", points=points)
        print(f"Uploaded {len(points)} keyword points (final)")

    print(f"Schema keywords built: {id_counter-1} vectors")


# ------------------ Schema embeddings (semantic) ------------------

def build_schema_embeddings(client: QdrantClient, batch_size: int = BATCH_SIZE):
    """Build semantic embeddings for schema entries (table.column + data type).
    Uploads embeddings to the 'schema_embeddings' collection.
    """
    print("Building schema embeddings (semantic)")

    src = get_source_conn()
    cur = src.cursor()

    try:
        cur.execute("""
            SELECT table_name, column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = %s
            ORDER BY table_name, ordinal_position
        """, (SCHEMA_NAME,))
        columns = cur.fetchall()

        points: List[PointStruct] = []
        id_counter = 1

        for table_name, column_name, data_type in columns:
            try:
                schema_text = f"{table_name} table {column_name} column type {data_type}"
                emb = EMBEDDING_MODEL.encode([schema_text])[0]
                payload = {
                    "table_name": table_name,
                    "column_name": column_name,
                    "data_type": data_type,
                    "schema_text": schema_text,
                    "embedding_type": "semantic_schema",
                }
                points.append(PointStruct(id=id_counter, vector=emb.tolist(), payload=payload))
                id_counter += 1

                if len(points) >= batch_size:
                    client.upsert(collection_name=settings.QDRANT_SCHEMA_COLLECTION, points=points)
                    print(f"Uploaded {len(points)} schema embedding points")
                    points = []

            except Exception as e:
                print(f"Warning: could not embed {table_name}.{column_name}: {e}")
                continue

        if points:
            client.upsert(collection_name=settings.QDRANT_SCHEMA_COLLECTION, points=points)
            print(f"Uploaded {len(points)} schema embedding points (final)")

        print(f"Schema embeddings complete: {id_counter-1} vectors")

    finally:
        cur.close()
        src.close()


# ------------------ Data samples (semantic) ------------------

def build_data_samples(client: QdrantClient, max_samples_per_column: int = 100, batch_size: int = BATCH_SIZE):
    """Extracts text samples from string/text columns and uploads semantic embeddings to Qdrant."""
    print("Building data samples (semantic)")

    src = get_source_conn()
    cur = src.cursor()

    try:
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = %s
              AND table_type = 'BASE TABLE'
            """,
            (SCHEMA_NAME,),
        )
        tables = [r[0] for r in cur.fetchall()]

        points: List[PointStruct] = []
        id_counter = 1

        ignore_tables = {"schema_embeddings", "schema_keywords", "data_samples", "lexical_embeddings"}

        for table in tables:
            if table in ignore_tables:
                continue

            cur.execute(
                """
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = %s AND table_schema = %s
                ORDER BY ordinal_position
                """,
                (table, SCHEMA_NAME),
            )
            cols = cur.fetchall()

            for col_name, data_type in cols:
                if 'char' not in str(data_type).lower() and 'text' not in str(data_type).lower():
                    continue

                try:
                    # Use quoted identifiers to handle case-sensitive table/column names
                    cur.execute(
                        f'SELECT DISTINCT "{col_name}"::TEXT FROM "{SCHEMA_NAME}"."{table}" WHERE "{col_name}" IS NOT NULL LIMIT %s',
                        (max_samples_per_column,),
                    )
                    samples = [r[0] for r in cur.fetchall() if r[0]]

                    for sample in samples:
                        if len(sample) > 200:
                            continue
                        text = f"{sample} value in {table}.{col_name}"
                        emb = EMBEDDING_MODEL.encode([text])[0]
                        payload = {
                            "table_name": table,
                            "column_name": col_name,
                            "sample_value": sample,
                            "value_type": 'text',
                            "embedding_type": "semantic_value",
                        }
                        points.append(PointStruct(id=id_counter, vector=emb.tolist(), payload=payload))
                        id_counter += 1

                        if len(points) >= batch_size:
                            client.upsert(collection_name=settings.QDRANT_DATA_SAMPLES_COLLECTION, points=points)
                            print(f"Uploaded {len(points)} data sample points")
                            points = []

                except Exception as e:
                    print(f"Warning: could not sample {table}.{col_name}: {e}")
                    try:
                        src.rollback()
                    except Exception:
                        pass
                    continue

        if points:
            client.upsert(collection_name="data_samples", points=points)
            print(f"Uploaded {len(points)} data sample points (final)")

        print(f"Data samples complete: {id_counter-1} vectors")

    finally:
        cur.close()
        src.close()


# ------------------ Main pipeline ------------------

def main():
    client = get_qdrant_client()

    # 1) Create collections (lexical size will be adjusted later during lexical build)
    create_qdrant_collections(client)

    # 2) Build semantic schema embeddings
    build_schema_embeddings(client) 
    
    # 3) Build lexical embeddings (this will adjust lexical collection size if needed)
    build_lexical_embeddings(client)

    # 4) Load user-supplied schema keywords from external file and build them
    loaded_schema_keywords = load_schema_keywords()

    SCHEMA_KEYWORDS_EXAMPLE = {
        # Example: Users table
        "users": {
            "table_keywords": [
                ("kullanıcı", "translation"),
                ("user", "translation"),
                ("hesap", "translation"),
                ("account", "translation")
            ],
            "column_keywords": {
                "user_id": [("kullanıcı kimliği", "translation"), ("user id", "translation")],
                "email": [("e-posta", "translation"), ("mail", "translation")],
                "created_at": [("oluşturulma tarihi", "translation"), ("kayıt tarihi", "translation")],
                "full_name": [("ad soyad", "translation"), ("isim", "translation")],
            }
        },
        
        # Example: Orders table
        "orders": {
            "table_keywords": [
                ("sipariş", "translation"),
                ("order", "translation"),
                ("satın alma", "translation"),
                ("purchase", "translation")
            ],
            "column_keywords": {
                "order_id": [("sipariş numarası", "translation"), ("order number", "translation")],
                "order_date": [("sipariş tarihi", "translation"), ("tarih", "translation")],
                "total_amount": [("toplam tutar", "translation"), ("fiyat", "translation"), ("miktar", "translation")],
                "status": [("durum", "translation"), ("status", "translation")],
            }
        },
        
        # Example: Products table
        "products": {
            "table_keywords": [
                ("ürün", "translation"),
                ("product", "translation"),
                ("mal", "translation"),
                ("stok", "translation")
            ],
            "column_keywords": {
                "product_id": [("ürün kodu", "translation"), ("product code", "translation")],
                "product_name": [("ürün adı", "translation"), ("isim", "translation")],
                "price": [("fiyat", "translation"), ("ücret", "translation")],
                "category": [("kategori", "translation"), ("tür", "translation")],
            }
        },
    }

    if loaded_schema_keywords is None:
        print("No external schema keywords file found. Using example mapping. Create schema_keywords.py/json/yaml to customize.")
        schema_keywords_to_use = SCHEMA_KEYWORDS_EXAMPLE
    else:
        schema_keywords_to_use = loaded_schema_keywords

    build_schema_keywords(client, schema_keywords_to_use)

    # 5) Build data samples
    build_data_samples(client, max_samples_per_column=100)

    print("All embeddings created: semantic (schema_embeddings, schema_keywords, data_samples) and lexical (lexical_embeddings)")


if __name__ == "__main__":
    main()
