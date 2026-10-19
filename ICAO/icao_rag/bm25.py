"""Fast in-memory BM25 lexical search engine for acronyms, terms, and exact matches."""

import math
import re
from typing import Dict, List, Tuple


def default_tokenize(text: str) -> List[str]:
    """Tokenize text into lowercase alphanumeric words and standard technical terms."""
    # Matches words, acronyms, and hyphenated terms like CNS/ATM, 9562, A40-9
    clean = text.lower().replace("/", " ").replace("-", " ")
    return re.findall(r"\b[a-z0-9_]{2,}\b", clean)


class BM25Index:
    """BM25Okapi ranking implementation optimized for technical documentation retrieval."""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.corpus_size = 0
        self.avg_doc_len = 0.0
        self.doc_lens: List[int] = []
        self.doc_term_freqs: List[Dict[str, int]] = []
        self.idf: Dict[str, float] = {}

    def index(self, documents: List[str]):
        """Index a list of text documents."""
        self.corpus_size = len(documents)
        if self.corpus_size == 0:
            return

        self.doc_lens = []
        self.doc_term_freqs = []
        df: Dict[str, int] = {}

        total_len = 0
        for doc in documents:
            tokens = default_tokenize(doc)
            length = len(tokens)
            self.doc_lens.append(length)
            total_len += length

            tf: Dict[str, int] = {}
            for t in tokens:
                tf[t] = tf.get(t, 0) + 1

            self.doc_term_freqs.append(tf)
            for t in tf:
                df[t] = df.get(t, 0) + 1

        self.avg_doc_len = total_len / max(1, self.corpus_size)

        # Calculate Robertson-Spärck Jones IDF with smoothing
        self.idf = {}
        for term, freq in df.items():
            self.idf[term] = math.log(1.0 + (self.corpus_size - freq + 0.5) / (freq + 0.5))

    def get_scores(self, query: str) -> List[float]:
        """Compute BM25 scores for all indexed documents with respect to the query."""
        scores = [0.0] * self.corpus_size
        if self.corpus_size == 0:
            return scores

        query_tokens = default_tokenize(query)
        if not query_tokens:
            return scores

        for token in query_tokens:
            if token not in self.idf:
                continue

            idf_val = self.idf[token]
            for doc_idx, tf_dict in enumerate(self.doc_term_freqs):
                if token not in tf_dict:
                    continue

                tf = tf_dict[token]
                doc_len = self.doc_lens[doc_idx]
                denom = tf + self.k1 * (1.0 - self.b + self.b * (doc_len / self.avg_doc_len))
                score = idf_val * ((tf * (self.k1 + 1.0)) / max(1e-6, denom))
                scores[doc_idx] += score

        return scores
